"""Villa Commissioner API.

Run from the repo folder:
    .venv/bin/uvicorn backend.main:app --reload --port 8000
Docs at http://localhost:8000/docs. If frontend/dist exists it is served at http://localhost:8000/.
"""
from collections import defaultdict
from pathlib import Path
import json
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pydantic_ai.exceptions import AgentRunError, ModelHTTPError, UsageLimitExceeded

from backend import config, scoring
from backend.agents import host, recapper, ref, rulesmith, scout

app = FastAPI(title="Villa Commissioner", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

# One agent run or league write at a time: the league files are plain JSON.
WRITE_LOCK = threading.Lock()


class HouseRulesIn(BaseModel):
    text: str = Field(min_length=3, max_length=rulesmith.MAX_REQUEST_CHARS)


class DisputeIn(BaseModel):
    player: str
    text: str = Field(min_length=3, max_length=ref.MAX_DISPUTE_CHARS)


def _league(key: str) -> dict:
    if not scoring.league_path(key).exists():
        raise HTTPException(404, f"No league '{key}'")
    return scoring.load_league(key)


def _guard(fn, *args, **kwargs):
    """Run an agent step with clean HTTP errors instead of stack traces."""
    try:
        with WRITE_LOCK:
            return fn(*args, **kwargs)
    except KeyError as e:
        raise HTTPException(400, str(e.args[0]) if e.args else "Not found")
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    except UsageLimitExceeded as e:
        raise HTTPException(429, f"Stopped by the run's safety limits: {e}")
    except (ModelHTTPError, AgentRunError) as e:
        raise HTTPException(502, f"The model call failed: {e}")


# ---------- app + season ----------

@app.get("/api/config")
def get_config():
    return {"source_mode": config.SOURCE_MODE, "snapshot": config.SNAPSHOT, "model": config.MODEL_NAME,
            "seasons": {k: {"show": v["show"], "season": v["season"]} for k, v in scout.seasons().items()}}


@app.get("/api/seasons/{season}/weeks")
def season_weeks(season: str):
    if season not in scout.seasons():
        raise HTTPException(404, f"No season '{season}'")
    s = scout.seasons()[season]
    guide = scout.wiki.episode_guide("wikipedia", s["pages"]["wikipedia"])
    events = recapper.latest_events(season)
    weeks = defaultdict(lambda: {"episodes": [], "aired": []})
    for ep in guide:
        if ep["week"] and ep["week"].startswith("Week"):
            weeks[ep["week"]]["episodes"].append(ep["episode"])
            weeks[ep["week"]]["aired"].append(ep["aired"])
    out = []
    for w, info in sorted(weeks.items(), key=lambda kv: scoring.week_num(kv[0])):
        evs = events.get(w, [])
        out.append({"week": w, "episodes": info["episodes"], "first_aired": min(info["aired"]),
                    "last_aired": max(info["aired"]), "recapped": w in events,
                    "verified_events": sum(e.status == "verified" for e in evs),
                    "rejected_events": sum(e.status == "rejected" for e in evs)})
    return out


@app.get("/api/seasons/{season}/events")
def season_events(season: str, week: str | None = None):
    events = recapper.latest_events(season)
    return {w: [e.model_dump() for e in evs] for w, evs in events.items() if not week or w == week}


@app.get("/api/seasons/{season}/sources")
def week_sources(season: str, week: str):
    try:
        return recapper.latest_bundle(season, week).model_dump()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/seasons/{season}/weeks/{n}/refresh")
def refresh_week(season: str, n: int):
    """Scout + Recapper for one week (live sources, or the snapshot in snapshot mode)."""
    def run():
        bundle, scout_run = scout.run_scout(season, f"Week {n}")
        events, recap_run = recapper.run_recapper(season, bundle)
        return {"week": bundle.week, "sources": len(bundle.sources), "gaps": bundle.gaps,
                "verified_events": recap_run["events_verified"], "rejected_events": recap_run["events_rejected"],
                "cost_usd": round(scout_run["usage"]["total_cost_usd"] + recap_run["usage"]["cost_usd"], 6),
                "seconds": round(scout_run["seconds"] + recap_run["seconds"], 1)}
    return _guard(run)


# ---------- leagues ----------

@app.get("/api/leagues")
def leagues():
    return [{"key": p.stem, "name": json.loads(p.read_text())["name"]}
            for p in sorted((config.DATA / "leagues").glob("*.json"))]


@app.get("/api/leagues/{key}")
def league(key: str):
    return _league(key)


@app.get("/api/leagues/{key}/standings")
def league_standings(key: str, week: int | None = None):
    _league(key)
    r = _guard(scoring.score_league, key, save=week is None, up_to_week=week)
    return {k: r[k] for k in ("league", "weeks", "standings", "rules")}


@app.get("/api/leagues/{key}/ledger")
def league_ledger(key: str, week: str | None = None, islander: str | None = None, player: str | None = None):
    lg = _league(key)
    lines = scoring.score_league(key, save=False)["ledger"]
    if player:
        roster = {s["islander"]: s.get("from_week", 1) for p in lg["players"] if p["name"] == player for s in p["roster"]}
        lines = [l for l in lines if l["islander"] in roster and scoring.week_num(l["week"]) >= roster[l["islander"]]]
    return [l for l in lines if (not week or l["week"] == week) and (not islander or l["islander"] == islander)]


@app.post("/api/leagues/{key}/house-rules")
def propose_house_rules(key: str, body: HouseRulesIn):
    _league(key)

    def run():
        new, proposal, run = rulesmith.propose(key, body.text)
        rows, matches = rulesmith.impact(key, [r.id for r in new]) if new else ([], {})
        return {"rules": [r.model_dump() for r in new], "unsupported": [u.model_dump() for u in proposal.unsupported],
                "impact": rows, "matches": matches, "cost_usd": run["usage"]["cost_usd"], "seconds": run["seconds"]}
    return _guard(run)


@app.post("/api/leagues/{key}/house-rules/{rule_id}/{decision}")
def decide_house_rule(key: str, rule_id: str, decision: str):
    if decision not in ("approve", "decline"):
        raise HTTPException(400, "decision must be approve or decline")
    _league(key)
    changed = _guard(rulesmith.set_status, key, [rule_id], "approved" if decision == "approve" else "declined")
    if not changed:
        raise HTTPException(409, f"{rule_id} is not pending")
    return {"changed": changed}


@app.get("/api/leagues/{key}/disputes")
def disputes(key: str):
    return _league(key).get("disputes", [])


@app.post("/api/leagues/{key}/disputes")
def file_dispute(key: str, body: DisputeIn):
    _league(key)

    def run():
        record, run = ref.file_dispute(key, body.player, body.text)
        impact = ref.impact(key, record) if record["adjustments"] else []
        return {"dispute": record, "impact": impact, "steps": [s["tool"] for s in run["steps"]],
                "cost_usd": run["usage"]["cost_usd"], "seconds": run["seconds"]}
    return _guard(run)


@app.post("/api/leagues/{key}/disputes/{dispute_id}/{decision}")
def decide_dispute(key: str, dispute_id: str, decision: str):
    if decision not in ("approve", "decline"):
        raise HTTPException(400, "decision must be approve or decline")
    lg = _league(key)
    if dispute_id not in {d["id"] for d in lg.get("disputes", [])}:
        raise HTTPException(404, f"No dispute '{dispute_id}'")
    return _guard(ref.decide, key, dispute_id, decision == "approve")


@app.get("/api/leagues/{key}/drops/{week}")
def get_drop(key: str, week: int):
    path = config.OUTPUT / "drops" / f"{key}_week{week}.json"
    if not path.exists():
        raise HTTPException(404, f"No drop for week {week} yet")
    return json.loads(path.read_text())


@app.post("/api/leagues/{key}/drops/{week}")
def make_drop(key: str, week: int):
    _league(key)

    def run():
        record, run = host.write_drop(key, week)
        return {**record, "cost_usd": run["usage"]["cost_usd"], "seconds": run["seconds"]}
    return _guard(run)


# ---------- tokenomics ----------

@app.get("/api/usage")
def usage():
    """Measured cost of every agent run so far, from output/runs/*.json."""
    per_agent = defaultdict(lambda: {"runs": 0, "cost_usd": 0.0, "input_tokens": 0, "cached_input_tokens": 0,
                                     "output_tokens": 0, "seconds": 0.0, "gateway_cache_hits": 0})
    for f in sorted((config.OUTPUT / "runs").glob("*.json")):
        data = json.loads(f.read_text())
        run = data.get("run", data)
        u = run.get("usage", {})
        parts = [u["scout_agent"], u["web_search_tool"]] if "scout_agent" in u else [u]
        a = per_agent[run.get("agent", f.stem.split("_")[0])]
        a["runs"] += 1
        a["seconds"] += run.get("seconds", 0)
        for part in parts:
            a["cost_usd"] += part.get("cost_usd", 0)
            for k in ("input_tokens", "cached_input_tokens", "output_tokens", "gateway_cache_hits"):
                a[k] += part.get(k, 0)
    for a in per_agent.values():
        a["avg_cost_usd"] = round(a["cost_usd"] / a["runs"], 6)
        a["avg_seconds"] = round(a["seconds"] / a["runs"], 1)
        a["cost_usd"] = round(a["cost_usd"], 6)
    return dict(per_agent)


# ---------- built frontend (optional) ----------

DIST = config.ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = DIST / path
        return FileResponse(file if path and file.is_file() else DIST / "index.html")
