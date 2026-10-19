"""Host agent: writes the weekly standings drop from a code-built fact sheet; code checks numbers and spoilers.

Usage:
    python -m backend.agents.host --league demo_league --week 2
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import json
import re

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.usage import UsageLimits

from backend import config, llm, scoring, verify
from backend.agents.recapper import verification_context
from backend.agents.scout import seasons
from backend.models import Drop
from backend.sources import cast as cast_source

USAGE_LIMITS = UsageLimits(request_limit=4, total_tokens_limit=60_000)
MODEL_SETTINGS = OpenAIResponsesModelSettings(max_tokens=6_000, openai_prompt_cache_key="villa-host")
MAX_MOMENTS = 8
FINALE_WORDS = re.compile(r"won (the )?(season|show|love island)|crowned|champions?\b|finale", re.I)


@dataclass
class HostDeps:
    facts: dict
    allowed_numbers: set[int]
    players: list[str]
    moment_ids: set[str]
    future_islanders: list[str]  # names that would be spoilers this week
    final_week: bool


agent = Agent(deps_type=HostDeps, output_type=Drop, retries=2, model_settings=MODEL_SETTINGS,
              instructions=(config.PROMPTS / "host.md").read_text())


def _numbers(obj) -> set[int]:
    return {abs(int(n)) for n in re.findall(r"-?\d+", json.dumps(obj))}


def build_facts(league_key: str, week: int) -> tuple[dict, dict]:
    """(fact sheet for the model, extra context for the checks). Uses only weeks <= `week` (spoiler-safe)."""
    league = scoring.load_league(league_key)
    now = scoring.score_league(league_key, save=False, up_to_week=week)
    before = scoring.score_league(league_key, save=False, up_to_week=week - 1) if week > 1 else None
    wk = f"Week {week}"
    if wk not in now["weeks"]:
        raise ValueError(f"{wk} has not been scored yet")
    prev_rank = {r["player"]: i for i, r in enumerate(before["standings"], 1)} if before else {}

    owners = defaultdict(list)  # islander -> players who have them this week
    for p in league["players"]:
        for slot in p["roster"]:
            if slot.get("from_week", 1) <= week:
                owners[slot["islander"]].append(p["name"])

    by_event = defaultdict(lambda: {"islanders": set(), "labels": set(), "league_points": 0, "quote": ""})
    for line in now["ledger"]:
        if line["week"] != wk or line["rule_id"] == "std-survive":
            continue
        m = by_event[line["event_id"]]
        m["islanders"].add(line["islander"])
        m["labels"].add(f"{line['label']} ({line['points']:+d})")
        m["quote"] = m["quote"] or line["quote"]
        if owners.get(line["islander"]):
            m["league_points"] += line["points"]
    moments = sorted(({"event_id": eid, "islanders": sorted(m["islanders"]), "scored": sorted(m["labels"]),
                       "teams": sorted({o for i in m["islanders"] for o in owners.get(i, [])}),
                       "points_for_teams": m["league_points"], "quote": m["quote"]}
                      for eid, m in by_event.items()), key=lambda m: -abs(m["points_for_teams"]))[:MAX_MOMENTS]

    standings = [{"rank": i, "player": r["player"], "total": r["total"], "this_week": r["by_week"][wk],
                  "rank_change": (prev_rank[r["player"]] - i) if prev_rank else 0,
                  "team": [s["islander"] for p in league["players"] if p["name"] == r["player"]
                           for s in p["roster"] if s.get("from_week", 1) <= week]}
                 for i, r in enumerate(now["standings"], 1)]
    dumped = sorted({l["islander"] for l in now["ledger"] if l["week"] == wk and l["label"].lower().startswith("dump")})
    facts = {"league": league["name"], "week": wk, "standings": standings, "moments": moments,
             "dumped_this_week": dumped,
             "house_rules": [f"{r['label']} {r['points']:+d}" for r in now["rules"] if r["source"] == "house"]}

    season = seasons()[league["season"]]
    _, days = verification_context(league["season"], wk)
    week_end = days[1] if days else 0
    people = cast_source.cast(season["pages"]["wikipedia"])
    future = [p["first_name"] for p in people if (p["stints"][0]["entered"] or 0) > week_end]
    final = any(l["week"] == wk and l["rule_id"] in ("std-win",) for l in now["ledger"])
    ctx = {"future_islanders": future, "final_week": final, "standings_table": standings}
    return facts, ctx


@agent.output_validator
def facts_only(ctx: RunContext[HostDeps], drop: Drop) -> Drop:
    d = ctx.deps
    problems = []
    texts = [drop.headline, drop.opener, drop.closer] + [p.line for p in drop.player_lines] + [m.line for m in drop.moments]
    for n in {int(x) for t in texts for x in re.findall(r"\d+", t)}:
        if n not in d.allowed_numbers:
            problems.append(f"the number {n} is not in the fact sheet")
    named = [p.player for p in drop.player_lines]
    if sorted(named) != sorted(d.players):
        problems.append(f"player_lines must cover exactly these players once each: {d.players} (got {named})")
    for m in drop.moments:
        if m.event_id not in d.moment_ids:
            problems.append(f"moment '{m.event_id}' is not in the fact sheet")
    full = " ".join(texts)
    for name in d.future_islanders:
        if re.search(rf"\b{re.escape(name)}\b", full):
            problems.append(f"spoiler: {name} hasn't entered the villa yet this week")
    if not d.final_week and FINALE_WORDS.search(full):
        problems.append("spoiler: don't talk about the season winner or finale before the final week")
    if problems:
        raise ModelRetry("Fix these problems in the drop:\n" + "\n".join(f"- {p}" for p in problems))
    return drop


def render_markdown(facts: dict, drop: Drop) -> str:
    """Code renders the real standings table and the receipts; the model only supplies the words."""
    lines = [f"# {drop.headline}", f"*{facts['league']} · {facts['week']}*", "", drop.opener, "",
             "| # | Player | Total | This week | Move |", "|---|---|---|---|---|"]
    for r in facts["standings"]:
        move = "–" if not r["rank_change"] else (f"▲{r['rank_change']}" if r["rank_change"] > 0 else f"▼{-r['rank_change']}")
        lines.append(f"| {r['rank']} | {r['player']} | {r['total']} | {r['this_week']:+d} | {move} |")
    lines += ["", "## The group chat report"]
    lines += [f"- **{p.player}:** {p.line}" for p in drop.player_lines]
    lines += ["", "## Moments that moved the league"]
    by_id = {m["event_id"]: m for m in facts["moments"]}
    for m in drop.moments:
        f = by_id[m.event_id]
        lines.append(f"- {m.line}  \n  <sub>Receipt: “{f['quote']}” · {', '.join(f['scored'])}</sub>")
    lines += ["", f"_{drop.closer}_", ""]
    return "\n".join(lines)


def write_drop(league_key: str, week: int) -> tuple[dict, dict]:
    facts, ctx = build_facts(league_key, week)
    deps = HostDeps(facts=facts, allowed_numbers=_numbers(facts) | {week + 1, len(facts["standings"])},
                    players=[r["player"] for r in facts["standings"]],
                    moment_ids={m["event_id"] for m in facts["moments"]},
                    future_islanders=ctx["future_islanders"], final_week=ctx["final_week"])
    recorder = llm.UsageRecorder()
    started = datetime.now(timezone.utc)
    result = agent.run_sync("Fact sheet:\n" + json.dumps(facts, indent=1, ensure_ascii=False), deps=deps,
                            model=llm.build_model(recorder), usage_limits=USAGE_LIMITS)
    drop = result.output
    markdown = render_markdown(facts, drop)
    record = {"league": league_key, "week": facts["week"], "written": started.isoformat(timespec="seconds"),
              "drop": drop.model_dump(), "facts": facts, "markdown": markdown}
    out = config.OUTPUT / "drops"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{league_key}_week{week}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False))
    (out / f"{league_key}_week{week}.md").write_text(markdown)
    run = {"agent": "host", "league": league_key, "week": facts["week"], "started": record["written"],
           "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
           "usage": llm.recorder_totals(recorder), "model_requests": len(recorder.calls)}
    (config.OUTPUT / "runs" / f"host_{league_key}_week{week}_{started.strftime('%Y%m%dT%H%M%S')}.json").write_text(
        json.dumps(run, indent=1))
    return record, run


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Write the weekly standings drop.")
    p.add_argument("--league", default="demo_league")
    p.add_argument("--week", type=int, default=1)
    args = p.parse_args()
    record, run = write_drop(args.league, args.week)
    print(record["markdown"])
    print(f"({run['seconds']}s, {run['model_requests']} model call(s), ${run['usage']['cost_usd']})")
