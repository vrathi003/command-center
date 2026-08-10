"""Value objects used by the double-entry ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class NewPosting:
    """A signed posting to create with a ledger transaction."""

    account_id: int
    amount_paise: int
    category: str | None = None


@dataclass(frozen=True, slots=True)
class PostTransactionInput:
    """The complete request for an atomic ledger transaction."""

    tx_date: date
    postings: tuple[NewPosting, ...]
    payee: str | None = None
    notes: str | None = None
    tags: str | None = None
    source: str = "manual"
    external_key: str | None = None


@dataclass(frozen=True, slots=True)
class PostedPosting:
    """A posting persisted in the ledger."""

    id: int
    account_id: int
    amount_paise: int
    category: str | None


@dataclass(frozen=True, slots=True)
class PostedTransaction:
    """A ledger transaction with its immutable postings."""

    id: int
    date: date
    payee: str | None
    notes: str | None
    tags: str | None
    source: str
    status: str
    external_key: str | None
    postings: tuple[PostedPosting, ...]
