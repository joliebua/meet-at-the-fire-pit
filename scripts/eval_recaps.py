"""Accuracy of verified Recapper events against the Wikipedia cast table (ground truth).

Checks the event types the table can prove: entered_villa, re_entered, dumped, left_villa, finalist, winner.
Usage:
    VILLA_SOURCE_MODE=snapshot python scripts/eval_recaps.py --season love_island_usa_s8
"""
from pathlib import Path
import argparse
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("VILLA_SOURCE_MODE", "snapshot")

from backend import config  # noqa: E402
from backend.agents.scout import seasons  # noqa: E402
from backend.sources import cast as cast_source  # noqa: E402

CHECKABLE = {"entered_villa", "re_entered", "dumped", "left_villa", "finalist", "winner"}
FINAL_STATUSES = {"Winner", "Runner-up", "Third place", "Fourth place"}


def truth(people: list[dict], last_day: int) -> dict[tuple, set]:
    """{(type, first_name): {days}} facts from the cast table (Amora was dumped twice)."""
    facts: dict[tuple, set] = {}
    add = lambda key, day: facts.setdefault(key, set()).add(day)
    for p in people:
        name = p["first_name"]
        for i, stint in enumerate(p["stints"]):
            add(("entered_villa" if i == 0 else "re_entered", name), stint["entered"])
            status = stint["status"]
            if status in ("Dumped", "Re-dumped"):
                add(("dumped", name), stint["exited"])
            elif status in ("Removed", "Walked"):
                add(("left_villa", name), stint["exited"])
            elif status in FINAL_STATUSES:
                add(("finalist", name), None)
                if status == "Winner":
                    add(("winner", name), last_day)
    return facts


def latest_recaps(season_key: str) -> list[dict]:
    """The newest self-corrected Recapper run per week."""
    by_week = {}
    for f in sorted((config.OUTPUT / "runs").glob(f"recap_{season_key}_*.json")):
        data = json.loads(f.read_text())
        if data["run"]["self_correct"]:
            by_week[data["run"]["week"]] = data
    return [by_week[w] for w in sorted(by_week)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--season", default="love_island_usa_s8")
    args = p.parse_args()
    season = seasons()[args.season]
    people = cast_source.cast(season["pages"]["wikipedia"])
    last_day = max(s["exited"] or 0 for person in people for s in person["stints"])
    facts = truth(people, last_day)

    predicted: dict[tuple, set] = {}
    for recap in latest_recaps(args.season):
        for e in recap["events"]:
            if e["status"] == "verified" and e["type"] in CHECKABLE:
                for name in e["islanders"]:
                    predicted.setdefault((e["type"], name), set()).add(e["day"])

    hits = [k for k in predicted if k in facts]
    false_pos = sorted(k for k in predicted if k not in facts)
    missed = sorted(k for k in facts if k not in predicted)
    # Every day the Recapper gave must be within one day of a day in the table.
    day_checked = [k for k in hits if None not in predicted[k] and None not in facts[k]]
    day_ok = [k for k in day_checked if all(any(abs(d - t) <= 1 for t in facts[k]) for d in predicted[k])]
    by_type = {}
    for t in sorted(CHECKABLE):
        tp = sum(1 for k in hits if k[0] == t)
        by_type[t] = {"truth": sum(1 for k in facts if k[0] == t), "predicted": sum(1 for k in predicted if k[0] == t),
                      "correct": tp}
    report = {
        "season": args.season, "weeks": [r["run"]["week"] for r in latest_recaps(args.season)],
        "precision": round(len(hits) / len(predicted), 3) if predicted else None,
        "recall": round(len(hits) / len(facts), 3) if facts else None,
        "day_within_1": f"{len(day_ok)}/{len(day_checked)}",
        "by_type": by_type,
        "false_positives": [f"{t} {n} (day {sorted(predicted[(t, n)], key=str)})" for t, n in false_pos],
        "missed": [f"{t} {n} (day {sorted(facts[(t, n)], key=str)})" for t, n in missed],
        "day_mismatches": [f"{t} {n}: said {sorted(predicted[(t, n)])}, table {sorted(facts[(t, n)])}"
                           for t, n in day_checked if (t, n) not in day_ok],
    }
    out = config.OUTPUT / "eval_recaps.json"
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
