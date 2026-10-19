"""Rulesmith agent: plain-English house rules -> structured rules that wait for commissioner approval.

Usage:
    python -m backend.agents.rulesmith --league demo_league propose "Steals are worth 5 extra points. ..."
    python -m backend.agents.rulesmith --league demo_league list
    python -m backend.agents.rulesmith --league demo_league approve house-1 house-2
    python -m backend.agents.rulesmith --league demo_league decline house-3
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import json

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.usage import UsageLimits

from backend import config, llm, scoring
from backend.models import Rule, RuleProposal

USAGE_LIMITS = UsageLimits(request_limit=3, total_tokens_limit=40_000)
MODEL_SETTINGS = OpenAIResponsesModelSettings(max_tokens=6_000, openai_prompt_cache_key="villa-rulesmith")
MAX_REQUEST_CHARS = 2_000


@dataclass
class RuleDeps:
    standard: list[Rule]
    names: set[str]  # islander and player names: rules may not single anyone out


agent = Agent(deps_type=RuleDeps, output_type=RuleProposal, retries=2, model_settings=MODEL_SETTINGS,
              instructions=(config.PROMPTS / "rulesmith.md").read_text())


@agent.instructions
def standard_table(ctx: RunContext[RuleDeps]) -> str:
    rows = "\n".join(f"- {r.id}: {r.label} ({r.event_type}) {r.points:+d}" for r in ctx.deps.standard)
    return f"Standard rules already in force:\n{rows}"


@agent.output_validator
def fair_and_valid(ctx: RunContext[RuleDeps], proposal: RuleProposal) -> RuleProposal:
    standard_ids = {r.id for r in ctx.deps.standard}
    problems = []
    for r in proposal.rules:
        if r.replaces and r.replaces not in standard_ids:
            problems.append(f"'{r.label}': replaces unknown rule '{r.replaces}'")
        for k in r.quote_keywords:
            if len(k) > 30 or k.lower() in {n.lower() for n in ctx.deps.names}:
                problems.append(f"'{r.label}': keyword '{k}' is a name or too long; rules must apply to everyone")
    if problems:
        raise ModelRetry("Fix these rules (or move them to unsupported):\n" + "\n".join(problems))
    return proposal


def _names(league: dict) -> set[str]:
    names = {p["name"] for p in league["players"]}
    names |= {slot["islander"] for p in league["players"] for slot in p["roster"]}
    return names


def propose(league_key: str, text: str) -> tuple[list[Rule], RuleProposal, dict]:
    """Draft rules from the commissioner's text and save them as *pending*. Returns (new rules, raw proposal, run log)."""
    if len(text) > MAX_REQUEST_CHARS:
        raise ValueError(f"House rules request is too long (max {MAX_REQUEST_CHARS} characters).")
    league = scoring.load_league(league_key)
    standard = [Rule(**r) for r in json.loads((config.DATA / "rules" / league["rules_file"]).read_text())["rules"]]
    recorder = llm.UsageRecorder()
    started = datetime.now(timezone.utc)
    result = agent.run_sync(f"Commissioner's house rules:\n\"\"\"\n{text}\n\"\"\"",
                            deps=RuleDeps(standard, _names(league)), model=llm.build_model(recorder),
                            usage_limits=USAGE_LIMITS)
    existing = league.setdefault("house_rules", [])
    new = []
    for draft in result.output.rules:
        rule = Rule(id=f"house-{len(existing) + 1}", source="house", status="pending", **draft.model_dump())
        existing.append(rule.model_dump())
        new.append(rule)
    scoring.save_league(league_key, league)
    run = {"agent": "rulesmith", "league": league_key, "started": started.isoformat(timespec="seconds"),
           "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
           "usage": llm.recorder_totals(recorder), "request": text,
           "proposed": [r.id for r in new], "unsupported": [u.model_dump() for u in result.output.unsupported]}
    out = config.OUTPUT / "runs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"rulesmith_{league_key}_{started.strftime('%Y%m%dT%H%M%S')}.json").write_text(
        json.dumps(run, indent=1, ensure_ascii=False))
    return new, result.output, run


def set_status(league_key: str, rule_ids: list[str], status: str) -> list[str]:
    """Commissioner decision on pending rules. Returns the IDs that changed."""
    league = scoring.load_league(league_key)
    changed = []
    for r in league.get("house_rules", []):
        if r["id"] in rule_ids and r["status"] == "pending":
            r["status"] = status
            changed.append(r["id"])
    scoring.save_league(league_key, league)
    return changed


def impact(league_key: str, rule_ids: list[str]) -> tuple[list[dict], dict[str, int]]:
    """What-if for pending rules (nothing is saved): each player's point change, and events each rule matches."""
    before = scoring.score_league(league_key, save=False)
    after = scoring.score_league(league_key, save=False, also_approve=set(rule_ids))
    b = {row["player"]: row["total"] for row in before["standings"]}
    return [{"player": row["player"], "before": b[row["player"]], "after": row["total"],
             "change": row["total"] - b[row["player"]]} for row in after["standings"]], \
        {rid: len({l["event_id"] for l in after["ledger"] if l["rule_id"] == rid}) for rid in rule_ids}


def describe(rule: dict) -> str:
    extra = []
    if rule.get("quote_keywords"):
        extra.append(f"quote has {rule['quote_keywords']}")
    if rule.get("min_day") or rule.get("max_day"):
        extra.append(f"days {rule.get('min_day') or 1}-{rule.get('max_day') or 'end'}")
    if rule.get("replaces"):
        extra.append(f"replaces {rule['replaces']}")
    if rule.get("applies_to", "islanders") != "islanders":
        extra.append(f"applies to {rule['applies_to']}")
    return (f"{rule['id']} [{rule['status']}] {rule['label']}: {rule['event_type']} {rule['points']:+d}"
            + (f" ({'; '.join(extra)})" if extra else "") + f"\n      from: \"{rule['original_text']}\"")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="House rules for a league.")
    p.add_argument("--league", default="demo_league")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("propose").add_argument("text")
    sub.add_parser("list")
    sub.add_parser("approve").add_argument("ids", nargs="+")
    sub.add_parser("decline").add_argument("ids", nargs="+")
    args = p.parse_args()

    if args.cmd == "propose":
        new, proposal, run = propose(args.league, args.text)
        print(f"Drafted {len(new)} rule(s) for approval in {run['seconds']}s, ${run['usage']['cost_usd']}:")
        for r in new:
            print("  " + describe(r.model_dump()))
        for u in proposal.unsupported:
            print(f"  ✗ can't score \"{u.original_text}\": {u.reason}")
        if new:
            rows, matches = impact(args.league, [r.id for r in new])
            print("Impact if approved:")
            for row in rows:
                print(f"  {row['player']:<8} {row['before']:>4} -> {row['after']:>4} ({row['change']:+d})")
            for rid, n in matches.items():
                print(f"  {rid} matches {n} event(s) so far" + ("  <- check this rule" if n == 0 else ""))
    elif args.cmd == "list":
        for r in scoring.load_league(args.league).get("house_rules", []):
            print("  " + describe(r))
    else:
        status = "approved" if args.cmd == "approve" else "declined"
        print(f"{status}: {set_status(args.league, args.ids, status) or 'nothing (only pending rules can change)'}")
