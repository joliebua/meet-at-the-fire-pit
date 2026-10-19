# Proof it runs from a fresh clone

Done on **Oct 19, 2026** against commit `6ba7f92`, the version submitted for grading. I cloned the public repo into a new folder next to the course `.env`, followed the README word for word, and drove the app with a headless browser (Playwright). Every screenshot below comes from that clone.

**Result: 12 of 12 steps passed · 0 app errors · 0 failed requests.**

## Setup, exactly as the README says

```
date: 2026-10-19 23:35 UTC · macOS 26.6.2 · Python 3.14.7
$ git clone https://github.com/joliebua/meet-at-the-fire-pit.git
commit: 6ba7f92 Add privacy redaction, an app-wide AI budget and rate limit, and hidden-text stripping
no .env in clone: yes · course .env one folder up: yes
$ python3 -m venv .venv
$ .venv/bin/pip install -r requirements.txt
installed after 15s
$ .venv/bin/uvicorn backend.main:app --port 8001    # port 8000 was busy on this Mac, as the README allows
INFO:     Started server process [37767]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8001 (Press CTRL+C to quit)
app running 27s after the clone started
GET /api/config → {"source_mode":"live","snapshot":"love_island_usa_s8","model":"gpt-6-luna","seasons":{"love_island_usa_s8":{"show":"Love Island USA","season":"8"}}}
GET /api/budget → {"spent_today_usd":0.09315,"daily_budget_usd":1.0,"max_agent_runs":30,"window_seconds":600}
```

## What a grader can do

| # | Step | What we checked | Screenshot |
|---|---|---|---|
| 1 | Leaderboard (demo league) | 3D fire pit loaded; labels: ['🎙️ Host “Islanders…”', 'Dev 💖 126 #1 · safe', 'Jolie 119 #2', 'Priya 91 #3', 'Maya 85 #4'] | [01_leaderboard.jpg](01_leaderboard.jpg) |
| 2 | Receipts for a player | 49 points, each with its source sentence | [02_receipts.jpg](02_receipts.jpg) |
| 3 | This Week in the Villa | 5 weeks; 7 events with quotes on the open week | [03_villa.jpg](03_villa.jpg) |
| 4 | Fire Pit tab: finale ready + weekly drop | finale card shown; drop headline: The Final Fire Pit: One Last Table Shake-Up | [04_fire_pit.jpg](04_fire_pit.jpg) |
| 5 | House Rules | 3 approved, 2 declined house rules listed | [05_house_rules.jpg](05_house_rules.jpg) |
| 6 | Disputes (past rulings) | 3 rulings; 2 manipulation attempts blocked | [06_disputes.jpg](06_disputes.jpg) |
| 7 | Safety live: sneaky dispute with a phone number | verdict: Denied 🙅; phone redacted: True; injection flagged: True; 11.3s | [07_safety_dispute.jpg](07_safety_dispute.jpg) |
| 8 | Cost to Run | 6 agents with measured tokens and cost | [08_costs.jpg](08_costs.jpg) |
| 9 | Finale: share or take it all | before reveal the card only said sealed (True); host: 🎙️ Dev chose to share… but Jolie took it all. The whole 100 goes to Jolie. The villa is speechless. | [09_finale.jpg](09_finale.jpg) |
| 10 | Play-along: play Week 3 on autopilot | Week 2 of 5 played → Week 3 of 5 played in 10.1s; 🤖 Autopilot: added Jen dropped Gabriel. Swap out Gabriel, who was dumped on Day 14 and can no longer earn points, for Jen: she is the only l | [10_play_week3.jpg](10_play_week3.jpg) |
| 11 | report.html opened from the clone | 6/6 embedded screenshots load; prints to 14 pages | [11_report.jpg](11_report.jpg) |
| 12 | slides.html opened from the clone | reveal.js ready; 10 slides; → arrow went to slide 2 | [12_slides.jpg](12_slides.jpg) |

## Screenshots

### 1. Leaderboard (demo league)

![Leaderboard (demo league)](01_leaderboard.jpg)

### 2. Receipts for a player

![Receipts for a player](02_receipts.jpg)

### 3. This Week in the Villa

![This Week in the Villa](03_villa.jpg)

### 4. Fire Pit tab: finale ready + weekly drop

![Fire Pit tab: finale ready + weekly drop](04_fire_pit.jpg)

### 5. House Rules

![House Rules](05_house_rules.jpg)

### 6. Disputes (past rulings)

![Disputes (past rulings)](06_disputes.jpg)

### 7. Safety live: sneaky dispute with a phone number

![Safety live: sneaky dispute with a phone number](07_safety_dispute.jpg)

### 8. Cost to Run

![Cost to Run](08_costs.jpg)

### 9. Finale: share or take it all

![Finale: share or take it all](09_finale.jpg)

### 10. Play-along: play Week 3 on autopilot

![Play-along: play Week 3 on autopilot](10_play_week3.jpg)

### 11. report.html opened from the clone

![report.html opened from the clone](11_report.jpg)

### 12. slides.html opened from the clone

![slides.html opened from the clone](12_slides.jpg)

---
The playing done in this run (a dispute, the finale, Week 3) happened only in the throwaway clone, which was deleted afterwards. The repo itself still starts fresh: the demo league's finale is unopened and the Villa Demo league is at Week 2.
