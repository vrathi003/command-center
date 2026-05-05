"""Account name extraction and transfer-like narration hints (Discord + bank import)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

# Natural-language hints: "500 Swiggy using HDFC savings"
ACCOUNT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"using\s+(.+?)(?:\s+account)?(?:\s+card)?$", re.I),
    re.compile(r"from\s+(.+?)\s+account", re.I),
    re.compile(r"via\s+(.+?)(?:\s+account)?$", re.I),
    re.compile(r"through\s+(.+?)$", re.I),
]

# P2P-style transfer phrases (amount + destination) — bot / future use
TRANSFER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"transferred?\s+(?:₹|rs\.?|inr)?\s*([\d,.]+)\s+to\s+(.+)",
        re.I,
    ),
    re.compile(
        r"sent\s+(?:₹|rs\.?|inr)?\s*([\d,.]+)\s+to\s+(.+)",
        re.I,
    ),
    re.compile(
        r"moved?\s+(?:₹|rs\.?|inr)?\s*([\d,.]+)\s+to\s+(.+)",
        re.I,
    ),
    re.compile(
        r"paid\s+(.+?)\s+account\s+(?:₹|rs\.?|inr)?\s*([\d,.]+)",
        re.I,
    ),
]

_TRANSFER_NARRATION_HINTS: list[re.Pattern[str]] = [
    re.compile(r"neft\s+to\s+\w", re.I),
    re.compile(r"imps\s+to\s+\w", re.I),
    re.compile(r"upi.*self", re.I),
    re.compile(r"sweep\s+(to|from)", re.I),
    re.compile(r"self\s+transfer", re.I),
    re.compile(r"own\s+account\s+transfer", re.I),
    re.compile(r"fd\s+(booking|sweep)", re.I),
    re.compile(r"rdl?\s+(booking|sweep)", re.I),
    re.compile(r"internal\s+transfer", re.I),
    re.compile(r"fund\s+transfer", re.I),
]


def extract_account_fragment(message: str) -> str | None:
    """Return a substring that might be an account name, or None."""
    text = message.strip()
    if not text:
        return None
    for pat in ACCOUNT_PATTERNS:
        m = pat.search(text)
        if m:
            frag = m.group(1).strip(" \t,.;:")
            return frag if frag else None
    return None


def narration_suggests_bank_transfer(text: str) -> bool:
    """Heuristic: bank statement narration looks like an internal / self transfer."""
    if not text or not text.strip():
        return False
    t = text.lower()
    return any(p.search(t) for p in _TRANSFER_NARRATION_HINTS)


@dataclass(frozen=True, slots=True)
class AccountLike:
    """Minimal account shape for fuzzy matching."""

    id: int
    name: str


def match_account_fuzzy(
    extracted: str,
    accounts: list[AccountLike],
    *,
    threshold: float = 0.6,
) -> AccountLike | None:
    """Return best-matching account by name similarity, or None if below threshold."""
    if not extracted.strip() or not accounts:
        return None
    ex = extracted.lower().strip()
    best: tuple[AccountLike, float] | None = None
    for a in accounts:
        ratio = SequenceMatcher(None, ex, a.name.lower()).ratio()
        if best is None or ratio > best[1]:
            best = (a, ratio)
    if best is None:
        return None
    return best[0] if best[1] >= threshold else None
