"""Keep private information away from the model and the logs.

Anything a person types (disputes, house rules) passes through redact() before it is sent to the model or
saved. Emails, phone numbers, card numbers, SSNs, IP addresses and API-key-like strings are replaced with
labelled placeholders, so the rest of the message still makes sense.
"""
import re

PATTERNS = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")),
    ("api key", re.compile(r"\b(sk|pk|rk|key|pt)[-_][A-Za-z0-9_-]{12,}\b|\b[A-Za-z0-9]{32,}\b")),
    ("card number", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"(?<!\w)(\+?\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\w)")),
    ("IP address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total, alt = total + n, not alt
    return total % 10 == 0


def redact(text: str) -> tuple[str, list[str]]:
    """(text with private details replaced, list of what kinds were removed)."""
    found: list[str] = []

    def sub(kind: str, pattern: re.Pattern, s: str) -> str:
        def repl(m: re.Match) -> str:
            if kind == "card number" and not _luhn_ok(re.sub(r"\D", "", m.group(0))):
                return m.group(0)  # long number that isn't a card (e.g. points or a year range)
            found.append(kind)
            return f"[{kind} removed]"
        return pattern.sub(repl, s)

    for kind, pattern in PATTERNS:
        text = sub(kind, pattern, text)
    return text, found
