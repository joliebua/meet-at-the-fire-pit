"""Capture app screenshots into docs/screenshots/ for the report and slides (dev tool).

Start the app first (it serves the built UI), then:
    .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m playwright install chromium
    .venv/bin/python scripts/capture_screenshots.py --url http://127.0.0.1:8000
    .venv/bin/python scripts/capture_screenshots.py --url http://127.0.0.1:8000 --play-demo

Without --play-demo it only reads the app (opens tabs, clicks a player). With --play-demo it also
(re)creates the "Villa Demo" play-along league, asks the Strategist (well under a cent in model
calls), drafts, plays Weeks 1-2 on autopilot and screenshots each step. That league stays in the repo
so graders can keep playing it.
"""
from pathlib import Path
import argparse
import json
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
DEMO_PLAY = "play_villa_demo"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--play-demo", action="store_true", help="Recreate and play the demo play-along league too")
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860}, device_scale_factor=1)

        def go(tab: str, week: int = 5, wait_for: str = "main .card", league: str = "demo_league"):
            page.goto(f"{args.url}/#league={league}&tab={tab}&week={week}")
            page.reload()  # hash-only navigation doesn't remount the app
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(wait_for, timeout=15_000)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(600)

        def save(name: str, element: str | None = None):
            path = OUT / f"{name}.png"
            if element:
                page.locator(element).first.screenshot(path=path)
            else:
                page.screenshot(path=path)
            print("saved", path.relative_to(OUT.parent.parent))

        go("board", wait_for=".player")
        page.wait_for_timeout(3500)  # let the leader stand up by the fire
        save("leaderboard")
        page.locator(".player", has_text="Priya").first.click()
        page.wait_for_selector(".ledger .line")
        page.wait_for_timeout(400)
        save("receipts")

        go("villa", week=5, wait_for=".weekbtn")
        page.locator(".weekbtn", has_text="Week 2").first.click()
        page.wait_for_selector(".event")
        page.wait_for_timeout(500)
        save("villa")

        go("drop", week=5, wait_for=".drop h1")
        save("drop")

        go("rules", wait_for="textarea")
        save("house_rules")

        go("disputes", wait_for=".ruling")
        save("disputes")
        save("injection", ".ruling.deny")

        go("costs", wait_for="table.tbl")
        save("costs")
        if args.play_demo:
            play_demo(page, args.url, save)
        browser.close()


def play_demo(page, url: str, save):
    """Fresh 'Villa Demo' league: Strategist draft advice, draft, autopilot Weeks 1-2, screenshots."""
    (ROOT / "data" / "leagues" / f"{DEMO_PLAY}.json").unlink(missing_ok=True)
    req = urllib.request.Request(f"{url}/api/play", data=json.dumps({"name": "Villa Demo", "you": "Jolie"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    key = json.loads(urllib.request.urlopen(req, timeout=60).read())["key"]
    assert key == DEMO_PLAY, key
    page.goto(f"{url}/#league={key}&tab=play")
    page.reload()
    page.wait_for_selector(".order")
    page.get_by_role("button", name="🎯 Ask the Strategist").click()
    page.wait_for_selector(".coach", timeout=120_000)
    page.wait_for_timeout(500)
    page.evaluate("window.scrollTo(0, 0)")
    save("draft")
    page.locator(".coach button").first.click()
    page.wait_for_selector(".coach", state="detached", timeout=60_000)
    while page.locator(".bigplay").count() == 0:
        page.wait_for_timeout(800)
        if page.locator("text=It's your pick!").count():
            page.locator(".icard button").first.click()
            page.wait_for_timeout(1500)
    page.locator(".switch").click()  # autopilot on
    page.wait_for_timeout(800)
    for week in (1, 2):
        page.get_by_role("button", name=f"▶ Play Week {week}").click()
        page.wait_for_selector(f"text=Week {week} results", timeout=180_000)
        page.wait_for_timeout(800)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(3500)  # let the 3D fire pit settle
    save("season")
    save("week_results", ".card:has(h3:text('Week 2 results'))")
    page.get_by_role("button", name="🎯 Ask the Strategist").click()
    page.wait_for_selector(".coach", timeout=120_000)
    page.wait_for_timeout(500)
    save("coach_moves", ".coach")
    print("play-along demo league:", key)


if __name__ == "__main__":
    main()
