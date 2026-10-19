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


EventType = Literal[
    "entered_villa",   # arrived (original islander or bombshell)
    "re_entered",      # came back after being dumped
    "coupled_up",      # formed a new couple
    "stayed_coupled",  # couple survived a recoupling together
    "left_single",     # left single / vulnerable at a recoupling
    "given_power",     # got a choice others did not (first pick, chose who to save or dump)
    "won_challenge",   # won (or was on the winning team of) a challenge
    "date",            # went on a date
    "kiss",            # kissed someone (challenge kisses count)
    "argument",        # fight, confrontation or major drama
    "dumped",          # eliminated
    "left_villa",      # walked or was removed (not dumped)
    "finalist",        # reached the final
    "winner",          # won the season
]


class Evidence(BaseModel):
    source_id: str = Field(description="ID of the source, e.g. 'S2'")
    quote: str = Field(description="Words copied EXACTLY from that source (one sentence or part of one)")


class Event(BaseModel):
    type: EventType
    islanders: list[str] = Field(description="First names of the islanders this event is about (they score)")
    others: list[str] = Field(default_factory=list, description="Other islanders involved who do not score")
    day: int | None = Field(None, description="Villa day number if the source says it")
    detail: str = Field("", description="A few words, e.g. 'love-letter recoupling' or 'Sweet as Pie'")
    evidence: list[Evidence] = Field(min_length=1)


class RecapDraft(BaseModel):
    """What the Recapper model returns."""
    events: list[Event]


class CheckedEvent(Event):
    """An event after code checked it. Only status 'verified' events can score."""
    id: str
    week: str
    status: Literal["verified", "rejected"]
    problems: list[str] = Field(default_factory=list)
    corroborated_by: int = Field(1, description="How many sources back this event")
