"""News recaps: Google News RSS search (no key) and article text extraction."""
from datetime import date
from urllib.parse import quote_plus, urlparse
import ipaddress
import socket

import feedparser
import httpx
import trafilatura

from backend import config
from backend.sources.store import cached_call

MAX_ARTICLE_BYTES = 2_000_000
MAX_ARTICLE_CHARS = 12_000


def search(query: str, after: date | None = None, before: date | None = None, limit: int = 8) -> list[dict]:
    """Headlines, links, outlets and dates for a news search, optionally inside a date window."""
    q = query + (f" after:{after.isoformat()}" if after else "") + (f" before:{before.isoformat()}" if before else "")

    def live():
        url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
        r = httpx.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=20)
        r.raise_for_status()
        feed = feedparser.parse(r.text)
        return [{"title": e.title, "url": e.link, "outlet": getattr(e, "source", {}).get("title", ""),
                 "published": e.get("published", "")} for e in feed.entries]
    return cached_call("news_search", {"q": q}, live)[:limit]


def _public_http_url(url: str) -> bool:
    """Only plain http(s) URLs that resolve to public internet addresses (no localhost / private network)."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def fetch_article(url: str) -> dict:
    """Main text of one article. Never recorded to the snapshot (articles are copyrighted)."""
    def live():
        if not _public_http_url(url):
            raise ValueError(f"Refusing to fetch non-public URL: {url}")
        with httpx.stream("GET", url, headers={"User-Agent": config.USER_AGENT}, timeout=20,
                          follow_redirects=True) as r:
            r.raise_for_status()
            body = b""
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) > MAX_ARTICLE_BYTES:
                    break
            final_url = str(r.url)
        html = body.decode("utf-8", errors="replace")
        text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
        if not text.strip():
            raise ValueError("No readable article text (page needs JavaScript or blocks readers)")
        meta = trafilatura.extract_metadata(html)
        return {"url": final_url, "title": (meta.title if meta else "") or "",
                "published": (meta.date if meta else "") or "", "text": text[:MAX_ARTICLE_CHARS]}
    return cached_call("article", {"url": url}, live, recordable=False)
