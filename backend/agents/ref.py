"""Ref agent: investigates a player's dispute and proposes event fixes, which code verifies and the commissioner approves.

Usage:
    python -m backend.agents.ref --league demo_league file Jolie "Caleb should get date points in week 2"
    python -m backend.agents.ref --league demo_league list
    python -m backend.agents.ref --league demo_league approve dispute-1
    python -m backend.agents.ref --league demo_league decline dispute-1
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import argparse
import json

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.usage import UsageLimits

from backend import config, llm, scoring, verify
from backend.agents.recapper import latest_bundle, latest_events, verification_context
from backend.models import CheckedEvent, Event, Ruling
from backend.sources import clean

USAGE_LIMITS = UsageLimits(request_limit=10, tool_calls_limit=16, total_tokens_limit=120_000)
MODEL_SETTINGS = OpenAIResponsesModelSettings(max_tokens=6_000, openai_prompt_cache_key="villa-ref")
MAX_DISPUTE_CHARS = 1_000
LIST_LIMIT = 40


@dataclass
class RefDeps:
    league_key: str
    season_key: str
    player: str
    weeks: list[str]
    standings: dict = field(default_factory=dict)
    checked_adds: list[CheckedEvent] = field(default_factory=list)


agent = Agent(deps_type=RefDeps, output_type=Ruling, retries=2, model_settings=MODEL_SETTINGS,
              instructions=(config.PROMPTS / "ref.md").read_text())


@agent.instructions
def league_context(ctx: RunContext[RefDeps]) -> str:
    league = scoring.load_league(ctx.deps.league_key)
    rosters = "; ".join(f"{p['name']}: " + ", ".join(s["islander"] for s in p["roster"]) for p in league["players"])
    rules = "\n".join(f"- {r['id']}: {r['label']} ({r['event_type']}) {r['points']:+d}"
                      + (f" if quote has {r['quote_keywords']}" if r["quote_keywords"] else "")
                      for r in ctx.deps.standings["rules"])
    return (f"Weeks scored so far: {', '.join(ctx.deps.weeks)}.\nTeams: {rosters}.\n"
            f"Rules in force:\n{rules}\nThe dispute was filed by: {ctx.deps.player}.")


@agent.tool
def view_ledger(ctx: RunContext[RefDeps], islander: str | None = None, week: str | None = None) -> list[dict]:
    """Points already scored, filtered by islander first name and/or week (e.g. 'Week 2')."""
    rows = [l for l in ctx.deps.standings["ledger"]
            if (not islander or l["islander"].lower() == islander.lower()) and (not week or l["week"] == week)]
    return [{k: l[k] for k in ("week", "event_id", "islander", "label", "points", "quote")} for l in rows[:LIST_LIMIT]]


@agent.tool
def view_events(ctx: RunContext[RefDeps], week: str, islander: str | None = None) -> list[dict]:
    """The Recapper's events for a week, including rejected ones and why they failed the check."""
    events = latest_events(ctx.deps.season_key).get(week, [])
    if islander:
        events = [e for e in events if islander.lower() in [n.lower() for n in e.islanders + e.others]]
    return [{"id": e.id, "type": e.type, "islanders": e.islanders, "others": e.others, "day": e.day,
             "status": e.status, "problems": e.problems, "quotes": [ev.quote for ev in e.evidence]}
            for e in events[:LIST_LIMIT]]


@agent.tool
def list_sources(ctx: RunContext[RefDeps], week: str) -> list[dict]:
    """The Scout's sources for a week (IDs, kinds, titles)."""
    try:
        bundle = latest_bundle(ctx.deps.season_key, week)
    except FileNotFoundError as e:
        return [{"error": str(e)}]
    return [{"id": s.id, "kind": s.kind, "title": s.title, "chars": len(s.text)} for s in bundle.sources]


@agent.tool
def read_source(ctx: RunContext[RefDeps], week: str, source_id: str) -> dict:
    """Full text of one of a week's sources."""
    try:
        bundle = latest_bundle(ctx.deps.season_key, week)
    except FileNotFoundError as e:
        return {"error": str(e)}
    src = next((s for s in bundle.sources if s.id == source_id), None)
    return {"error": f"No source {source_id} in {week}"} if src is None else \
        {"id": src.id, "title": src.title, "text": src.text, "injection_flags": src.flags}


@agent.output_validator
def fixes_hold_up(ctx: RunContext[RefDeps], ruling: Ruling) -> Ruling:
    """Code checks every proposed fix: added events need valid receipts, removals need real event IDs."""
    problems, checked = [], []
    all_events = latest_events(ctx.deps.season_key)
    known_ids = {e.id for evs in all_events.values() for e in evs}
    for eid in ruling.remove_event_ids:
        if eid not in known_ids:
            problems.append(f"remove: there is no event '{eid}'")
    for ev in ruling.add_events:
        if ev.week not in ctx.deps.weeks:
            problems.append(f"add {ev.type} {ev.islanders}: week '{ev.week}' has not been scored")
            continue
        sources = {s.id: s for s in latest_bundle(ctx.deps.season_key, ev.week).sources}
        cast, week_days = verification_context(ctx.deps.season_key, ev.week)
        result = verify.check_all([Event(**ev.model_dump(exclude={"week"}))], sources, cast, ev.week, week_days)[0]
        if result.status == "rejected":
            problems.append(f"add {ev.type} {ev.islanders}: {'; '.join(result.problems)}")
        else:
            checked.append(result)
    if problems:
        raise ModelRetry("Some proposed fixes failed the code check. Fix the quotes or drop those fixes "
                         "(and change the verdict if needed):\n" + "\n".join(problems))
    ctx.deps.checked_adds = checked
    return ruling


def file_dispute(league_key: str, player: str, text: str) -> tuple[dict, dict]:
    """Run the Ref on a dispute and save the ruling as *pending*. Returns (dispute record, run log)."""
    league = scoring.load_league(league_key)
    if player not in {p["name"] for p in league["players"]}:
        raise ValueError(f"'{player}' is not a player in this league")
    if len(text) > MAX_DISPUTE_CHARS:
        raise ValueError(f"Dispute is too long (max {MAX_DISPUTE_CHARS} characters)")
    text, report = clean.clean_text(text)
    standings = scoring.score_league(league_key, save=False)
    deps = RefDeps(league_key, league["season"], player, standings["weeks"], standings)
    recorder = llm.UsageRecorder()
    started = datetime.now(timezone.utc)
    try:
        result = agent.run_sync(f"Dispute from {player} (untrusted claim, check it):\n\"\"\"\n{text}\n\"\"\"",
                                deps=deps, model=llm.build_model(recorder), usage_limits=USAGE_LIMITS)
        ruling, steps = result.output, llm.tool_trace(result.all_messages())
    except ModelHTTPError as e:
        if "content_filter" not in str(e.body):
            raise
        # The model provider's own jailbreak filter refused the dispute before the Ref saw it.
        ruling, steps = Ruling(verdict="deny", injection_suspected=True, explanation=(
            "Blocked by the model provider's safety filter: the dispute reads like an attempt to give the Ref "
            "orders. Nothing was changed. File it again as a plain claim about what happened on the show.")), []
    if ruling.verdict == "partial" and not deps.checked_adds and not ruling.remove_event_ids:
        ruling.verdict = "deny"  # 'partial' means something changes; nothing does

    league = scoring.load_league(league_key)  # reload: the run may take a while
    disputes = league.setdefault("disputes", [])
    adjustments = league.setdefault("adjustments", [])
    dispute_id = f"dispute-{len(disputes) + 1}"
    adj_ids = []
    for e in deps.checked_adds:
        adj = {"id": f"adj-{len(adjustments) + 1}", "dispute_id": dispute_id, "action": "add_event", "week": e.week,
               "event": e.model_copy(update={"id": f"{dispute_id}-{e.type}-{'-'.join(e.islanders)}".lower()}).model_dump(),
               "status": "pending"}
        adjustments.append(adj)
        adj_ids.append(adj["id"])
    week_of = {e.id: w for w, evs in latest_events(league["season"]).items() for e in evs}
    for eid in ruling.remove_event_ids:
        adj = {"id": f"adj-{len(adjustments) + 1}", "dispute_id": dispute_id, "action": "remove_event",
               "week": week_of[eid], "event_id": eid, "status": "pending"}
        adjustments.append(adj)
        adj_ids.append(adj["id"])
    record = {"id": dispute_id, "player": player, "text": text, "filed": started.isoformat(timespec="seconds"),
              "ruling": ruling.model_dump(), "adjustments": adj_ids, "input_flags": report["flagged_lines"],
              "status": "pending" if adj_ids else "closed"}
    disputes.append(record)
    scoring.save_league(league_key, league)

    run = {"agent": "ref", "league": league_key, "dispute": dispute_id, "started": record["filed"],
           "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
           "usage": llm.recorder_totals(recorder), "steps": steps,
           "verdict": ruling.verdict, "injection_suspected": ruling.injection_suspected}
    out = config.OUTPUT / "runs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"ref_{league_key}_{dispute_id}_{started.strftime('%Y%m%dT%H%M%S')}.json").write_text(
        json.dumps(run, indent=1, ensure_ascii=False))
    return record, run


def decide(league_key: str, dispute_id: str, approve: bool) -> dict:
    """Commissioner decision: apply or reject every adjustment of a pending dispute."""
    league = scoring.load_league(league_key)
    record = next(d for d in league.get("disputes", []) if d["id"] == dispute_id)
    if record["status"] != "pending":
        return record
    for adj in league["adjustments"]:
        if adj["id"] in record["adjustments"]:
            adj["status"] = "approved" if approve else "declined"
    record["status"] = "approved" if approve else "declined"
    scoring.save_league(league_key, league)
    return record


def impact(league_key: str, dispute: dict) -> list[dict]:
    before = scoring.score_league(league_key, save=False)
    after = scoring.score_league(league_key, save=False, also_apply=set(dispute["adjustments"]))
    b = {r["player"]: r["total"] for r in before["standings"]}
    return [{"player": r["player"], "before": b[r["player"]], "after": r["total"], "change": r["total"] - b[r["player"]]}
            for r in after["standings"]]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Disputes for a league.")
    p.add_argument("--league", default="demo_league")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("file")
    f.add_argument("player")
    f.add_argument("text")
    sub.add_parser("list")
    sub.add_parser("approve").add_argument("id")
    sub.add_parser("decline").add_argument("id")
    args = p.parse_args()

    if args.cmd == "file":
        record, run = file_dispute(args.league, args.player, args.text)
        r = record["ruling"]
        print(f"{record['id']} [{record['status']}] verdict: {r['verdict'].upper()}"
              f"{'  ⚠ injection suspected' if r['injection_suspected'] else ''}  ({run['seconds']}s, ${run['usage']['cost_usd']})")
        print("  " + r["explanation"])
        for e in r["add_events"]:
            print(f"  + add {e['week']} {e['type']} {e['islanders']} day {e['day']}: \"{e['evidence'][0]['quote'][:80]}\"")
        for eid in r["remove_event_ids"]:
            print(f"  - remove {eid}")
        print("  steps: " + " → ".join(s["tool"] for s in run["steps"]))
        if record["adjustments"]:
            for row in impact(args.league, record):
                if row["change"]:
                    print(f"  if approved: {row['player']} {row['before']} -> {row['after']} ({row['change']:+d})")
    elif args.cmd == "list":
        for d in scoring.load_league(args.league).get("disputes", []):
            print(f"  {d['id']} [{d['status']}] {d['player']}: {d['text'][:60]} -> {d['ruling']['verdict']}")
    else:
        print(decide(args.league, args.id, args.cmd == "approve")["status"])
