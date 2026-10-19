"""Data shapes passed between agents."""
from typing import Literal

from pydantic import BaseModel, Field

SourceKind = Literal["wiki", "news_headline", "article", "web_search"]


class Source(BaseModel):
    """One piece of outside evidence, exactly as the tools fetched it (never written by a model)."""
    id: str
    kind: SourceKind
    title: str
    url: str
    outlet: str = ""
    published: str = ""
    text: str = ""
    flags: list[str] = Field(default_factory=list, description="Injection-looking lines found by the cleaner")


class ScoutReport(BaseModel):
    """What the Scout returns: which sources to hand to the Recapper and what is still missing."""
    week: str = Field(description="The week gathered, e.g. 'Week 2'")
    episodes: list[str] = Field(description="Episode numbers this week covers")
    source_ids: list[str] = Field(description="IDs of the sources worth reading, best first")
    gaps: list[str] = Field(default_factory=list, description="Things you could not find a source for")
    notes: str = Field("", description="One or two sentences on coverage; no episode facts")


class SourceBundle(BaseModel):
    """Scout output after code checks it: the real sources behind the chosen IDs."""
    show: str
    season: str
    week: str
    episodes: list[str]
    sources: list[Source]
    gaps: list[str]
    notes: str
    rejected_ids: list[str] = Field(default_factory=list, description="IDs the model named that do not exist")
