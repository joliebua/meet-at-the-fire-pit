"""Capture app screenshots into docs/screenshots/ for the report and slides (dev tool).

Start the app first (it serves the built UI), then:
    .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m playwright install chromium
    .venv/bin/python scripts/capture_screenshots.py --url http://127.0.0.1:8000

Only reads the app: it opens tabs and clicks a player, but never files disputes or drafts rules.
"""
from pathlib import Path
import argparse

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000")
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860}, device_scale_factor=1)

        def go(tab: str, week: int = 5, wait_for: str = "main .card"):
            page.goto(f"{args.url}/#tab={tab}&week={week}")
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
        browser.close()


if __name__ == "__main__":
    main()
