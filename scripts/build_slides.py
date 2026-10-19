"""Build slides.html: a 10-slide reveal.js deck (reveal.js from a CDN, screenshots embedded).

    python scripts/build_slides.py

Same numbers as the report (scripts/evidence.py). Arrow keys to move, F for full screen, S for speaker notes.
"""
from html import escape
from pathlib import Path
import base64
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import *  # noqa: E402,F401,F403

REVEAL = "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist"


def img(name: str, alt: str, cls: str = "shot") -> str:
    path = SHOTS / f"{name}.png"
    if not path.exists():
        return f'<div class="missing">Screenshot pending: {escape(name)}.png</div>'
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img class="{cls}" src="data:image/png;base64,{data}" alt="{escape(alt)}">'


def notes(text: str) -> str:
    return f'<aside class="notes">{escape(text)}</aside>'


facts_checked = sum(v["truth"] for v in evals["by_type"].values())
search_x = round(search_scout[0]["cost_usd"] / (sum(normal_scout) / len(normal_scout))) if search_scout else 0
ref_cached_pct = round(100 * agents["ref"]["cached_input_tokens"] / max(agents["ref"]["input_tokens"], 1))
week_seconds = round(sum(s["seconds"] + r["seconds"] for _, s, r in season_rows) / len(season_rows))
per_user_10k = scale_rows[2][3]
month_10k = scale_rows[2][2]
alone_10k = scale_rows[2][4]
s = safety["summary"]
_ev = list(evals_autopilot.values())
coach_seasons = sum(v["summary"]["seasons"] for v in _ev)
coach_rank = round(sum(v["summary"]["avg_rank"] * v["summary"]["seasons"] for v in _ev) / max(coach_seasons, 1), 2)

CSS = """
:root { --hot:#ff2e93; --sunset:#ff8a3d; --pool:#29e6d6; --gold:#ffd23f; --ink:#fff7fb; }
.reveal-viewport { background: radial-gradient(circle at 80% 15%, rgba(255,210,63,.45) 0, rgba(255,138,61,.25) 10%, transparent 26%),
  linear-gradient(180deg,#1d0730 0%,#4a0f4f 30%,#9c1f6e 58%,#ff2e93 82%,#ff8a3d 100%); }
.reveal { font-family: Poppins, "Helvetica Neue", Arial, sans-serif; color: var(--ink); font-size: 30px; }
.reveal h1, .reveal h2 { font-family: Pacifico, "Brush Script MT", cursive; font-weight: 400; text-transform: none; color: #ffe6f2;
  text-shadow: 0 0 8px rgba(255,46,147,.9), 0 0 24px rgba(255,46,147,.6); letter-spacing: 0; }
.reveal h1 { font-size: 2.6em; margin-bottom: .2em; }
.reveal h2 { font-size: 1.6em; margin-bottom: .45em; }
.reveal p, .reveal li { line-height: 1.35; }
.reveal ul { margin-left: .4em; }
.reveal li { margin: .25em 0; }
.reveal .sub { color: rgba(255,247,251,.8); font-size: .75em; }
.reveal .big { font-size: 1.15em; font-weight: 700; }
.reveal b, .reveal strong { color: #fff; }
.reveal .hl { color: var(--gold); }
.reveal .pool { color: var(--pool); }
.card { background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.25); border-radius: 22px; padding: 18px 24px;
  box-shadow: 0 10px 40px rgba(29,7,48,.35); text-align: left; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 26px; align-items: start; }
.cols3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.stat { text-align: center; }
.stat b { display: block; font-size: 2.1em; line-height: 1.1; color: #fff; text-shadow: 0 0 14px rgba(255,46,147,.7); }
.stat span { font-size: .62em; color: rgba(255,247,251,.85); }
.reveal img.shot { border-radius: 14px; border: 2px solid rgba(255,255,255,.35); box-shadow: 0 10px 40px rgba(29,7,48,.5); margin: 0; max-height: 470px; }
.reveal img.tall { max-height: 520px; }
.cap { font-size: .55em; color: rgba(255,247,251,.85); margin-top: 6px; }
.diagram { background: #fff; border-radius: 22px; padding: 12px 18px; display: inline-block; }
.diagram svg { width: auto !important; height: 470px !important; max-width: 100%; }
table.cmp { font-size: .78em; width: 100%; border-collapse: collapse; }
table.cmp th, table.cmp td { padding: 9px 12px; border-bottom: 1px solid rgba(255,255,255,.2); text-align: left; }
table.cmp th { color: var(--gold); font-weight: 600; }
table.cmp td.y { color: var(--pool); font-weight: 700; text-align: center; }
table.cmp td.n { color: rgba(255,247,251,.45); text-align: center; }
table.cmp td.p { color: var(--gold); font-weight: 700; text-align: center; }
table.cmp tr:last-child td { background: rgba(255,46,147,.25); font-weight: 700; }
.todo { background: rgba(255,210,63,.18); border: 2px dashed var(--gold); border-radius: 14px; padding: 8px 14px; font-size: .6em; color: #fff3c4; }
.missing { border: 2px dashed rgba(255,255,255,.5); padding: 60px; border-radius: 14px; }
.small { font-size: .62em; }
"""

slides = []

# 1. Title
slides.append(f"""
<section>
  <h1>Meet at the Fire Pit 🔥</h1>
  <p class="big">An AI agent team that runs your Love Island fantasy league</p>
  <p class="sub">Live sources in · a receipt behind every point · disputes settled · an AI coach that drafts and plays for you · a share-or-take finale · a 3D villa</p>
  <p class="sub" style="margin-top:1.4em">Jolie Bua · MGT 409 AI Foundations for Managers · Fall 2026<br>{REPO.replace("https://", "")}</p>
  {notes("One sentence: it's the commissioner's job, done by agents, with proof for every point.")}
</section>""")

# 2. Problem + audience
slides.append(f"""
<section>
  <h2>Why nobody runs a Love Island league</h2>
  <div class="cols">
    <div class="card">
      <p><b>Who:</b> Love Island fans who'd play a fantasy league the way fantasy football fans do.</p>
      <p><b>Today:</b> Bachelor brackets (prediction games) exist, but a points league means one friend rewatching, scoring a spreadsheet and settling "that wasn't a real date!" every week.</p>
    </div>
    <div class="card">
      <p class="big" style="font-size:.95em">“I watch Love Island religiously but have never seen a fantasy league for it. I play fantasy football, which is a lot of effort to prep for the draft.”</p>
      <p class="small">Me, the target user (my own experience, not an outside interview)</p>
    </div>
  </div>
  <p class="small" style="margin-top:16px">Fantasy football works because the platform does the scoring. For Love Island, the one draft app I found doesn't describe your own house rules or proof for each point.</p>
  {notes("Be upfront that the quote is my own experience as a fan; the outside-user trial is a next step.")}
</section>""")

# 3. What is new
rows = [("Spreadsheet + group chat", "y", "n", "n", "n"),
        ("RealTVFantasy", "p", "n", "n", "n"),
        ("Bracketology", "n", "n", "n", "n"),
        ("Make Your Picks", "n", "n", "n", "n"),
        ("Reality Draft Picks", "n", "n", "n", "n"),
        ("Meet at the Fire Pit", "y", "y", "y", "y")]
MARK = {"y": "✓", "p": "◐", "n": "–"}
cells = "".join(f"<tr><td>{n}</td>" + "".join(f'<td class="{c}">{MARK[c]}</td>' for c in cs) + "</tr>"
                for n, *cs in rows)
slides.append(f"""
<section>
  <h2>What's new</h2>
  <table class="cmp">
    <thead><tr><th></th><th>Your own house rules</th><th>Receipt for every point</th><th>AI ref for disputes</th><th>AI coach / autopilot</th></tr></thead>
    <tbody>{cells}</tbody>
  </table>
  <p class="small" style="margin-top:14px">◐ custom scoring categories · – not described in the app's store listing (checked Oct 19, 2026).
  The others offer category or fixed scoring or prediction games, and mostly don't cover Love Island. Spreadsheets are fully custom but 100% manual.</p>
  {notes("Point: a points-per-event league with your own rules and proof, not a prediction game.")}
</section>""")

# 4. Agent diagram
slides.append(f"""
<section>
  <h2>Six agents, one code referee</h2>
  <div class="diagram">{DIAGRAM}</div>
  <p class="small" style="margin-top:10px">gpt-6-luna proposes · <span class="hl">plain code checks every quote and does all the math</span> · the commissioner approves every change</p>
  {notes("Scout gathers, Recapper extracts with exact quotes, verify.py checks, Scorekeeper is code, Host writes the drop. Rulesmith and Ref only create pending items. The Strategist coaches or plays a team; the season engine checks every move.")}
</section>""")

# 5. Demo: receipts + villa
slides.append(f"""
<section>
  <h2>Every point has a receipt</h2>
  <div class="cols">
    <div>{img("receipts", "Leaderboard with receipts")}<div class="cap">Tap a player → every point with its rule and source sentence</div></div>
    <div>{img("villa", "This week in the villa")}<div class="cap">Sources the Scout found · events the Recapper extracted, each ✓ verified by code</div></div>
  </div>
  {notes("Live demo here if time: open Week 2, show the America's-choice coupling quote.")}
</section>""")

# 6. Demo: the AI coach + 3D villa
slides.append(f"""
<section>
  <h2>Your AI coach, by the fire pit</h2>
  <div class="cols">
    <div>{img("draft", "Draft room with the Strategist")}<div class="cap">Draft room: the Villa Strategist ranks picks from what has aired so far ({usd(coach)} per call)</div></div>
    <div>{img("season", "Play-along season in 3D")}<div class="cap">Play week by week: your islanders on the fire pit couches with their partners (🧳 = dumped), 🤖 autopilot makes rule-checked moves before each week</div></div>
  </div>
  {notes("Play-along mode: you + 3 bots draft after Day 2, then reveal one week at a time. Autopilot added Kenzie and Corbin before Weeks 1-2 with reasons; after Week 2 it held because nobody was free.")}
</section>""")

# 7. Cost
slides.append(f"""
<section>
  <h2>What it costs to run</h2>
  <div class="cols3">
    <div class="card stat"><b>{usd(season_cost, 3)}</b><span>to recap the whole S8 season once ({len(season_rows)} weeks, live sources)</span></div>
    <div class="card stat"><b>{per_user_10k}</b><span>per user per month at 10,000 users ({month_10k}/month total)</span></div>
    <div class="card stat"><b>{search_x}×</b><span>more for a week that needs web search. Capped at 1 per run</span></div>
  </div>
  <ul class="small" style="margin-top:22px">
    <li>The recap pipeline runs <b>once per show-week, shared by every league</b>. Without sharing, 10,000 users would cost {alone_10k}/month</li>
    <li>Prompt caching: {ref_cached_pct}% of the Ref's input tokens cached · previews, not full pages, for the Scout</li>
    <li>Villa Strategist: about {usd(coach)} per advice or autopilot week</li>
    <li>Self-correct round: +1 call ({usd(w2_with["cost_usd"] - w2_without["cost_usd"])}) recovered 3 of 19 Week 2 events. Kept</li>
  </ul>
  <p class="sub small">Measured from API usage on every billed run · gpt-6-luna course prices · assumptions: {PLAYERS_PER_LEAGUE} players/league, {DISPUTES_PER_LEAGUE_WEEK} disputes/week, {STRATEGIST_PER_LEAGUE_WEEK} coach call/week</p>
  {notes("All numbers come from output/runs via scripts/evidence.py.")}
</section>""")

# 8. Safety
slides.append(f"""
<section>
  <h2>Safety: attack it, log it</h2>
  <div class="cols">
    <div class="card">
      <p class="big"><span class="pool">{s["PASS"]} pass</span> · {s["FAIL"]} fail · <span class="hl">{s["known limit"]} known limit</span></p>
      <ul class="small">
        <li><b>Injection in recaps:</b> hidden text stripped, the line flagged, its quotes can't count</li>
        <li><b>Injection in disputes:</b> fake "commissioner approved" denied, nothing changes without approval</li>
        <li><b>Invented events:</b> fake quotes, fake islanders, wrong days, an islander who wasn't in the villa: all rejected by code</li>
        <li><b>Overspending:</b> request, token, web-search and input-size caps</li>
        <li><b>Autonomous coach:</b> sees only aired weeks; autopilot can't apply illegal moves</li>
      </ul>
      <p class="small"><span class="hl">Known limit:</span> a believable lie planted in a trusted source can pass. It shows as single-source and can be disputed.</p>
    </div>
    <div>{img("injection", "Manipulation attempt denied", "shot")}<div class="cap">A real dispute that claimed commissioner pre-approval: flagged and denied</div></div>
  </div>
  {notes("scripts/safety_tests.py: 21 repeatable attacks, evidence in output/safety/.")}
</section>""")

# 9. Impact
slides.append(f"""
<section>
  <h2>Impact</h2>
  <div class="cols3">
    <div class="card stat"><b>{evals["precision"]:.0%}</b><span>precision and {evals["recall"]:.0%} recall on {facts_checked} facts the cast table can prove</span></div>
    <div class="card stat"><b>{n_verified}</b><span>verified events, Love Island USA S8 weeks 1–5</span></div>
    <div class="card stat"><b>~{week_seconds}s</b><span>machine time per episode week (Scout + Recapper)</span></div>
  </div>
  <p class="small" style="margin-top:20px">Commissioner's job → approve or decline. Arguments end with a quote.</p>
  <p class="small"><span class="hl">AI coach vs. simple bots:</span> average rank {coach_rank} of 4 over {coach_seasons} simulated seasons, 0 wins: no edge yet (draft luck likely dominates).</p>
  <p class="small"><span class="hl">Tested with 3 friends:</span> 3/3 would use it, and they're launching a league with it next season. They loved the graphics, the draft coach and the finale.</p>
  {notes("Caveat: accuracy is graded against wiki tables; noisier sources are next.")}
</section>""")

# 10. Next steps
slides.append(f"""
<section>
  <h2>Limits & what's next</h2>
  <div class="cols">
    <div class="card">
      <p><b>Not yet</b></p>
      <ul class="small">
        <li>A quote proves it's <i>in</i> a source, not that it's <i>true</i></li>
        <li>Wiki recaps lag a few days; X and Reddit need keys the course doesn't allow</li>
        <li>Small, friendly test (3) · no timed trial yet · one season · no logins</li>
        <li>The AI coach doesn't beat simple bots yet</li>
      </ul>
    </div>
    <div class="card">
      <p><b>Next</b></p>
      <ul class="small">
        <li>Two-source rule for big events</li>
        <li>Live recaps from X/TikTok trends (testers' #1 ask)</li>
        <li>Live scoring during a season + push notifications for the drop</li>
        <li>Accounts, a draft room and invite links</li>
        <li>Timed trial when the testers launch next summer, and a bigger autopilot evaluation</li>
      </ul>
    </div>
  </div>
  <p class="sub" style="margin-top:20px">💖 Thanks! Try it: {REPO.replace("https://", "")}</p>
  {notes("Close on the real-user trial plan.")}
</section>""")

assert len(slides) <= 10, "the deck must have 10 slides or fewer"

html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Meet at the Fire Pit · slides</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="{REVEAL}/reset.css">
<link rel="stylesheet" href="{REVEAL}/reveal.css">
<link rel="stylesheet" href="{REVEAL}/theme/black.css">
<link href="https://fonts.googleapis.com/css2?family=Pacifico&family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head><body>
<div class="reveal"><div class="slides">
{"".join(slides)}
</div></div>
<script src="{REVEAL}/reveal.js"></script>
<script src="{REVEAL.replace('/dist', '')}/plugin/notes/notes.js"></script>
<script>
  Reveal.initialize({{ hash: true, slideNumber: "c/t", transition: "fade", width: 1280, height: 720, margin: 0.04,
                      plugins: [RevealNotes] }});
</script>
</body></html>
"""
(ROOT / "slides.html").write_text(html)
print(f"slides.html written: {len(slides)} slides, {len(html) // 1024} KB")
