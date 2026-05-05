"""Discord transfer resolution: fuzzy account match + reaction picker state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import Literal

from finance_common.parsing.account_mentions import AccountLike, match_account_fuzzy
from finance_common.parsing.expense_parser import ParsedTransferLine
from finance_common.repositories.accounts import AccountRow

PICK_EMOJIS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")


def accounts_to_likes(accounts: list[AccountRow]) -> list[AccountLike]:
    return [AccountLike(id=a.id, name=a.name) for a in accounts]


def pick_accounts_for_display(
    accounts: list[AccountRow],
    hint: str | None,
    *,
    exclude: set[int] | None = None,
) -> list[AccountRow]:
    """Up to four accounts for reaction picker; optional hint ranks by similarity."""
    ex = exclude or set()
    pool = [a for a in accounts if a.id not in ex]
    if not pool:
        return []
    if hint and hint.strip():
        h = hint.lower().strip()

        def score(a: AccountRow) -> float:
            return SequenceMatcher(None, h, a.name.lower()).ratio()

        pool = sorted(pool, key=score, reverse=True)
    return pool[:4]


@dataclass
class PendingTransfer:
    """Stored while user picks an account via reactions (message_id → pending)."""

    user_id: int
    amount_paise: int
    tx_date: date
    notes: str | None
    source_discord_message_id: str | None
    pick_for: Literal["from", "to"]
    resolved_from_id: int | None
    resolved_from_name: str | None
    resolved_to_id: int | None
    resolved_to_name: str | None
    fragment_from: str | None
    fragment_to: str
    account_ids_shown: list[int]


def resolve_transfer_accounts(
    accounts: list[AccountRow],
    pt: ParsedTransferLine,
) -> tuple[AccountRow | None, AccountRow | None]:
    """Fuzzy-match from/to fragments. Either side may be None if no confident match."""
    likes = accounts_to_likes(accounts)
    by_id = {a.id: a for a in accounts}

    def pick(m: AccountLike | None) -> AccountRow | None:
        return by_id.get(m.id) if m else None

    from_a: AccountRow | None = None
    if pt.fragment_from:
        from_a = pick(match_account_fuzzy(pt.fragment_from, likes))
    to_a = pick(match_account_fuzzy(pt.fragment_to, likes))
    return from_a, to_a
