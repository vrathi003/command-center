"""Registry of per-bank credit-card statement parsers.

Ported from CardQL (CardQL/src/cardql/parsers/registry.py), adapted to this app's
canonical import-row dict shape (consumed directly by `parse_import_row`) instead of
CardQL's own Transaction/Statement models, and scoped to *within-bank* version
selection only — the bank itself is already known from the card's `issuer` field, so
there's no need for CardQL's cross-bank guessing.
"""

from __future__ import annotations

from collections.abc import Callable

from finance_common.parsing.bank_parsers import (
    axis_v1,
    hdfc_v1,
    hdfc_v2,
    hsbc_v1,
    icici_v1,
    indusind_v1,
    sbi_v1,
)

ParserFunc = Callable[[str], list[dict[str, str]]]

_BANK_PARSERS: dict[str, list[ParserFunc]] = {
    "axis": [axis_v1.parse],
    "hdfc": [hdfc_v1.parse, hdfc_v2.parse],
    "hsbc": [hsbc_v1.parse],
    "icici": [icici_v1.parse],
    "indusind": [indusind_v1.parse],
    "sbi": [sbi_v1.parse],
}

SUPPORTED_BANKS: tuple[str, ...] = tuple(_BANK_PARSERS)

# Free-text `credit_cards.issuer` -> bank slug. "state bank" before "sbi" doesn't matter
# here since both map to the same slug; order only matters between distinct slugs.
_ISSUER_KEYWORDS: list[tuple[str, str]] = [
    ("axis", "axis"),
    ("hdfc", "hdfc"),
    ("hsbc", "hsbc"),
    ("icici", "icici"),
    ("indusind", "indusind"),
    ("sbi", "sbi"),
    ("state bank", "sbi"),
]


def issuer_to_bank_slug(issuer: str | None) -> str | None:
    """Best-effort map of a free-text card issuer to a known bank slug, or None."""
    if not issuer:
        return None
    lower = issuer.strip().lower()
    for keyword, slug in _ISSUER_KEYWORDS:
        if keyword in lower:
            return slug
    return None


def best_parse_for_bank(bank_slug: str | None, text: str) -> list[dict[str, str]]:
    """Try every parser variant registered for this bank; return whichever extracts the
    most transaction rows.

    Returns [] when the bank is unknown or every variant found nothing — a statement with
    genuinely zero transactions this cycle is indistinguishable from an unrecognized
    layout at this layer; callers decide how to handle an empty result (see
    `credit_card_statement_service.py`, which raises a clear error rather than silently
    falling back to a lower-precision heuristic).
    """
    if not bank_slug:
        return []
    variants = _BANK_PARSERS.get(bank_slug, [])
    best: list[dict[str, str]] = []
    for parser in variants:
        try:
            rows = parser(text)
        except Exception:  # noqa: BLE001 - one bad variant must not block the others
            continue
        if len(rows) > len(best):
            best = rows
    return best
