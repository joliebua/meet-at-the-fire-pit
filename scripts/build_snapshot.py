"""Record a season's live sources into data/samples/<season>/ so the app can run offline.

Usage:
    python scripts/build_snapshot.py --season love_island_usa_s8 --weeks 1-5

It fetches every wiki section the app needs, then runs the Scout once per week with recording on,
so a later offline run can replay the same calls. Full news articles are never recorded.
"""
from pathlib import Path
import argparse
import json
import os
import sys

os.environ["VILLA_SOURCE_MODE"] = "live"
os.environ["VILLA_RECORD"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.scout import run_scout, seasons  # noqa: E402
from backend.sources import wiki  # noqa: E402
from backend.sources.store import snapshot_dir  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--season", default="love_island_usa_s8")
    p.add_argument("--weeks", default="1-5")
    args = p.parse_args()
    os.environ["VILLA_SNAPSHOT"] = args.season
    from backend import config
    config.SNAPSHOT = args.season

    season = seasons()[args.season]
    for name, page in season["pages"].items():
        wiki.search(name, page)
        for section in wiki.sections(name, page):
            wiki.raw_section(name, page, section)
    wiki.episode_guide("wikipedia", season["pages"]["wikipedia"])
    print("wiki pages recorded")

    first, last = (int(x) for x in args.weeks.split("-"))
    summary = []
    for n in range(first, last + 1):
        bundle, run = run_scout(args.season, f"Week {n}")
        summary.append({"week": bundle.week, "sources": len(bundle.sources),
                        "cost_usd": run["usage"]["total_cost_usd"], "steps": [s["tool"] for s in run["steps"]]})
        print(summary[-1])

    out = snapshot_dir(args.season)
    (out / "README.md").write_text(
        f"# Snapshot: {season['show']} season {season['season']}\n\n"
        "Recorded answers from the live sources (Wikipedia + Fandom MediaWiki API, Google News RSS headlines, "
        "OpenAI web search answers) so the app runs offline with `VILLA_SOURCE_MODE=snapshot`.\n\n"
        "- Wiki text is CC BY-SA (Wikipedia / Fandom contributors).\n"
        "- News items are headlines + links only; full articles are never saved.\n\n"
        f"Scout runs used to record it:\n\n```json\n{json.dumps(summary, indent=1)}\n```\n")


if __name__ == "__main__":
    main()
