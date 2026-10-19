"""Recapper agent: turns one week's sources into events with receipts, then code verifies every receipt.

Usage:
    python -m backend.agents.recapper --week 2                 # uses the latest Scout bundle for that week
    python -m backend.agents.recapper --week 2 --no-self-correct
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import json

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.usage import UsageLimits

from backend import config, llm, verify
from backend.agents.scout import seasons
from backend.models import CheckedEvent, RecapDraft, SourceBundle
from backend.sources import cast as cast_source, wiki

USAGE_LIMITS = UsageLimits(request_limit=4, total_tokens_limit=120_000)
MODEL_SETTINGS = OpenAIResponsesModelSettings(max_tokens=12_000, openai_prompt_cache_key="villa-recapper")
SELF_CORRECT_ROUNDS = 1


@dataclass
class RecapDeps:
    bundle: SourceBundle
    cast: verify.Cast
    week_days: tuple[int, int] | None
    self_correct: bool
    rounds: int = 0
    first_draft_rejections: int | None = None


agent = Agent(
    deps_type=RecapDeps,
    output_type=RecapDraft,
    instructions=(config.PROMPTS / "recapper.md").read_text(),
    model_settings=MODEL_SETTINGS,
    retries=SELF_CORRECT_ROUNDS + 1,
)


@agent.instructions
def cast_list(ctx: RunContext[RecapDeps]) -> str:
    # Same for every week of a season, so it stays in the cached prefix.
    return "Cast list (first names to use): " + ", ".join(ctx.deps.cast.names())


@agent.output_validator
def receipts_hold_up(ctx: RunContext[RecapDeps], draft: RecapDraft) -> RecapDraft:
    """Run the code checks; send failures back once so the model can fix or drop them."""
    sources = {s.id: s for s in ctx.deps.bundle.sources}
    checked = verify.check_all(draft.events, sources, ctx.deps.cast, ctx.deps.bundle.week, ctx.deps.week_days)
    bad = [(i, e) for i, e in enumerate(checked, 1) if e.status == "rejected"]
    if ctx.deps.first_draft_rejections is None:
        ctx.deps.first_draft_rejections = len(bad)
    if bad and ctx.deps.self_correct and ctx.deps.rounds < SELF_CORRECT_ROUNDS:
        ctx.deps.rounds += 1
        lines = [f"- {e.type} {e.islanders} (day {e.day}): {'; '.join(e.problems)}" for _, e in bad]
        raise ModelRetry("These events failed the receipt check. Return the FULL event list again: fix each "
                         "one by quoting the exact sentence from the source, or drop it if no source states it.\n"
                         + "\n".join(lines))
    return draft


def format_sources(bundle: SourceBundle) -> str:
    parts = [f"Week: {bundle.week} (episodes {', '.join(bundle.episodes)})"]
    for s in bundle.sources:
        head = f"### {s.id} [{s.kind}] {s.title}" + (f" ({s.outlet}, {s.published})" if s.outlet else "")
        parts.append(f"{head}\n{s.text}")
    return "\n\n".join(parts)


def latest_bundle(season_key: str, week: str) -> SourceBundle:
    slug = week.lower().replace(" ", "")
    runs = sorted((config.OUTPUT / "runs").glob(f"scout_{season_key}_{slug}_*.json"))
    if not runs:
        raise FileNotFoundError(f"No Scout run for {season_key} {week}. Run the Scout first.")
    return SourceBundle(**json.loads(runs[-1].read_text())["bundle"])


def latest_events(season_key: str) -> dict[str, list[CheckedEvent]]:
    """{week: events} from the newest self-corrected Recapper run of each week, in week order."""
    by_week = {}
    for f in sorted((config.OUTPUT / "runs").glob(f"recap_{season_key}_*.json")):
        data = json.loads(f.read_text())
        if data["run"]["self_correct"]:
            by_week[data["run"]["week"]] = [CheckedEvent(**e) for e in data["events"]]
    return {w: by_week[w] for w in sorted(by_week, key=lambda w: int(w.split()[-1]))}


def verification_context(season_key: str, week: str) -> tuple[verify.Cast, tuple[int, int] | None]:
    """The cast and the week's day range: what the code needs to check an event."""
    page = seasons()[season_key]["pages"]["wikipedia"]
    return verify.Cast(cast_source.cast(page)), verify.week_day_range(wiki.episode_guide("wikipedia", page), week)


def run_recapper(season_key: str, bundle: SourceBundle, self_correct: bool = True,
                 save: bool = True) -> tuple[list[CheckedEvent], dict]:
    """Recap one week. save=False (safety tests) keeps the run out of output/runs, so it never feeds scoring."""
    cast, week_days = verification_context(season_key, bundle.week)
    deps = RecapDeps(bundle, cast, week_days, self_correct)
    recorder = llm.UsageRecorder()
    started = datetime.now(timezone.utc)
    result = agent.run_sync(format_sources(bundle), deps=deps, model=llm.build_model(recorder),
                            usage_limits=USAGE_LIMITS)

    # The final word is always the code check, whatever the model returned.
    events = verify.check_all(result.output.events, {s.id: s for s in bundle.sources}, cast, bundle.week, week_days)
    verified = [e for e in events if e.status == "verified"]
    run = {
        "agent": "recapper", "season": season_key, "week": bundle.week, "mode": config.SOURCE_MODE,
        "self_correct": self_correct, "started": started.isoformat(timespec="seconds"),
        "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        "usage": llm.recorder_totals(recorder),
        "events_proposed": len(result.output.events), "events_verified": len(verified),
        "events_rejected": len(events) - len(verified),
        "first_draft_rejections": deps.first_draft_rejections, "self_correct_rounds": deps.rounds,
    }
    if not save:
        return events, run
    out = config.OUTPUT / "runs"
    out.mkdir(parents=True, exist_ok=True)
    slug = bundle.week.lower().replace(" ", "")
    (out / f"recap_{season_key}_{slug}_{started.strftime('%Y%m%dT%H%M%S')}.json").write_text(json.dumps(
        {"run": run, "events": [e.model_dump() for e in events]}, indent=1, ensure_ascii=False))
    return events, run


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Turn one week's Scout sources into verified events.")
    p.add_argument("--season", default="love_island_usa_s8", choices=list(seasons()))
    p.add_argument("--week", default="1")
    p.add_argument("--no-self-correct", action="store_true")
    args = p.parse_args()
    events, run = run_recapper(args.season, latest_bundle(args.season, f"Week {args.week}"),
                               self_correct=not args.no_self_correct)
    u = run["usage"]
    print(f"{run['week']}: {run['events_verified']} verified, {run['events_rejected']} rejected "
          f"(first draft rejected {run['first_draft_rejections']}, {run['self_correct_rounds']} fix round) "
          f"in {run['seconds']}s | in {u['input_tokens']} (cached {u['cached_input_tokens']}) out {u['output_tokens']} "
          f"| ${u['cost_usd']}")
    for e in events:
        mark = "✓" if e.status == "verified" else "✗"
        print(f" {mark} {e.type:<15} {', '.join(e.islanders):<22} day {e.day}  x{e.corroborated_by}  {e.detail[:30]}"
              + (f"  <- {'; '.join(e.problems)}" if e.problems else ""))
