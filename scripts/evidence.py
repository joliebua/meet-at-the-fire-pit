"""Numbers and pieces shared by build_report.py and build_slides.py, all computed from the app's own logs."""
from html import escape
from pathlib import Path
import base64
import json
import os
import sys

os.environ.setdefault("VILLA_SOURCE_MODE", "snapshot")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, usage_log  # noqa: E402
from backend.agents.recapper import latest_events  # noqa: E402

ROOT = config.ROOT
SHOTS = ROOT / "docs" / "screenshots"
REPO = "https://github.com/joliebua/villa-commissioner"
SEASON = "love_island_usa_s8"
WEEKS_PER_MONTH = 4.3
PLAYERS_PER_LEAGUE = 4          # the demo league
DISPUTES_PER_LEAGUE_WEEK = 2    # assumption, stated in the report
RULE_REQUESTS_PER_LEAGUE_MONTH = 2  # assumption, stated in the report
STRATEGIST_PER_LEAGUE_WEEK = 1  # one coach call per league per week (asked for, or autopilot)
DEMO_PLAY = "play_villa_demo"


def usd(x: float, digits: int = 4) -> str:
    return f"${x:,.{digits}f}" if x < 1 else f"${x:,.2f}"


# ---------------------------------------------------------------- evidence

runs = usage_log.load_runs()
agents = usage_log.per_agent(runs)
billed = [r for r in runs if r["billed"]]
evals = json.loads((config.OUTPUT / "eval_recaps.json").read_text())
safety = json.loads((config.OUTPUT / "safety" / "safety_report.json").read_text())
league = json.loads((config.DATA / "leagues" / "demo_league.json").read_text())
standings = json.loads((config.OUTPUT / "standings_demo_league.json").read_text())
prices = json.loads((config.DATA / "prices.json").read_text())["gpt-6-luna"]
events = latest_events(SEASON)
n_verified = sum(e.status == "verified" for evs in events.values() for e in evs)

# One full pass over the season: the latest billed live Scout run and self-corrected Recapper run per week.
season_rows = []
for week in events:
    sc = [r for r in billed if r["agent"] == "scout" and r["week"] == week and r["mode"] == "live"]
    rc = [r for r in billed if r["agent"] == "recapper" and r["week"] == week and r["self_correct"]]
    if sc and rc:
        season_rows.append((week, sc[-1], rc[-1]))
season_cost = sum(s["cost_usd"] + r["cost_usd"] for _, s, r in season_rows)
pipeline_week = season_cost / len(season_rows)
normal_scout = [s["cost_usd"] for _, s, _ in season_rows if s["web_searches"] == 0]
search_scout = [s for _, s, _ in season_rows if s["web_searches"] > 0]

host = agents["host"]["avg_cost_usd"]
refc = agents["ref"]["avg_cost_usd"]
rules = agents["rulesmith"]["avg_cost_usd"]
coach = agents["strategist"]["avg_cost_usd"] if "strategist" in agents else 0.0
league_week = host + DISPUTES_PER_LEAGUE_WEEK * refc + STRATEGIST_PER_LEAGUE_WEEK * coach
league_month = WEEKS_PER_MONTH * league_week + RULE_REQUESTS_PER_LEAGUE_MONTH * rules
pipeline_month = WEEKS_PER_MONTH * pipeline_week


def month_cost(users: int, shared: bool = True) -> float:
    leagues = max(1, round(users / PLAYERS_PER_LEAGUE))
    return (pipeline_month if shared else leagues * pipeline_month) + leagues * league_month


scale_rows = []
for users in (PLAYERS_PER_LEAGUE, 100, 10_000):
    shared, alone = month_cost(users), month_cost(users, shared=False)
    scale_rows.append([f"{users:,}", f"{max(1, round(users / PLAYERS_PER_LEAGUE)):,}", usd(shared, 4 if shared < 1 else 2),
                       usd(shared / users, 5), usd(alone, 4 if alone < 1 else 2)])

# Self-correct tradeoff (week 2): same first draft with and without the fix round.
w2 = [r for r in runs if r["agent"] == "recapper" and r["week"] == "Week 2"]
w2_with = next(r for r in w2 if r["self_correct"] and r["billed"] and r["requests"] == 2)
w2_without = next(r for r in w2 if r["self_correct"] is False and r["requests"] == 1)


def run_json(prefix: str) -> dict:
    files = sorted((config.OUTPUT / "runs").glob(prefix))
    return json.loads(files[-1].read_text()) if files else {}


scout_w2 = next(json.loads(f.read_text()) for f in sorted((config.OUTPUT / "runs").glob(f"scout_{SEASON}_week2_*.json"))
                if json.loads(f.read_text())["run"]["mode"] == "live")
ref_trace = run_json("ref_demo_league_dispute-3_*.json")
corbin = next(d for d in league.get("disputes", []) if d["id"] == "dispute-3")
host_w3 = run_json("host_demo_league_week3_*.json")
_line = next(l for l in standings["ledger"] if l["week"] == "Week 2" and l["label"].startswith("Dump"))
example_line = f'{_line["islander"]} {_line["points"]:+d}, {_line["label"]}: “{_line["quote"]}” ({_line["source_id"]})'



DIAGRAM = """
<svg viewBox="0 0 860 520" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Agent diagram" style="width:100%;height:auto">
<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#7a2a5a"/></marker></defs>
<style>.b{fill:#fff;stroke:#c2185b;stroke-width:2;rx:12}.c{fill:#fff4d6;stroke:#b8860b;stroke-width:2}.h{fill:#e0fbf8;stroke:#0c8fa3;stroke-width:2}
.t{font:600 14px Poppins,Arial,sans-serif;fill:#3a0d2e}.s{font:12px Poppins,Arial,sans-serif;fill:#6b4a60}.l{stroke:#7a2a5a;stroke-width:1.8;fill:none;marker-end:url(#a)}</style>
<rect x="10" y="20" width="170" height="150" class="h" rx="12"/><text x="24" y="44" class="t">Live sources</text>
<text x="24" y="68" class="s">Wikipedia (MediaWiki API)</text><text x="24" y="88" class="s">Love Island Fandom wiki</text>
<text x="24" y="108" class="s">Google News RSS</text><text x="24" y="128" class="s">OpenAI web search (cap 1)</text>
<text x="24" y="152" class="s">or the offline snapshot</text>
<rect x="225" y="45" width="140" height="70" class="b" rx="12"/><text x="243" y="73" class="t">🔎 Scout</text><text x="243" y="95" class="s">gathers a week</text>
<rect x="410" y="45" width="150" height="70" class="b" rx="12"/><text x="428" y="73" class="t">📝 Recapper</text><text x="428" y="95" class="s">events + exact quotes</text>
<rect x="605" y="35" width="240" height="90" class="c" rx="12"/><text x="620" y="60" class="t">✓ verify.py (code)</text>
<text x="620" y="80" class="s">quote word-for-word · real islander</text><text x="620" y="98" class="s">named in sentence · in villa that day</text><text x="620" y="116" class="s">wording fits type · day in week</text>
<rect x="605" y="170" width="240" height="70" class="c" rx="12"/><text x="620" y="198" class="t">🧮 Scorekeeper (code)</text><text x="620" y="220" class="s">verified events × approved rules</text>
<rect x="605" y="290" width="240" height="70" class="b" rx="12"/><text x="620" y="318" class="t">🎙️ Host</text><text x="620" y="340" class="s">weekly drop, numbers checked</text>
<rect x="225" y="190" width="160" height="70" class="b" rx="12"/><text x="240" y="218" class="t">📜 Rulesmith</text><text x="240" y="240" class="s">plain English → rules</text>
<rect x="225" y="300" width="160" height="70" class="b" rx="12"/><text x="240" y="328" class="t">⚖️ Ref</text><text x="240" y="350" class="s">disputes → event fixes</text>
<rect x="420" y="245" width="140" height="70" class="c" rx="12"/><text x="434" y="273" class="t">👑 Commissioner</text><text x="434" y="295" class="s">approves / declines</text>
<rect x="10" y="240" width="170" height="130" class="h" rx="12"/><text x="24" y="264" class="t">League members</text><text x="24" y="288" class="s">house rules (commish)</text><text x="24" y="308" class="s">disputes (any player)</text><text x="24" y="328" class="s">🙈 spoiler shield</text><text x="24" y="348" class="s">🎯 draft + weekly moves</text>
<path class="l" d="M180,80 L223,80"/><path class="l" d="M365,80 L408,80"/><path class="l" d="M560,80 L603,80"/>
<path class="l" d="M725,125 L725,168"/><path class="l" d="M725,240 L725,288"/>
<path class="l" d="M180,280 L223,225"/><path class="l" d="M180,320 L223,330"/>
<path class="l" d="M385,225 L418,270"/><path class="l" d="M385,335 L418,295"/><path class="l" d="M385,310 C395,190 520,140 640,127"/>
<path class="l" d="M560,270 L603,215"/>
<rect x="225" y="405" width="160" height="70" class="b" rx="12"/><text x="240" y="433" class="t">🎯 Strategist</text><text x="240" y="455" class="s">coach · or autopilot</text>
<rect x="420" y="405" width="180" height="70" class="c" rx="12"/><text x="434" y="433" class="t">🗓️ Season engine (code)</text><text x="434" y="455" class="s">draft · moves checked · weeks</text>
<path class="l" d="M180,355 L223,425"/><path class="l" d="M385,440 L418,440"/><path class="l" d="M598,405 C590,330 596,270 606,242"/>
<text x="200" y="497" class="s">Ref fixes go through verify.py too · nothing changes scores until the commissioner approves · Strategist moves pass code checks</text>
<text x="200" y="515" class="s">Gold boxes are plain code; pink boxes are gpt-6-luna agents; teal boxes are inputs</text>
</svg>"""


# Play-along mode: the committed demo league, plus the autopilot evaluations.
from backend import scoring as _scoring  # noqa: E402

demo_play = json.loads((config.DATA / "leagues" / f"{DEMO_PLAY}.json").read_text())
demo_play_standings = _scoring.score_league(DEMO_PLAY, save=False, up_to_week=demo_play["current_week"])["standings"]
autopilot_moves = [m for m in demo_play["moves"] if m["by"] == "autopilot"]
coach_runs = [r for r in billed if r["agent"] == "strategist"]
evals_autopilot = {v: json.loads((config.OUTPUT / f"eval_autopilot_{v}.json").read_text())
                   for v in ("v1", "v2") if (config.OUTPUT / f"eval_autopilot_{v}.json").exists()}


def _latest_coach_run(kind: str) -> dict:
    files = sorted((config.OUTPUT / "runs").glob(f"strategist_{DEMO_PLAY}_{kind}_*.json"))
    return json.loads(files[0].read_text()) if files else {}


demo_draft_run = _latest_coach_run("draft")       # the first draft advice in the demo league
demo_moves_run = json.loads(sorted((config.OUTPUT / "runs").glob(f"strategist_{DEMO_PLAY}_moves_*.json"))[-1].read_text()) \
    if list((config.OUTPUT / "runs").glob(f"strategist_{DEMO_PLAY}_moves_*.json")) else {}
