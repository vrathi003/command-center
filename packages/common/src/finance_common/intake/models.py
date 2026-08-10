"""Value objects for external transaction intake."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True, slots=True)
class Candidate:
    source: str
    tx_date: date
    amount_paise: int
    direction: Literal["out", "in"]
    suggested_account_id: int | None
    payee: str | None = None
    narration: str | None = None
    suggested_category: str | None = None
    suggested_counter_account_id: int | None = None
    external_key: str | None = None
    confidence: float = 0.0
    raw_payload: dict[str, object] | None = None
    email_staging_id: int | None = None
