"""Scout agent: gathers the sources for one week of a season, with hard caps on cost and steps.

Usage:
    python -m backend.agents.scout --season love_island_usa_s8 --week 2
    VILLA_SOURCE_MODE=snapshot python -m backend.agents.scout --season love_island_usa_s8 --week 2
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import argparse
import functools
import json
import re

from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from backend import config, llm
from backend.models import ScoutReport, Source, SourceBundle
from backend.sources import clean, news, websearch, wiki
from backend.sources.store import NotInSnapshot

USAGE_LIMITS = UsageLimits(request_limit=12, tool_calls_limit=20, total_tokens_limit=150_000)
MODEL_SETTINGS = ModelSettings(max_tokens=2_000)
WEB_SEARCH_CAP = 1
ARTICLE_CAP = 4
PREVIEW_CHARS = 700


@dataclass
class ScoutDeps:
    season_key: str
    season: dict
    week: str
    sources: dict[str, Source] = field(default_factory=dict)
    known_urls: set[str] = field(default_factory=set)  # URLs a tool returned; the only ones we may fetch
    web_searches: int = 0
    articles: int = 0
    web_search_usage: list[dict] = field(default_factory=list)

    def add(self, **fields) -> Source:
        text, report = clean.clean_text(fields.pop("text", ""))
        src = Source(id=f"S{len(self.sources) + 1}", text=text, flags=report["flagged_lines"], **fields)
        self.sources[src.id] = src
        self.known_urls.add(src.url)
        return src


def seasons() -> dict:
    return json.loads((config.DATA / "seasons.json").read_text())


def _safe(fn):
    """Turn tool failures into a message the model can read instead of crashing the run."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotInSnapshot:
            return {"error": "Not available in offline snapshot mode."}
        except Exception as e:  # network errors, missing sections, bad URLs
            return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    return wrapper


def _headings(text: str) -> list[str]:
    return [h.strip("[]: ") for h in re.findall(r"^(\[[^\]\n]+\]|[A-Z][\w ]{2,30}:)\s*$", text, re.M)]


def _days(text: str) -> list[int]:
    return sorted({int(d) for d in re.findall(r"\bDay (\d{1,2})\b", text)})


agent = Agent(
    deps_type=ScoutDeps,
    output_type=ScoutReport,
    instructions=(config.PROMPTS / "scout.md").read_text(),
    model_settings=MODEL_SETTINGS,
)


@agent.instructions
def season_context(ctx: RunContext[ScoutDeps]) -> str:
    s = ctx.deps.season
    return (f"Show: {s['show']}, season {s['season']}. Week to gather: {ctx.deps.week}.\n"
            f"Known wiki pages: {json.dumps(s['pages'])}. Weekly summary sections: {json.dumps(s['weekly_sections'])}.")


@agent.tool
@_safe
def episode_guide(ctx: RunContext[ScoutDeps]) -> list[dict]:
    """Episodes of this season with week, days and air date (from Wikipedia)."""
    return wiki.episode_guide("wikipedia", ctx.deps.season["pages"]["wikipedia"])


@agent.tool
@_safe
def find_pages(ctx: RunContext[ScoutDeps], query: str) -> dict:
    """Search both wikis ('wikipedia', 'fandom') for page titles."""
    return {w: wiki.search(w, query) for w in wiki.WIKIS}


@agent.tool
@_safe
def list_sections(ctx: RunContext[ScoutDeps], wiki_name: str, page: str) -> list[str]:
    """Section names of a wiki page. wiki_name is 'wikipedia' or 'fandom'."""
    return list(wiki.sections(wiki_name, page))


@agent.tool
@_safe
def read_week(ctx: RunContext[ScoutDeps], wiki_name: str, page: str, section: str, week: str) -> dict:
    """Save one week (e.g. 'Week 2') of a wiki weekly-summary section as a source. Returns a preview."""
    raw = wiki.raw_section(wiki_name, page, section)
    weeks = wiki.split_weeks(raw)
    if week not in weeks:
        return {"error": f"'{week}' not found. Weeks in this section: {list(weeks)}"}
    links = wiki.cited_links(weeks[week])
    ctx.deps.known_urls.update(link["url"] for link in links)
    src = ctx.deps.add(kind="wiki", title=f"{page} - {section} - {week}", url=wiki.page_url(wiki_name, page),
                       outlet=wiki_name, text=wiki.to_plain(weeks[week]))
    return {"source_id": src.id, "chars": len(src.text), "headings": _headings(src.text),
            "days_mentioned": _days(src.text), "preview": src.text[:PREVIEW_CHARS],
            "cited_articles": links, "injection_flags": src.flags}


@agent.tool
@_safe
def search_news(ctx: RunContext[ScoutDeps], query: str, after: str, before: str) -> list[dict]:
    """News headlines for a query between two dates (YYYY-MM-DD). Each headline is saved as a source."""
    end = date.fromisoformat(before) + timedelta(days=3)  # recaps often land a day or two after airing
    out = []
    for item in news.search(query, date.fromisoformat(after), end):
        src = ctx.deps.add(kind="news_headline", title=item["title"], url=item["url"], outlet=item["outlet"],
                           published=item["published"], text=item["title"])
        out.append({"source_id": src.id, "title": item["title"], "outlet": item["outlet"],
                    "published": item["published"]})
    return out


@agent.tool
@_safe
def read_article(ctx: RunContext[ScoutDeps], url: str) -> dict:
    """Fetch an article's text. Only URLs that a tool already returned are allowed."""
    if url not in ctx.deps.known_urls:
        return {"error": "Blocked: this URL did not come from a tool result."}
    if ctx.deps.articles >= ARTICLE_CAP:
        return {"error": f"Article cap reached ({ARTICLE_CAP} per run)."}
    ctx.deps.articles += 1
    a = news.fetch_article(url)
    src = ctx.deps.add(kind="article", title=a["title"], url=a["url"], published=a["published"], text=a["text"])
    return {"source_id": src.id, "chars": len(src.text), "days_mentioned": _days(src.text),
            "preview": src.text[:PREVIEW_CHARS], "injection_flags": src.flags}


@agent.tool
@_safe
def web_search(ctx: RunContext[ScoutDeps], question: str) -> dict:
    """Search the live web for one specific gap. Expensive: capped per run."""
    if ctx.deps.web_searches >= WEB_SEARCH_CAP:
        return {"error": f"Web search cap reached ({WEB_SEARCH_CAP} per run)."}
    ctx.deps.web_searches += 1
    r = websearch.web_search(question)
    ctx.deps.web_search_usage.append(r["usage"])
    ctx.deps.known_urls.update(c["url"] for c in r["citations"])
    src = ctx.deps.add(kind="web_search", title=f"Web search: {question}",
                       url=r["citations"][0]["url"] if r["citations"] else "", text=r["answer"])
    return {"source_id": src.id, "answer": src.text[:1500], "citations": r["citations"], "injection_flags": src.flags}


def run_scout(season_key: str, week: str) -> tuple[SourceBundle, dict]:
    """Run the Scout for one week. Returns (checked source bundle, run log) and saves both to output/runs/."""
    season = seasons()[season_key]
    recorder = llm.UsageRecorder()
    deps = ScoutDeps(season_key, season, week)
    started = datetime.now(timezone.utc)
    result = agent.run_sync(f"Gather the sources for {week}.", deps=deps, model=llm.build_model(recorder),
                            usage_limits=USAGE_LIMITS)
    report = result.output

    chosen = [deps.sources[i] for i in report.source_ids if i in deps.sources]
    bundle = SourceBundle(show=season["show"], season=season["season"], week=report.week or week,
                          episodes=report.episodes, sources=chosen, gaps=report.gaps, notes=report.notes,
                          rejected_ids=[i for i in report.source_ids if i not in deps.sources])

    agent_usage = llm.usage_totals([c["usage"] for c in recorder.calls])
    # In snapshot mode the web search answers are replayed from disk: nothing was spent on them.
    replayed = config.SOURCE_MODE == "snapshot"
    search_usage = llm.usage_totals([] if replayed else deps.web_search_usage,
                                    web_searches=0 if replayed else deps.web_searches)
    search_usage["replayed_from_snapshot"] = deps.web_searches if replayed else 0
    run = {
        "agent": "scout", "season": season_key, "week": week, "mode": config.SOURCE_MODE,
        "started": started.isoformat(timespec="seconds"),
        "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        "usage": {"scout_agent": agent_usage, "web_search_tool": search_usage,
                  "total_cost_usd": round(agent_usage["cost_usd"] + search_usage["cost_usd"], 6)},
        "sources_gathered": len(deps.sources), "sources_chosen": len(chosen),
        "steps": llm.tool_trace(result.all_messages()),
    }
    out = config.OUTPUT / "runs"
    out.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%S")
    slug = week.lower().replace(" ", "")
    (out / f"scout_{season_key}_{slug}_{stamp}.json").write_text(
        json.dumps({"run": run, "bundle": bundle.model_dump()}, indent=1, ensure_ascii=False))
    return bundle, run


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Gather one week of sources for a season.")
    p.add_argument("--season", default="love_island_usa_s8", choices=list(seasons()))
    p.add_argument("--week", default="1", help="Week number, e.g. 2")
    args = p.parse_args()
    bundle, run = run_scout(args.season, f"Week {args.week}")
    print(f"{bundle.week}: {len(bundle.sources)} sources chosen of {run['sources_gathered']} gathered "
          f"in {run['seconds']}s, ${run['usage']['total_cost_usd']}")
    for s in bundle.sources:
        print(f"  {s.id} [{s.kind}] {s.title[:80]}  ({len(s.text)} chars){'  FLAGS' if s.flags else ''}")
    print("  gaps:", bundle.gaps)
    print("  notes:", bundle.notes)
    for step in run["steps"]:
        print("  >", step["tool"], json.dumps(step["arguments"])[:120])
