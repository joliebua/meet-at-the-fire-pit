"""Export slides.html to slides.pdf: one 16:9 page per slide, same design (dev tool, uses Playwright).

    .venv/bin/python scripts/build_slides_pdf.py            # after scripts/build_slides.py
    .venv/bin/python scripts/build_slides_pdf.py --preview DIR   # also save a PNG of every page to DIR

Uses reveal.js's own print mode (?print-pdf), so the PDF matches the deck. Needs an internet connection
(reveal.js and the fonts load from a CDN, exactly as when the deck is opened).
"""
from pathlib import Path
import argparse
import re

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--preview", help="Folder to save a PNG of every page for checking")
    args = p.parse_args()
    src, out = ROOT / "slides.html", ROOT / "slides.pdf"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(src.resolve().as_uri() + "?print-pdf")
        page.wait_for_load_state("networkidle")
        page.wait_for_function("typeof Reveal !== 'undefined' && Reveal.isReady()", timeout=30_000)
        page.wait_for_selector(".pdf-page")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(1500)
        pages = page.locator(".pdf-page")
        n = pages.count()
        if args.preview:
            prev = Path(args.preview)
            prev.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                pages.nth(i).screenshot(path=str(prev / f"slide_{i + 1:02d}.png"))
        page.pdf(path=str(out), width="1280px", height="720px", print_background=True, prefer_css_page_size=True)
        browser.close()
    pdf_pages = len(re.findall(rb"/Type\s*/Page[^s]", out.read_bytes()))
    print(f"slides.pdf written: {pdf_pages} pages from {n} slides, {out.stat().st_size // 1024} KB")
    if pdf_pages != n:
        raise SystemExit("Page count doesn't match the slide count: check for a slide that overflows")


if __name__ == "__main__":
    main()
