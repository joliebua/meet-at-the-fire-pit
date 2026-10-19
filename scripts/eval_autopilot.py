"""Does the Villa Strategist play well? Let it draft and run autopilot for whole seasons against the bots.

    VILLA_SOURCE_MODE=snapshot python scripts/eval_autopilot.py --seeds 1 2 3

For each seed (which sets the draft order and the bots' taste): the Strategist makes every one of "Coach"'s
draft picks (its top-ranked pick), autopilot handles every week, and the bots play their simple heuristic.
Results go to output/eval_autopilot.json (or --out). Throwaway leagues are deleted afterwards.
cost_usd counts only billed calls; identical repeat requests are answered free by Portkey's cache.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import sys

os.environ.setdefault("VILLA_SOURCE_MODE", "snapshot")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, scoring, season_play as sp, usage_log  # noqa: E402
from backend.agents import strategist  # noqa: E402

YOU = "Coach"


def play(seed: int) -> dict:
    key = sp.create(f"Autopilot eval {seed}", YOU, seed=seed)
    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    try:
        league = sp.load(key)
        picks = []
        while sp.draft_turn(league):
            if sp.draft_turn(league) == YOU:
                top = strategist.advise(key, league)["advice"]["picks"][0]
                picks.append(sp.make_pick(league, YOU, top["islander"], by="strategist", reason=top["reason"]))
            sp.run_bot_picks(league)
        league["settings"]["autopilot"] = True
        sp.save(key, league)
        weekly = []
        while sp.load(key)["current_week"] < sp.max_week(sp.load(key)):
            r = sp.advance(key, autopilot_fn=strategist.autopilot)
            weekly.append({"week": r["week"], "autopilot_moves": [(m["add"], m["drop"]) for m in r["autopilot_moves"]],
                           "rank": next(i for i, s in enumerate(r["standings"], 1) if s["player"] == YOU)})
        final = sp._standings(key, sp.load(key))
        new_runs = [r for r in usage_log.load_runs() if r["agent"] == "strategist" and f"_{key}_" in r["file"]
                    and r["file"].rsplit("_", 1)[-1].removesuffix(".json") >= started]  # this season's runs only
        return {"seed": seed, "draft_picks": [p["islander"] for p in picks],
                "final": [{"player": r["player"], "total": r["total"], "by_islander": r["by_islander"]} for r in final],
                "draft": sp.load(key)["draft"]["picks"],
                "rank": next(i for i, r in enumerate(final, 1) if r["player"] == YOU),
                "weekly": weekly, "moves": [m for m in sp.load(key)["moves"] if m["player"] == YOU],
                "strategist_runs": len(new_runs), "cost_usd": round(sum(r["cost_usd"] for r in new_runs), 6)}
    finally:
        scoring.league_path(key).unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    p.add_argument("--out", default="eval_autopilot.json")
    args = p.parse_args()
    results = []
    for seed in args.seeds:
        r = play(seed)
        results.append(r)
        print(f"seed {r['seed']}: rank {r['rank']}/4 · {[(f['player'], f['total']) for f in r['final']]} · "
              f"{r['strategist_runs']} Strategist runs · ${r['cost_usd']}")
    bot_avg = sum(f["total"] for r in results for f in r["final"] if f["player"] != YOU) / (3 * len(results))
    summary = {"seasons": len(results), "avg_rank": round(sum(r["rank"] for r in results) / len(results), 2),
               "wins": sum(r["rank"] == 1 for r in results),
               "avg_total": round(sum(next(f["total"] for f in r["final"] if f["player"] == YOU) for r in results) / len(results), 1),
               "bot_avg_total": round(bot_avg, 1), "cost_usd": round(sum(r["cost_usd"] for r in results), 6)}
    (config.OUTPUT / args.out).write_text(json.dumps({"summary": summary, "seasons": results}, indent=1))
    print(summary)


if __name__ == "__main__":
    main()
