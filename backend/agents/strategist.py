"""Villa Strategist: a coach agent that helps one player draft and make weekly moves (or makes them on autopilot).

It only sees the league up to "now" (season_play.horizon) through read-only tools. Code checks every
suggestion against the league rules and for spoilers before anyone sees it, and autopilot can only apply
moves that pass those same checks.

Usage:
    python -m backend.agents.strategist --league play_my_villa_league
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import argparse
import json
import re

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits

from backend import config, llm, scoring, season_play as sp
from backend.models import DraftAdvice, FinaleAdvice, MoveAdvice

USAGE_LIMITS = UsageLimits(request_limit=8, tool_calls_limit=12, total_tokens_limit=80_000)
MODEL_SETTINGS = OpenAIResponsesModelSettings(max_tokens=5_000, openai_prompt_cache_key="villa-strategist")
LIST_LIMIT = 14


@dataclass
class CoachDeps:
    key: str
    league: dict
    player: str
    facts: dict = field(default_factory=dict)
    future: list[str] = field(default_factory=list)


tools = FunctionToolset()


def _brief(f: dict, recent: int = 3) -> dict:
    return {"name": f["name"], "points": f["points"], "in_villa": f["in_villa"], "partner": f["partner"],
            "recent": [{k: e[k] for k in ("week", "day", "type", "with", "quote")} for e in f["events"][-recent:]]}


@tools.tool
def my_team(ctx: RunContext[CoachDeps]) -> dict:
    """Your roster for next week with points so far, couple status and recent events."""
    d = ctx.deps
    roster = sp.active_roster(sp._player(d.league, d.player), sp.next_week(d.league))
    return {"roster": [_brief(d.facts.get(n, {"name": n, "points": 0, "in_villa": False, "partner": None, "events": []}))
                       for n in roster],
            "roster_max": d.league["settings"]["roster_max"],
            "moves_left_this_week": d.league["settings"]["moves_per_week"] - sp.moves_this_window(d.league, d.player)}


@tools.tool
def free_agents(ctx: RunContext[CoachDeps]) -> list[dict]:
    """Islanders in the villa right now that nobody has, best scorers first."""
    return [_brief(f, recent=2) for f in sp.free_agents(ctx.deps.league)[:LIST_LIMIT]]


@tools.tool
def islander_report(ctx: RunContext[CoachDeps], name: str) -> dict:
    """Everything that has happened to one islander so far, with quotes."""
    f = ctx.deps.facts.get(name)
    if not f:
        return {"error": f"No events for '{name}' so far"}
    return {**_brief(f, recent=12), "owned_by": sp.owners(ctx.deps.league, sp.next_week(ctx.deps.league)).get(name)}


@tools.tool
def standings(ctx: RunContext[CoachDeps]) -> list[dict]:
    """League standings so far and each player's current roster."""
    d = ctx.deps
    rows = sp._standings(d.key, d.league)
    return [{"player": r["player"], "total": r["total"],
             "roster": sp.active_roster(sp._player(d.league, r["player"]), sp.next_week(d.league))} for r in rows]


@tools.tool
def scoring_rules(ctx: RunContext[CoachDeps]) -> list[str]:
    """The point table in force for this league."""
    return [f"{r.label}: {r.points:+d}" for r in scoring.load_rules(ctx.deps.league)]


def _instructions(ctx: RunContext[CoachDeps]) -> str:
    d = ctx.deps
    week, day = sp.horizon(d.league)
    now = f"before Week 1 ends (through Day {day})" if day else f"after Week {week}"
    return f"You coach {d.player}. It is now {now}. Season: Love Island USA season 8."


draft_agent = Agent(deps_type=CoachDeps, output_type=DraftAdvice, toolsets=[tools], retries=2,
                    model_settings=MODEL_SETTINGS, instructions=[(config.PROMPTS / "strategist.md").read_text(), _instructions])
move_agent = Agent(deps_type=CoachDeps, output_type=MoveAdvice, toolsets=[tools], retries=2,
                   model_settings=MODEL_SETTINGS, instructions=[(config.PROMPTS / "strategist.md").read_text(), _instructions])


FINALE_INSTRUCTIONS = """## The finale
The season is over and the player is one of the two finalists at the fire pit. Each finalist seals an envelope:
**share** the pot or **take it all**. Both share: 50/50. One takes: the taker gets everything. Both take: nobody gets anything.
You can NOT see the other envelope; nobody can. Use `finale_info` for the pot and what the opponent did all season,
then recommend share or take with an honest two-or-three-sentence reason (the trade-off, and your read on the opponent).
It's a game between friends: be playful, never mean."""

finale_tools = FunctionToolset()


@finale_tools.tool
def finale_info(ctx: RunContext[CoachDeps]) -> dict:
    """The pot, the rules, the two finalists' totals, and the opponent's season (their moves). Never their envelope."""
    d = ctx.deps
    f = d.league.get("finale") or {}
    opponent = next((p["player"] for p in f.get("finalists", []) if p["player"] != d.player), None)
    moves = [m for m in d.league.get("moves", []) if m["player"] == opponent]
    return {"pot": f.get("prize"), "finalists": f.get("finalists"), "you": d.player, "opponent": opponent,
            "opponent_is_a_bot": any(p["name"] == opponent and p.get("bot") for p in d.league["players"]),
            "opponent_moves_this_season": len(moves),
            "opponent_recent_moves": [{"add": m["add"], "drop": m["drop"], "reason": m["reason"][:120]} for m in moves[-3:]]}


finale_agent = Agent(deps_type=CoachDeps, output_type=FinaleAdvice, toolsets=[tools, finale_tools], retries=2,
                     model_settings=MODEL_SETTINGS,
                     instructions=[(config.PROMPTS / "strategist.md").read_text(), FINALE_INSTRUCTIONS, _instructions])


def blind_copy(league: dict) -> dict:
    """The league as the coach may see it: every sealed envelope removed, so it cannot peek."""
    blind = json.loads(json.dumps(league))
    if blind.get("finale"):
        blind["finale"]["choices"] = {}
        blind["finale"].pop("by", None)
    return blind


def advise_finale(key: str) -> dict:
    """Share or take? Only for you, only while your envelope is still open."""
    league = sp.load(key)
    f = league.get("finale")
    you = league["you"]
    if not f or f.get("revealed"):
        raise sp.MoveError("There's no envelope to decide on right now")
    if you not in [p["player"] for p in f["finalists"]]:
        raise sp.MoveError("You're not one of the finalists this time")
    if you in f["choices"]:
        raise sp.MoveError("Your envelope is already sealed")
    blind = blind_copy(league)
    deps = CoachDeps(key, blind, you, sp.islander_facts(blind), sp.future_names(blind))
    recorder = llm.UsageRecorder()
    started = datetime.now(timezone.utc)
    result = finale_agent.run_sync(f"{you} is in the final. Share or take it all?", deps=deps,
                                   model=llm.build_model(recorder), usage_limits=USAGE_LIMITS)
    steps = [st["tool"] for st in llm.tool_trace(result.all_messages())]
    run = _log("finale", key, recorder, started, {"steps": steps, "advice": result.output.model_dump()})
    return {"kind": "finale", "advice": result.output.model_dump(), "cost_usd": run["usage"]["cost_usd"],
            "seconds": run["seconds"], "steps": steps}


def _spoilers(d: CoachDeps, texts: list[str]) -> list[str]:
    blob = " ".join(texts)
    out = [f"'{n}' hasn't entered the villa yet; you can't know about them" for n in d.future
           if re.search(rf"\b{re.escape(n)}\b", blob)]
    if re.search(r"\b(won (the )?(season|show)|crowned|finale|wins? it all|will win)\b", blob, re.I):
        out.append("don't predict or mention the season's winner or finale")
    return out


@draft_agent.output_validator
def draft_ok(ctx: RunContext[CoachDeps], advice: DraftAdvice) -> DraftAdvice:
    pool = {f["name"] for f in sp.draft_pool(ctx.deps.league)}
    problems = [f"{p.islander} isn't available to draft" for p in advice.picks if p.islander not in pool]
    problems += _spoilers(ctx.deps, [advice.summary] + [p.reason for p in advice.picks])
    if problems:
        raise ModelRetry("Fix these:\n" + "\n".join(f"- {p}" for p in problems))
    return advice


@move_agent.output_validator
def moves_ok(ctx: RunContext[CoachDeps], advice: MoveAdvice) -> MoveAdvice:
    d = ctx.deps
    trial = json.loads(json.dumps(d.league))  # check moves in order on a scratch copy
    problems = []
    for m in advice.moves:
        issues = sp.check_move(trial, d.player, m.add, m.drop)
        if issues:
            problems.append(f"add {m.add} / drop {m.drop}: {'; '.join(issues)}")
        else:
            sp.apply_move(trial, d.player, m.add, m.drop, by="check")
    problems += _spoilers(d, [advice.summary] + [m.reason for m in advice.moves])
    if problems:
        raise ModelRetry("These moves break the league rules or spoil the season. Fix or remove them:\n"
                         + "\n".join(f"- {p}" for p in problems))
    return advice


def _log(kind: str, key: str, recorder, started, extra: dict) -> dict:
    run = {"agent": "strategist", "kind": kind, "league": key, "started": started.isoformat(timespec="seconds"),
           "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
           "usage": llm.recorder_totals(recorder), **extra}
    out = config.OUTPUT / "runs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"strategist_{key}_{kind}_{started.strftime('%Y%m%dT%H%M%S')}.json").write_text(json.dumps(run, indent=1))
    return run


def advise(key: str, league: dict | None = None) -> dict:
    """Draft advice if it's the draft, move advice otherwise. Returns {kind, advice, cost_usd, seconds, steps}."""
    league = league or sp.load(key)
    player = league["you"]
    deps = CoachDeps(key, league, player, sp.islander_facts(league), sp.future_names(league))
    recorder = llm.UsageRecorder()
    started = datetime.now(timezone.utc)
    if not league["draft"]["done"]:
        if sp.draft_turn(league) != player:
            raise sp.MoveError("It isn't your pick yet")
        kind, agent = "draft", draft_agent
        prompt = (f"It's {player}'s pick (pick {len(league['draft']['picks']) + 1}). Look at the pool and "
                  f"{player}'s roster, then rank the best picks.")
    else:
        kind, agent = "moves", move_agent
        prompt = f"Week {league['current_week']} just ended. Should {player} make a move before next week?"
    result = agent.run_sync(prompt, deps=deps, model=llm.build_model(recorder), usage_limits=USAGE_LIMITS)
    steps = [s["tool"] for s in llm.tool_trace(result.all_messages())]
    run = _log(kind, key, recorder, started, {"steps": steps, "advice": result.output.model_dump()})
    return {"kind": kind, "advice": result.output.model_dump(), "cost_usd": run["usage"]["cost_usd"],
            "seconds": run["seconds"], "steps": steps}


def autopilot(key: str, league: dict) -> list[dict]:
    """Used by season_play.advance: ask for moves and apply the ones that still pass the rules."""
    out = advise(key, league)
    applied = []
    for m in out["advice"]["moves"]:
        try:
            applied.append(sp.apply_move(league, league["you"], m["add"], m["drop"], by="autopilot", reason=m["reason"]))
        except sp.MoveError:
            continue
    return applied


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ask the Villa Strategist for advice.")
    p.add_argument("--league", required=True)
    args = p.parse_args()
    print(json.dumps(advise(args.league), indent=1))
