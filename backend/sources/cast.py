"""The season's cast from the Wikipedia 'Islanders' table: names, villa stints and final status.

Used two ways: the Recapper must use these names (no invented islanders), and the table is the
ground truth for checking entered / dumped / final-placement events.
"""
import re

import mwparserfromhell

from backend.sources import wiki


def _cell(text: str) -> str:
    code = mwparserfromhell.parse(text)
    for tpl in code.filter_templates(recursive=False):
        name = str(tpl.name).strip().lower()
        if name in ("efn", "efn-ua", "notetag"):
            code.remove(tpl)
        else:  # {{won|'''Winner'''}} -> Winner, {{Runner-up}} -> Runner-up, {{eliminated|Dumped}} -> Dumped
            label = tpl.params[0].value.strip_code().strip() if tpl.params else str(tpl.name).strip()
            code.replace(tpl, label)
    for tag in code.filter_tags(matches=lambda n: n.tag == "ref"):
        try:
            code.remove(tag)
        except ValueError:
            pass
    text = code.strip_code().strip()
    text = re.sub(r"^(?:\s*(?:rowspan|colspan|style|nowrap)\s*=?\s*\"?[^|\"]*\"?\s*\|)+", "", text)
    return re.sub(r"\s+", " ", text.replace("nowrap |", "")).strip()


def _day(text: str) -> int | None:
    m = re.search(r"Day (\d+)", text)
    return int(m.group(1)) if m else None


def cast(page: str) -> list[dict]:
    """[{name, first_name, stints: [{entered, exited, status}]}] in table order."""
    raw = wiki.raw_section("wikipedia", page, "Islanders")
    table = raw[raw.index("{|"):raw.index("|}", raw.index("{|"))]
    rows = [r for r in re.split(r"^\|-.*$", table, flags=re.M)[1:] if r.strip()]
    people: list[dict] = []
    for row in rows:
        cells = [c for c in re.split(r"^\|\s?", row, flags=re.M)[1:]]
        cells = [_cell(c) for c in cells]
        if len(cells) >= 6:      # full row: name, age, hometown, entered, exited, status, ref
            name = cells[0]
            people.append({"name": name, "first_name": name.split()[0], "age": cells[1], "hometown": cells[2],
                           "stints": [{"entered": _day(cells[3]), "exited": _day(cells[4]), "status": cells[5]}]})
        elif len(cells) >= 3 and people:  # continuation row of a rowspan: an earlier stint
            people[-1]["stints"].append({"entered": _day(cells[0]), "exited": _day(cells[1]), "status": cells[2]})
    for p in people:
        p["stints"].sort(key=lambda s: s["entered"] or 0)
    return people
