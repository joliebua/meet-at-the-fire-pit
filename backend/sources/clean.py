"""Strip what a reader would never see before any model reads outside text, and flag injection-looking lines."""
import re
import unicodedata

INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿­]")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# Text that talks to an AI instead of describing an episode.
INJECTION_HINTS = re.compile(
    r"(ignore (all |any |the )?(previous|prior|above) (instructions|rules)|system prompt|you are (now )?an? (ai|assistant)"
    r"|award .{0,40}\d+ points|new instructions|developer message|disregard .{0,30}rules)",
    re.I,
)


def clean_text(text: str) -> tuple[str, dict]:
    """Return (clean text, report of what was removed or flagged)."""
    report = {"invisible_chars": len(INVISIBLE.findall(text)), "html_comments": len(HTML_COMMENT.findall(text))}
    text = HTML_COMMENT.sub(" ", INVISIBLE.sub("", text))
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    report["flagged_lines"] = [line.strip()[:200] for line in text.splitlines() if INJECTION_HINTS.search(line)]
    return text, report
