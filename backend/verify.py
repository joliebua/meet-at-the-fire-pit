"""Code checks on Recapper events. No event scores unless its receipts hold up.

An evidence item is valid when its quote appears word-for-word in the cited source. An event is
verified when at least one evidence item is valid, every name is a real islander, every scoring
islander is named in the quoted sentence and was in the villa at the time (cast table), the sentence
uses words that fit the event type, and any day number is stated in the quote's paragraph and falls
inside the week. Quotes from lines that look like instructions to an AI never count as evidence.
"""
import re
import unicodedata

from backend.models import CheckedEvent, Event, Source
from backend.sources.clean import INJECTION_HINTS

MIN_QUOTE_CHARS = 12
TRANSLATE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(TRANSLATE).lower()
    return re.sub(r"\s+", " ", text).strip()


# Words the quoted sentence must contain for each event type (types not listed are not keyword-checked).
TYPE_WORDS = {
    "entered_villa": r"enter|arriv|bombshell|join|walk(ed)? in",
    "re_entered": r"re-?enter|return|back",
    "coupled_up": r"couple|pair|chose|picked|steal|stole",
    "stayed_coupled": r"remain|stay|kept|together|couple",
    "left_single": r"single|vulnerable|not chosen|no one|nobody",
    "given_power": r"power|chance|choose|chose|pick|save|decide|first",
    "won_challenge": r"\bw[oi]n|winner|victor|first place|came out on top",
    "date": r"\bdate|hideaway",
    "kiss": r"kiss",
    "argument": r"argu|fight|feud|clash|confront|tension|drama|row|blew up|called out",
    "dumped": r"dump|eliminat|sent home|left the (villa|island)",
    "left_villa": r"remov|walk|left|quit|exit",
    "finalist": r"final|finish|place|runner|remaining couples",
    "winner": r"\bw[oi]n|winner|crowned|prize",
}


def _paragraph(source_text: str, quote_n: str) -> str | None:
    """The normalized paragraph (line) of the source that contains the quote, or None if absent."""
    for para in source_text.splitlines():
        if quote_n in norm(para):
            return norm(para)
    return quote_n if quote_n in norm(source_text) else None  # quote spans lines


def _sentence(paragraph: str, quote_n: str) -> str:
    """The sentence(s) of the paragraph that the quote overlaps."""
    start = paragraph.index(quote_n)
    end = start + len(quote_n)
    out, pos = [], 0
    for sent in re.split(r"(?<=[.!?])\s+", paragraph):
        s_start = paragraph.index(sent, pos)
        pos = s_start + len(sent)
        if s_start < end and pos > start:
            out.append(sent)
    return " ".join(out) or quote_n


class Cast:
    def __init__(self, people: list[dict]):
        self.people = people
        self.by_key = {}
        for p in people:
            self.by_key[norm(p["first_name"])] = p["first_name"]
            self.by_key[norm(p["name"])] = p["first_name"]

    def canonical(self, name: str) -> str | None:
        return self.by_key.get(norm(name)) or self.by_key.get(norm(name.split()[0])) if name.strip() else None

    def names(self) -> list[str]:
        return [p["first_name"] for p in self.people]

    def in_villa(self, first_name: str, start: int, end: int) -> bool:
        """Was this islander in the villa at some point between these days? (±1 day for recap timing)"""
        for p in self.people:
            if p["first_name"] == first_name:
                return any((s["entered"] or 0) - 1 <= end and (s["exited"] or 999) + 1 >= start for s in p["stints"])
        return False


def _mentions(paragraph: str, first_name: str) -> bool:
    return re.search(rf"\b{re.escape(norm(first_name))}\b", paragraph) is not None


def check(event: Event, sources: dict[str, Source], cast: Cast, week_days: tuple[int, int] | None) -> list[str]:
    """All problems with one event (empty list = verified). Also canonicalizes names in place."""
    problems = []
    for field in ("islanders", "others"):
        fixed = []
        for name in getattr(event, field):
            canon = cast.canonical(name)
            if canon is None:
                problems.append(f"'{name}' is not an islander this season")
            else:
                fixed.append(canon)
        setattr(event, field, list(dict.fromkeys(fixed)))
    if not event.islanders:
        problems.append("no scoring islander named")

    valid_paragraphs, valid_sentences = [], []
    for ev in event.evidence:
        src = sources.get(ev.source_id)
        quote_n = norm(ev.quote).strip(" .\"'")
        if src is None:
            problems.append(f"{ev.source_id} is not one of the sources")
        elif len(quote_n) < MIN_QUOTE_CHARS:
            problems.append(f"quote from {ev.source_id} is too short to check")
        elif (para := _paragraph(src.text, quote_n)) is None:
            problems.append(f"quote not found word-for-word in {ev.source_id}: \"{ev.quote[:80]}\"")
        elif INJECTION_HINTS.search(para):
            problems.append(f"quote from {ev.source_id} comes from a line that reads like instructions to an AI")
        else:
            valid_paragraphs.append(para)
            valid_sentences.append(_sentence(para, quote_n))
    if not valid_paragraphs:
        return problems + ["no valid evidence"]

    for name in event.islanders:
        if not any(_mentions(s, name) for s in valid_sentences):
            problems.append(f"{name} is not named in the quoted sentence")
    window = (event.day, event.day) if event.day is not None else week_days
    if window:
        for name in event.islanders:
            if not cast.in_villa(name, *window):
                problems.append(f"{name} was not in the villa then (days {window[0]}-{window[1]})")
    words = TYPE_WORDS.get(event.type)
    if words and not any(re.search(words, s) for s in valid_sentences):
        problems.append(f"quoted sentence does not describe a '{event.type}' event")
    if event.day is not None:
        if not any(re.search(rf"\bday {event.day}\b", p) for p in valid_paragraphs):
            problems.append(f"Day {event.day} is not stated in the quoted passage")
        if week_days and not week_days[0] <= event.day <= week_days[1]:
            problems.append(f"Day {event.day} is outside this week (days {week_days[0]}-{week_days[1]})")
    return problems


def check_all(events: list[Event], sources: dict[str, Source], cast: Cast, week: str,
              week_days: tuple[int, int] | None) -> list[CheckedEvent]:
    """Check every event, then merge duplicates (same type, islanders and day) into one corroborated event."""
    merged: dict[tuple, CheckedEvent] = {}
    rejected: list[CheckedEvent] = []
    for event in events:
        event = event.model_copy(deep=True)
        problems = check(event, sources, cast, week_days)
        status = "rejected" if problems else "verified"
        checked = CheckedEvent(**event.model_dump(), id="", week=week, status=status, problems=problems)
        if status == "rejected":
            rejected.append(checked)
            continue
        key = (event.type, frozenset(event.islanders), event.day)
        if key in merged:
            merged[key].evidence += event.evidence
            merged[key].others = list(dict.fromkeys(merged[key].others + event.others))
        else:
            merged[key] = checked
    out = list(merged.values()) + rejected
    for i, e in enumerate(out, 1):
        e.id = f"{week.replace(' ', '').lower()}-e{i}"
        e.corroborated_by = len({ev.source_id for ev in e.evidence if ev.source_id in sources})
    return out


def week_day_range(guide: list[dict], week: str) -> tuple[int, int] | None:
    """(first day, last day) of a week from the episode guide's 'Days 6–7' labels."""
    days = [int(d) for ep in guide if ep["week"] == week for d in re.findall(r"\d+", ep["days"])]
    return (min(days), max(days)) if days else None
