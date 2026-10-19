"""Scorekeeper: verified events + approved rules -> points ledger -> standings. Plain code, no model.

Usage:
    python -m backend.scoring --league demo_league
"""
from collections import defaultdict
import argparse
import json

from backend import config, verify
from backend.agents.recapper import latest_events
from backend.agents.scout import seasons
from backend.models import CheckedEvent, LedgerLine, Rule
from backend.sources import cast as cast_source


def league_path(league_key: str):
    return config.DATA / "leagues" / f"{league_key}.json"


def load_league(league_key: str) -> dict:
    return json.loads(league_path(league_key).read_text())


def save_league(league_key: str, league: dict) -> None:
    league_path(league_key).write_text(json.dumps(league, indent=1, ensure_ascii=False) + "\n")


def load_rules(league: dict, also_approve: set[str] = frozenset()) -> list[Rule]:
    """Standard table plus approved house rules; an approved house rule with `replaces` switches that standard rule off.

    also_approve treats those pending rules as approved, for a what-if preview (nothing is saved).
    """
    standard = [Rule(**r) for r in json.loads((config.DATA / "rules" / league["rules_file"]).read_text())["rules"]]
    house = [Rule(**r) for r in league.get("house_rules", [])]
    house = [r for r in house if r.status == "approved" or (r.status == "pending" and r.id in also_approve)]
    replaced = {r.replaces for r in house if r.replaces}
    return [r for r in standard if r.id not in replaced] + house


def _matches(rule: Rule, event: CheckedEvent) -> bool:
    if rule.event_type != event.type:
        return False
    if rule.min_day is not None and (event.day is None or event.day < rule.min_day):
        return False
    if rule.max_day is not None and (event.day is None or event.day > rule.max_day):
        return False
    if rule.quote_keywords:
        quotes = " ".join(verify.norm(ev.quote) for ev in event.evidence)
        if not any(verify.norm(k) in quotes for k in rule.quote_keywords):
            return False
    return True


def _receipt(rule: Rule, event: CheckedEvent):
    """The evidence quote to show for this rule: the one that contains the rule's keyword, if it has one."""
    for ev in event.evidence:
        if not rule.quote_keywords or any(verify.norm(k) in verify.norm(ev.quote) for k in rule.quote_keywords):
            return ev
    return event.evidence[0]


def survival_events(events_by_week: dict[str, list[CheckedEvent]]) -> dict[str, list[CheckedEvent]]:
    """A 'survived_week' event for everyone still in the villa when each week ends (from verified events only)."""
    in_villa: set[str] = set()
    out = {}
    for week, events in events_by_week.items():
        for e in sorted((e for e in events if e.status == "verified"), key=lambda e: e.day or 0):
            if e.type in ("entered_villa", "re_entered"):
                in_villa.update(e.islanders)
            elif e.type in ("dumped", "left_villa"):
                in_villa.difference_update(e.islanders)
        out[week] = [CheckedEvent(type="survived_week", islanders=[name], id=f"{week}-survived-{name}", week=week,
                                  status="verified",
                                  evidence=[{"source_id": "code", "quote": "still in the villa at the end of the week"}])
                     for name in sorted(in_villa)]
    return out


def ledger(events_by_week: dict[str, list[CheckedEvent]], rules: list[Rule]) -> list[LedgerLine]:
    lines = []
    survived = survival_events(events_by_week)
    for week, events in events_by_week.items():
        for event in [e for e in events if e.status == "verified"] + survived[week]:
            for rule in rules:
                if not _matches(rule, event):
                    continue
                who = {"islanders": event.islanders, "others": event.others,
                       "both": event.islanders + event.others}[rule.applies_to]
                ev = _receipt(rule, event)
                for name in who:
                    lines.append(LedgerLine(week=week, event_id=event.id, islander=name, rule_id=rule.id,
                                            label=rule.label, points=rule.points, quote=ev.quote,
                                            source_id=ev.source_id))
    return lines


def check_rosters(league: dict, cast: verify.Cast) -> list[str]:
    problems = []
    for player in league["players"]:
        for slot in player["roster"]:
            if cast.canonical(slot["islander"]) is None:
                problems.append(f"{player['name']}: '{slot['islander']}' is not in the cast")
    return problems


def slot_active(slot: dict, week: str | int) -> bool:
    """A roster slot counts from its `from_week` (pickup) through its `until_week` (drop), inclusive."""
    n = week if isinstance(week, int) else week_num(week)
    return slot.get("from_week", 1) <= n <= slot.get("until_week", 10_000)


def standings(league: dict, lines: list[LedgerLine], weeks: list[str]) -> list[dict]:
    """[{player, total, by_week, by_islander}] sorted best first. Slots only count while active (slot_active)."""
    points = defaultdict(lambda: defaultdict(int))  # islander -> week -> points
    for line in lines:
        points[line.islander][line.week] += line.points
    table = []
    for player in league["players"]:
        by_week = {w: 0 for w in weeks}
        by_islander = {}
        for slot in player["roster"]:
            counted = {w: p for w, p in points[slot["islander"]].items() if slot_active(slot, w)}
            by_islander[slot["islander"]] = by_islander.get(slot["islander"], 0) + sum(counted.values())
            for w, p in counted.items():
                by_week[w] += p
        table.append({"player": player["name"], "total": sum(by_week.values()), "by_week": by_week,
                      "by_islander": by_islander})
    return sorted(table, key=lambda r: -r["total"])


def week_num(week: str) -> int:
    return int(week.split()[-1])


def apply_adjustments(events_by_week: dict[str, list[CheckedEvent]], league: dict,
                      also_apply: set[str] = frozenset()) -> dict[str, list[CheckedEvent]]:
    """Approved Ref rulings: drop events by ID and add events the code already verified."""
    out = {w: list(evs) for w, evs in events_by_week.items()}
    for adj in league.get("adjustments", []):
        if not (adj["status"] == "approved" or (adj["status"] == "pending" and adj["id"] in also_apply)):
            continue
        week = adj["week"]
        if week not in out:
            continue
        if adj["action"] == "remove_event":
            out[week] = [e for e in out[week] if e.id != adj["event_id"]]
        elif adj["action"] == "add_event":
            out[week].append(CheckedEvent(**adj["event"]))
    return out


def score_league(league_key: str, save: bool = True, also_approve: set[str] = frozenset(),
                 up_to_week: int | None = None, also_apply: set[str] = frozenset()) -> dict:
    """Score a league. up_to_week stops at that week (spoiler-safe); also_* preview pending rules/adjustments."""
    league = load_league(league_key)
    season = seasons()[league["season"]]
    cast = verify.Cast(cast_source.cast(season["pages"]["wikipedia"]))
    problems = check_rosters(league, cast)
    if problems:
        raise ValueError("; ".join(problems))
    events = latest_events(league["season"])
    if up_to_week is not None:
        events = {w: e for w, e in events.items() if week_num(w) <= up_to_week}
    events = apply_adjustments(events, league, also_apply)
    rules = load_rules(league, also_approve)
    lines = ledger(events, rules)
    result = {"league": league["name"], "weeks": list(events), "rules": [r.model_dump() for r in rules],
              "standings": standings(league, lines, list(events)), "ledger": [l.model_dump() for l in lines]}
    if save and up_to_week is None and not also_approve and not also_apply:
        (config.OUTPUT / f"standings_{league_key}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Score a league from verified events.")
    p.add_argument("--league", default="demo_league")
    args = p.parse_args()
    r = score_league(args.league)
    print(f"{r['league']} — {', '.join(r['weeks'])}  ({len(r['ledger'])} ledger lines, {len(r['rules'])} rules)")
    for i, row in enumerate(r["standings"], 1):
        weeks = "  ".join(f"{p:+d}" for p in row["by_week"].values())
        print(f" {i}. {row['player']:<8} {row['total']:>4}   weeks: {weeks}   {row['by_islander']}")
