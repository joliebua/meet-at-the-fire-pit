"""Play a season week by week: snake draft, bot friends, weekly reveals and roster moves. Plain code.

The league's `current_week` is "now": 0 means pre-season (the draft happens after Day 2), N means weeks
1..N have aired and been scored. Everything an agent or a bot sees is cut off at that horizon, so nobody
can use what happens later in the season.

Moves made while `current_week` is N take effect from week N+1 (pickups get from_week N+1, drops get
until_week N). Bots make their moves when the user plays the next week.
"""
from collections import defaultdict
from datetime import datetime, timezone
import json
import random
import re

from backend import config, scoring, verify
from backend.agents.recapper import latest_events
from backend.agents.scout import seasons
from backend.models import CheckedEvent
from backend.sources import cast as cast_source

BOT_NAMES = ["Maya", "Dev", "Priya"]
DEFAULT_SETTINGS = {"draft_rounds": 2, "roster_max": 4, "moves_per_week": 1, "draft_after_day": 2, "autopilot": False}


class MoveError(ValueError):
    pass


def slug(name: str) -> str:
    return "play_" + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "league")[:30]


def is_play(league: dict) -> bool:
    return league.get("mode") == "play"


# ---------------------------------------------------------------- horizon + facts

def max_week(league: dict) -> int:
    return max((scoring.week_num(w) for w in latest_events(league["season"])), default=0)


def horizon(league: dict) -> tuple[int, int | None]:
    """(last week anyone may see, last day within it). Pre-season = Week 1 up to `draft_after_day`."""
    if league["current_week"] == 0:
        return 1, league["settings"]["draft_after_day"]
    return league["current_week"], None


def visible_events(league: dict) -> dict[str, list[CheckedEvent]]:
    """Verified events up to the horizon, nothing later."""
    last_week, last_day = horizon(league)
    out = {}
    for week, evs in latest_events(league["season"]).items():
        n = scoring.week_num(week)
        if n > last_week:
            continue
        keep = [e for e in evs if e.status == "verified"]
        if last_day is not None and n == last_week:
            keep = [e for e in keep if e.day is not None and e.day <= last_day]
        out[week] = keep
    return out


def next_week(league: dict) -> int:
    return league["current_week"] + 1


def active_roster(player: dict, week: int) -> list[str]:
    return [s["islander"] for s in player["roster"] if scoring.slot_active(s, week)]


def owners(league: dict, week: int) -> dict[str, str]:
    return {name: p["name"] for p in league["players"] for name in active_roster(p, week)}


def islander_facts(league: dict) -> dict[str, dict]:
    """Per islander, as of the horizon: in the villa?, partner, points to date (standard + house rules), events."""
    events = visible_events(league)
    rules = scoring.load_rules(league)
    lines = scoring.ledger(events, rules)
    if horizon(league)[1] is not None:  # pre-season: the week hasn't ended, so nobody has "survived" it yet
        lines = [l for l in lines if l.rule_id != "std-survive"]
    points = defaultdict(int)
    for line in lines:
        points[line.islander] += line.points
    facts: dict[str, dict] = {}
    ordered = sorted((e for evs in events.values() for e in evs),
                     key=lambda e: (scoring.week_num(e.week), e.day or 0))
    for e in ordered:
        for name in e.islanders:
            f = facts.setdefault(name, {"name": name, "in_villa": False, "partner": None, "points": 0, "events": []})
            f["events"].append({"week": e.week, "day": e.day, "type": e.type, "with": e.others or
                                [n for n in e.islanders if n != name], "quote": e.evidence[0].quote})
            if e.type in ("entered_villa", "re_entered"):
                f["in_villa"] = True
            elif e.type in ("dumped", "left_villa"):
                f["in_villa"], f["partner"] = False, None
            elif e.type in ("coupled_up", "stayed_coupled"):
                f["partner"] = next((n for n in e.islanders if n != name), f["partner"])
            elif e.type == "left_single":
                f["partner"] = None
    for name, f in facts.items():
        f["points"] = points.get(name, 0)
    return facts


def free_agents(league: dict) -> list[dict]:
    """Islanders in the villa now and on nobody's roster for next week, best scorers first."""
    taken = owners(league, next_week(league))
    pool = [f for f in islander_facts(league).values() if f["in_villa"] and f["name"] not in taken]
    return sorted(pool, key=lambda f: (-f["points"], f["name"]))


def future_names(league: dict) -> list[str]:
    """Cast members who haven't entered by the horizon (used only to catch spoilers, never shown to agents)."""
    season = seasons()[league["season"]]
    seen = set(islander_facts(league))
    return [p["first_name"] for p in cast_source.cast(season["pages"]["wikipedia"]) if p["first_name"] not in seen]


# ---------------------------------------------------------------- league lifecycle

def save(key: str, league: dict) -> None:
    scoring.save_league(key, league)


def load(key: str) -> dict:
    league = scoring.load_league(key)
    if not is_play(league):
        raise MoveError("That league is not a play-along league")
    return league


def create(name: str, you: str = "You", season_key: str = "love_island_usa_s8", seed: int | None = None) -> str:
    """Create a play-along league (you + 3 bot friends), pick a draft order, and let bots pick until your turn."""
    if season_key not in seasons():
        raise MoveError(f"Unknown season '{season_key}'")
    you = you.strip()[:20] or "You"
    if you in BOT_NAMES:
        raise MoveError(f"Pick a name other than {', '.join(BOT_NAMES)}")
    key = slug(name)
    if scoring.league_path(key).exists():
        key = f"{key}_{datetime.now(timezone.utc).strftime('%H%M%S')}"
    seed = seed if seed is not None else random.randrange(10_000)
    order = [you] + BOT_NAMES
    random.Random(seed).shuffle(order)
    league = {
        "name": name.strip()[:60] or "My Villa League", "season": season_key, "commissioner": you, "mode": "play",
        "rules_file": "standard.json", "house_rules": [], "seed": seed, "you": you,
        "settings": dict(DEFAULT_SETTINGS), "current_week": 0,
        "players": [{"name": n, "bot": n != you, "roster": []} for n in [you] + BOT_NAMES],
        "draft": {"order": order, "picks": [], "done": False}, "moves": [],
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    run_bot_picks(league)
    save(key, league)
    return key


def draft_turn(league: dict) -> str | None:
    """Whose pick it is (snake order), or None when the draft is over."""
    d = league["draft"]
    total = len(d["order"]) * league["settings"]["draft_rounds"]
    n = len(d["picks"])
    if n >= total:
        return None
    rnd, i = divmod(n, len(d["order"]))
    return d["order"][i] if rnd % 2 == 0 else d["order"][::-1][i]


def draft_pool(league: dict) -> list[dict]:
    return free_agents(league)


def _player(league: dict, name: str) -> dict:
    return next(p for p in league["players"] if p["name"] == name)


def make_pick(league: dict, player: str, islander: str, by: str, reason: str = "") -> dict:
    turn = draft_turn(league)
    if turn is None:
        raise MoveError("The draft is over")
    if player != turn:
        raise MoveError(f"It's {turn}'s pick, not {player}'s")
    pool = {f["name"]: f for f in draft_pool(league)}
    if islander not in pool:
        raise MoveError(f"{islander} isn't available")
    pick = {"round": len(league["draft"]["picks"]) // len(league["draft"]["order"]) + 1,
            "pick": len(league["draft"]["picks"]) + 1, "player": player, "islander": islander, "by": by,
            "reason": reason[:300]}
    league["draft"]["picks"].append(pick)
    _player(league, player)["roster"].append({"islander": islander, "from_week": 1})
    if draft_turn(league) is None:
        league["draft"]["done"] = True
    return pick


def _bot_score(league: dict, bot: str, f: dict) -> float:
    """Bots like points, islanders in a couple, and have a little personal taste (seeded, so it's repeatable)."""
    taste = random.Random(f"{league['seed']}-{bot}-{f['name']}").random() * 4
    return f["points"] + (2 if f["partner"] else 0) + taste


def run_bot_picks(league: dict) -> list[dict]:
    picks = []
    while (turn := draft_turn(league)) and _player(league, turn).get("bot"):
        pool = draft_pool(league)
        best = max(pool, key=lambda f: _bot_score(league, turn, f))
        picks.append(make_pick(league, turn, best["name"], by="bot",
                               reason=f"{best['points']} pts so far" + (f", coupled with {best['partner']}" if best["partner"] else "")))
    return picks


# ---------------------------------------------------------------- moves

def moves_this_window(league: dict, player: str) -> int:
    return sum(1 for m in league["moves"] if m["player"] == player and m["from_week"] == next_week(league))


def check_move(league: dict, player: str, add: str | None, drop: str | None) -> list[str]:
    """Every reason this move breaks the league rules (empty list = allowed)."""
    problems = []
    if not league["draft"]["done"]:
        problems.append("the draft isn't finished")
    if league["current_week"] >= max_week(league):
        problems.append("the season is over")
    if not add and not drop:
        problems.append("a move needs an add or a drop")
    roster = active_roster(_player(league, player), next_week(league))
    agents = {f["name"] for f in free_agents(league)}
    if add and add not in agents:
        problems.append(f"{add} isn't a free agent in the villa right now")
    if drop and drop not in roster:
        problems.append(f"{drop} isn't on {player}'s roster")
    size_after = len(roster) + (1 if add else 0) - (1 if drop else 0)
    if size_after > league["settings"]["roster_max"]:
        problems.append(f"roster would have {size_after} islanders (max {league['settings']['roster_max']}); drop someone")
    if moves_this_window(league, player) >= league["settings"]["moves_per_week"]:
        problems.append(f"{player} already used this week's {league['settings']['moves_per_week']} move")
    return problems


def apply_move(league: dict, player: str, add: str | None, drop: str | None, by: str, reason: str = "") -> dict:
    problems = check_move(league, player, add, drop)
    if problems:
        raise MoveError("; ".join(problems))
    week = next_week(league)
    p = _player(league, player)
    if drop:
        slot = next(s for s in p["roster"] if s["islander"] == drop and scoring.slot_active(s, week))
        if slot.get("from_week", 1) >= week:
            p["roster"].remove(slot)  # picked up and dropped before ever playing
        else:
            slot["until_week"] = week - 1
    if add:
        p["roster"].append({"islander": add, "from_week": week})
    move = {"from_week": week, "player": player, "add": add, "drop": drop, "by": by, "reason": reason[:400],
            "made_after": f"Week {league['current_week']}"}
    league["moves"].append(move)
    return move


def bot_moves(league: dict) -> list[dict]:
    """Each bot: drop anyone who left the villa, then fill the roster with the best free agent it likes."""
    made = []
    facts = islander_facts(league)
    for p in league["players"]:
        if not p.get("bot") or moves_this_window(league, p["name"]):
            continue
        roster = active_roster(p, next_week(league))
        gone = [n for n in roster if not facts.get(n, {}).get("in_villa")]
        pool = free_agents(league)
        if not pool:
            continue
        best = max(pool, key=lambda f: _bot_score(league, p["name"], f))
        drop = gone[0] if gone else None
        if not drop and len(roster) >= league["settings"]["roster_max"]:
            continue
        try:
            made.append(apply_move(league, p["name"], best["name"], drop, by="bot",
                                   reason=(f"{drop} left the villa; " if drop else "") + f"{best['name']} has {best['points']} pts"))
        except MoveError:
            pass
    return made


def advance(key: str, autopilot_fn=None) -> dict:
    """Play the next week: autopilot moves for you (if on), bot moves, then reveal and score the week."""
    league = load(key)
    if not league["draft"]["done"]:
        raise MoveError("Finish the draft first")
    if league["current_week"] >= max_week(league):
        raise MoveError("That was the last week recapped so far")
    you = league["you"]
    auto = []
    if league["settings"].get("autopilot") and autopilot_fn:
        auto = autopilot_fn(key, league)
    bots = bot_moves(league)
    before = {r["player"]: r["total"] for r in _standings(key, league)}
    league["current_week"] += 1
    save(key, league)
    after = _standings(key, league)
    week = f"Week {league['current_week']}"
    mine = [l for l in scoring.score_league(key, save=False, up_to_week=league["current_week"])["ledger"]
            if l["week"] == week and l["islander"] in active_roster(_player(league, you), league["current_week"])]
    return {"week": week, "autopilot_moves": auto, "bot_moves": bots,
            "standings": [{**r, "change": r["total"] - before.get(r["player"], 0)} for r in after],
            "your_points": sorted(mine, key=lambda l: -abs(l["points"]))}


def _standings(key: str, league: dict) -> list[dict]:
    return scoring.score_league(key, save=False, up_to_week=league["current_week"])["standings"]


def state(key: str) -> dict:
    """Everything the Draft & Moves screen needs."""
    league = load(key)
    you = _player(league, league["you"])
    week = next_week(league)
    facts = islander_facts(league)
    return {
        "key": key, "name": league["name"], "you": league["you"], "season": league["season"],
        "current_week": league["current_week"], "max_week": max_week(league), "settings": league["settings"],
        "draft": {**league["draft"], "turn": draft_turn(league)},
        "free_agents": free_agents(league),
        "your_roster": [{**facts.get(n, {"name": n, "in_villa": False, "partner": None, "points": 0, "events": []})}
                        for n in active_roster(you, week)],
        "rosters": {p["name"]: active_roster(p, week) for p in league["players"]},
        "moves": league["moves"][-30:],
        "moves_left": league["settings"]["moves_per_week"] - moves_this_window(league, league["you"]),
        "standings": _standings(key, league),
    }


def set_autopilot(key: str, on: bool) -> dict:
    league = load(key)
    league["settings"]["autopilot"] = bool(on)
    save(key, league)
    return league["settings"]
