"""The finale at the fire pit: the top two players each choose, in a sealed envelope, to share the pot or take it all.

Same rules as the show's final twist:
    both share          -> split 50/50
    one takes it all    -> the taker gets everything, the sharer gets nothing
    both take it all    -> nobody gets anything
The pot is virtual: no real money moves through the app.

Sealed choices are never returned before the reveal. In play-along leagues the bot finalist decides at the
reveal, from its own personality, without seeing your envelope.
"""
from datetime import datetime, timezone
import random

from backend import scoring, season_play as sp
from backend.agents.recapper import latest_events

DEFAULT_PRIZE = 100
CHOICES = ("share", "take")
# How likely each bot is to take it all (plus a little seeded mood).
BOT_TAKE_RATE = {"Maya": 0.35, "Dev": 0.55, "Priya": 0.2}


class FinaleError(ValueError):
    pass


def season_complete(league: dict) -> tuple[bool, int]:
    """(is the season over?, final week number)."""
    events = latest_events(league["season"])
    last = max((scoring.week_num(w) for w in events), default=0)
    if sp.is_play(league):
        return league["current_week"] >= last and last > 0, last
    crowned = any(e.type == "winner" and e.status == "verified" for e in events.get(f"Week {last}", []))
    return crowned, last


def finalists(key: str, league: dict, final_week: int) -> list[dict]:
    rows = scoring.score_league(key, save=False, up_to_week=final_week)["standings"][:2]
    return [{"player": r["player"], "total": r["total"]} for r in rows]


def _public(f: dict | None, league: dict) -> dict | None:
    """The finale as anyone may see it: who has sealed an envelope, but never what is inside before the reveal."""
    if not f:
        return None
    out = {k: f[k] for k in ("prize", "finalists", "round", "started", "revealed")}
    out["sealed"] = {p["player"]: p["player"] in f["choices"] for p in f["finalists"]}
    out["bots"] = [p["player"] for p in f["finalists"] if _is_bot(league, p["player"])]
    if f["revealed"]:
        out.update(choices=f["choices"], payout=f["payout"], host_line=f["host_line"], revealed_at=f.get("revealed_at"))
    return out


def _is_bot(league: dict, name: str) -> bool:
    return any(p["name"] == name and p.get("bot") for p in league["players"])


def state(key: str) -> dict:
    league = scoring.load_league(key)
    done, last = season_complete(league)
    return {"complete": done, "final_week": last, "finale": _public(league.get("finale"), league),
            "you": league.get("you"), "mode": league.get("mode", "classic")}


def start(key: str, prize: int = DEFAULT_PRIZE) -> dict:
    """Hand out the envelopes to the top two (starts a fresh round if one already happened)."""
    league = scoring.load_league(key)
    done, last = season_complete(league)
    if not done:
        raise FinaleError("The season isn't over yet: the finale happens after the final week")
    if not 1 <= int(prize) <= 1_000_000:
        raise FinaleError("The pot must be between 1 and 1,000,000")
    previous = league.get("finale") or {}
    league["finale"] = {"prize": int(prize), "finalists": finalists(key, league, last), "choices": {}, "by": {},
                        "revealed": False, "round": previous.get("round", 0) + 1,
                        "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    scoring.save_league(key, league)
    return state(key)


def choose(key: str, player: str, choice: str) -> dict:
    """Seal one finalist's envelope. In play-along leagues only you choose; the bot decides at the reveal."""
    league = scoring.load_league(key)
    f = league.get("finale")
    if not f:
        raise FinaleError("Hand out the envelopes first")
    if f["revealed"]:
        raise FinaleError("The envelopes are already open")
    if choice not in CHOICES:
        raise FinaleError("Choose 'share' or 'take'")
    names = [p["player"] for p in f["finalists"]]
    if player not in names:
        raise FinaleError(f"{player} isn't a finalist ({' and '.join(names)} are)")
    if _is_bot(league, player):
        raise FinaleError(f"{player} decides for themselves at the reveal")
    if player in f["choices"]:
        raise FinaleError(f"{player}'s envelope is already sealed")
    f["choices"][player] = choice
    f["by"][player] = "player"
    scoring.save_league(key, league)
    return state(key)


def bot_choice(league: dict, bot: str) -> str:
    """A bot's own decision: its personality plus seeded mood. It never looks at the other envelope."""
    rnd = random.Random(f"{league.get('seed', 0)}-{bot}-finale-{league['finale']['round']}")
    return "take" if rnd.random() < BOT_TAKE_RATE.get(bot, 0.4) else "share"


def payout(prize: int, choices: dict[str, str]) -> dict[str, float]:
    (a, ca), (b, cb) = choices.items()
    if ca == "share" and cb == "share":
        return {a: prize / 2, b: prize / 2}
    if ca == "take" and cb == "take":
        return {a: 0, b: 0}
    return {a: prize if ca == "take" else 0, b: prize if cb == "take" else 0}


def _host_line(choices: dict[str, str], prize: int) -> str:
    (a, ca), (b, cb) = choices.items()
    if ca == cb == "share":
        return f"Islanders… {a} and {b} both chose to share. That's {prize // 2 if prize % 2 == 0 else prize / 2} each, and the fire pit has never felt warmer. 💞"
    if ca == cb == "take":
        return f"Oh my days. {a} and {b} both tried to take it all… so nobody gets a thing. The pot goes up in smoke. 🔥"
    taker, sharer = (a, b) if ca == "take" else (b, a)
    return f"{sharer} chose to share… but {taker} took it all. The whole {prize} goes to {taker}. The villa is speechless."


def reveal(key: str) -> dict:
    league = scoring.load_league(key)
    f = league.get("finale")
    if not f:
        raise FinaleError("Hand out the envelopes first")
    if f["revealed"]:
        return state(key)
    for p in f["finalists"]:
        name = p["player"]
        if name in f["choices"]:
            continue
        if _is_bot(league, name):
            f["choices"][name] = bot_choice(league, name)
            f["by"][name] = "bot"
        else:
            raise FinaleError(f"{name} hasn't sealed their envelope yet")
    ordered = {p["player"]: f["choices"][p["player"]] for p in f["finalists"]}
    f["choices"] = ordered
    f["payout"] = payout(f["prize"], ordered)
    f["host_line"] = _host_line(ordered, f["prize"])
    f["revealed"] = True
    f["revealed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    scoring.save_league(key, league)
    return state(key)


def reset(key: str) -> dict:
    league = scoring.load_league(key)
    league.pop("finale", None)
    scoring.save_league(key, league)
    return state(key)
