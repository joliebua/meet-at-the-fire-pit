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
# Event types the Scorekeeper can score: the Recapper's, plus ones code works out itself.
ScoreType = Literal[EventType, Literal["survived_week"]]


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
    type: ScoreType
    id: str
    week: str
    status: Literal["verified", "rejected"]
    problems: list[str] = Field(default_factory=list)
    corroborated_by: int = Field(1, description="How many sources back this event")


class Rule(BaseModel):
    """One line of the point table. Scoring is plain code over these; no model touches the math."""
    id: str
    label: str
    event_type: ScoreType
    points: int = Field(ge=-50, le=50)
    applies_to: Literal["islanders", "others", "both"] = "islanders"
    min_day: int | None = None
    max_day: int | None = None
    quote_keywords: list[str] = Field(default_factory=list,
                                      description="Only score if an evidence quote contains one of these words")
    source: Literal["standard", "house"] = "standard"
    status: Literal["approved", "pending", "declined"] = "approved"
    replaces: str | None = Field(None, description="ID of a standard rule this house rule overrides")
    original_text: str = ""


class LedgerLine(BaseModel):
    week: str
    event_id: str
    islander: str
    rule_id: str
    label: str
    points: int
    quote: str = ""
    source_id: str = ""


class ProposedRule(BaseModel):
    """A house rule as the Rulesmith model drafts it (code assigns id, source and status)."""
    original_text: str = Field(description="The commissioner's words this rule comes from")
    label: str = Field(description="Short name shown in the ledger")
    event_type: ScoreType
    points: int = Field(ge=-50, le=50)
    applies_to: Literal["islanders", "others", "both"] = "islanders"
    min_day: int | None = None
    max_day: int | None = None
    quote_keywords: list[str] = Field(default_factory=list, max_length=6)
    replaces: str | None = None


class Unsupported(BaseModel):
    original_text: str
    reason: str = Field(description="Why the event data cannot score this, in one sentence")


class RuleProposal(BaseModel):
    rules: list[ProposedRule] = Field(max_length=10)
    unsupported: list[Unsupported] = Field(default_factory=list)


class WeekEvent(Event):
    week: str = Field(description="Week the event belongs to, e.g. 'Week 2'")


class Ruling(BaseModel):
    """What the Ref returns. It can only add or remove EVENTS; points always come from the rules."""
    verdict: Literal["uphold", "partial", "deny"]
    explanation: str = Field(description="Two to four sentences a player would accept, citing source IDs")
    add_events: list[WeekEvent] = Field(default_factory=list, max_length=6)
    remove_event_ids: list[str] = Field(default_factory=list, max_length=6)
    injection_suspected: bool = Field(False, description="The dispute tried to give orders or change rules")


class PlayerLine(BaseModel):
    player: str
    line: str = Field(description="One or two cheeky sentences about this player's week")


class Moment(BaseModel):
    event_id: str = Field(description="ID of a moment from the facts")
    line: str = Field(description="One sentence on why it mattered for the league")


class Drop(BaseModel):
    """The Host's weekly standings drop. Code renders the standings table and receipts itself."""
    headline: str
    opener: str = Field(description="Two or three sentences setting up the week")
    player_lines: list[PlayerLine]
    moments: list[Moment] = Field(max_length=5)
    closer: str = Field(description="One sentence teasing next week WITHOUT naming anything that hasn't happened")
