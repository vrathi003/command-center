"""Match `template <name> …` / `t <name> …` lines against saved transaction templates."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Protocol

_TEMPLATE_PREFIX_RE = re.compile(r"^\s*(?:template|t)\s+(.+)$", re.IGNORECASE | re.DOTALL)


class HasName(Protocol):
    name: str


def strip_template_prefix(text: str) -> str | None:
    """If the line starts with `template ` or `t `, return the rest; else None."""
    m = _TEMPLATE_PREFIX_RE.match(text.strip())
    return m.group(1).strip() if m else None


def match_template_longest_prefix(
    rest: str,
    templates: list[HasName],
) -> tuple[Any, str] | None:
    """Match `rest` against template names (longest name first). Returns (template, remainder)."""
    r = rest.strip()
    if not r or not templates:
        return None
    for t in sorted(templates, key=lambda x: len(x.name), reverse=True):
        if not t.name:
            continue
        if r.lower() == t.name.lower():
            return t, ""
        prefix = t.name.lower() + " "
        if r.lower().startswith(prefix):
            rem = r[len(t.name) :].strip()
            return t, rem
    # Whole-string fuzzy fallback (single-token short names)
    if len(templates) == 1:
        only = templates[0]
        ratio = SequenceMatcher(None, r.lower(), only.name.lower()).ratio()
        if ratio >= 0.6:
            return only, ""
    best_score = 0.0
    best_t: Any | None = None
    for t in templates:
        if not t.name:
            continue
        ratio = SequenceMatcher(None, r.lower(), t.name.lower()).ratio()
        if ratio > best_score:
            best_score = ratio
            best_t = t
    if best_t is not None and best_score >= 0.82:
        return best_t, ""
    return None
