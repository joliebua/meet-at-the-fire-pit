"""Wikipedia and the Love Island Fandom wiki through the public MediaWiki API (no key needed)."""
from functools import lru_cache
import json
import re
import time

import httpx
import mwparserfromhell

from backend import config
from backend.sources.store import cached_call

WIKIS = {
    "wikipedia": "https://en.wikipedia.org/w/api.php",
    "fandom": "https://loveisland.fandom.com/api.php",
}
PAGE_URL = {
    "wikipedia": "https://en.wikipedia.org/wiki/{}",
    "fandom": "https://loveisland.fandom.com/wiki/{}",
}
WEEK_HEADER = re.compile(r"^!.*\|\s*(Week\s*\d+|Final[^\n|]*)\s*$", re.M)
TAB = re.compile(r"^\|-\|\s*([^=\n]+?)\s*=\s*$", re.M)


def _api(wiki: str, **params) -> dict:
    return json.loads(_api_cached(wiki, json.dumps(params, sort_keys=True)))


@lru_cache(maxsize=256)  # one fetch per page/section per process
def _api_cached(wiki: str, params_json: str) -> str:
    params = json.loads(params_json)

    def live():
        for attempt in range(4):
            r = httpx.get(WIKIS[wiki], params={**params, "format": "json", "formatversion": 2},
                          headers={"User-Agent": config.USER_AGENT}, timeout=20)
            if r.status_code != 429:
                break
            time.sleep(min(int(r.headers.get("Retry-After", "0") or 0) or 2 ** (attempt + 1), 30))
        r.raise_for_status()
        return r.json()
    return json.dumps(cached_call("wiki", {"wiki": wiki, **params}, live))


def page_url(wiki: str, page: str) -> str:
    return PAGE_URL[wiki].format(page.replace(" ", "_"))


def search(wiki: str, query: str, limit: int = 6) -> list[str]:
    data = _api(wiki, action="query", list="search", srsearch=query, srlimit=limit)
    return [hit["title"] for hit in data["query"]["search"]]


def sections(wiki: str, page: str) -> dict[str, str]:
    data = _api(wiki, action="parse", page=page, prop="sections", redirects=1)
    return {s["line"]: s["index"] for s in data["parse"]["sections"]}


def raw_section(wiki: str, page: str, section: str) -> str:
    index = sections(wiki, page).get(section)
    if index is None:
        raise KeyError(f"No section '{section}' on {wiki} page '{page}'")
    data = _api(wiki, action="parse", page=page, prop="wikitext", section=index, redirects=1)
    return data["parse"]["wikitext"]


def cited_links(wikitext: str) -> list[dict]:
    """The news articles a wiki section cites (title + url + site), in order, de-duplicated."""
    links, seen = [], set()
    for tpl in mwparserfromhell.parse(wikitext).filter_templates():
        if not tpl.name.strip().lower().startswith("cite") or not tpl.has("url"):
            continue
        url = tpl.get("url").value.strip_code().strip()
        if url and url not in seen:
            seen.add(url)
            get = lambda p: tpl.get(p).value.strip_code().strip() if tpl.has(p) else ""
            links.append({"url": url, "title": get("title"), "site": get("website") or get("work") or get("publisher")})
    return links


def to_plain(wikitext: str) -> str:
    code = mwparserfromhell.parse(wikitext)
    for tag in code.filter_tags(matches=lambda n: n.tag == "ref"):
        try:
            code.remove(tag)
        except ValueError:
            pass
    text = code.strip_code(normalize=True, collapse=True)
    text = re.sub(r"^\s*[!|]\s*(style|rowspan|colspan|class)=[^|\n]*\|\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*\|[-}]?\s*$", "", text, flags=re.M)
    text = re.sub(r"^\s*\|\|?\s*", "", text, flags=re.M)
    text = re.sub(r"\s*\|\|\s*$", ":", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def episode_guide(wiki: str, page: str, section: str = "Episodes") -> list[dict]:
    """[{episode, week, days, aired}] from a Wikipedia-style episode table."""
    raw = raw_section(wiki, page, section)
    guide, week = [], None
    for chunk in re.split(r"(?=\{\{Episode (?:table/part|list/sublist))", raw):
        if m := re.match(r"\{\{Episode table/part\|subtitle=([^|}]+)", chunk):
            week = m.group(1).strip()
        elif chunk.startswith("{{Episode list/sublist"):
            field = lambda name: (re.search(rf"\|\s*{name}\s*=\s*([^\n]*)", chunk) or [None, ""])[1].strip()
            aired = re.search(r"\{\{Start date\|(\d{4})\|(\d{1,2})\|(\d{1,2})", field("OriginalAirDate"))
            guide.append({"episode": field("EpisodeNumber2") or field("EpisodeNumber"), "week": week,
                          "days": mwparserfromhell.parse(field("Aux1")).strip_code().strip(),
                          "aired": f"{aired[1]}-{int(aired[2]):02d}-{int(aired[3]):02d}" if aired else ""})
    return guide


def split_weeks(wikitext: str) -> dict[str, str]:
    """{'Week 1': wikitext, ...} for a weekly-summary table; Fandom tabs are kept as [Tab] headings."""
    tabs = TAB.split(wikitext)
    chunks = [("", tabs[0])] + list(zip(tabs[1::2], tabs[2::2]))
    weeks: dict[str, str] = {}
    for tab, body in chunks:
        parts = WEEK_HEADER.split(body)
        for label, rows in zip(parts[1::2], parts[2::2]):
            label = re.sub(r"\s+", " ", label).strip()
            weeks[label] = weeks.get(label, "") + (f"\n[{tab}]\n" if tab else "\n") + rows
    return weeks
