"""Convert legacy transaction rows into ledger posting plans without applying them."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal

import aiosqlite

from finance_common.intake.models import Candidate
from finance_common.intake.posting_plan import IntakePlanError, plan_postings, plan_transfer
from finance_common.ledger.models import PostTransactionInput
from finance_common.migration.resolve import resolve_account_id
from finance_common.repositories.transactions import TransactionRow

LegacyRow = TransactionRow | Mapping[str, object]


@dataclass(frozen=True)
class PlannedMigrate:
    kind: Literal["post", "quarantine", "skip_deleted", "noop"]
    external_key: str | None
    post_input: PostTransactionInput | None
    quarantine_reason: str | None
    raw_payload: dict[str, object] | None
    legacy_ids: tuple[int, ...]


def _payload(row: LegacyRow) -> dict[str, object]:
    if isinstance(row, Mapping):
        return dict(row)
    return asdict(row)


def _text(payload: Mapping[str, object], name: str) -> str | None:
    value = payload.get(name)
    return str(value) if value is not None else None


def _int(payload: Mapping[str, object], name: str) -> int | None:
    value = payload.get(name)
    return int(str(value)) if value is not None else None


def _required_int(payload: Mapping[str, object], name: str) -> int:
    value = _int(payload, name)
    if value is None:
        raise ValueError(f"Legacy transaction row has no {name}")
    return value


def _date(payload: Mapping[str, object]) -> date:
    value = payload["date"]
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _is_deleted(payload: Mapping[str, object]) -> bool:
    value = payload.get("is_deleted")
    return value is True or (type(value) is int and value == 1) or value == "1"


def _planned(
    *,
    kind: Literal["post", "quarantine", "skip_deleted", "noop"],
    external_key: str | None,
    legacy_ids: tuple[int, ...],
    post_input: PostTransactionInput | None = None,
    quarantine_reason: str | None = None,
    raw_payload: dict[str, object] | None = None,
) -> PlannedMigrate:
    return PlannedMigrate(
        kind=kind,
        external_key=external_key,
        post_input=post_input,
        quarantine_reason=quarantine_reason,
        raw_payload=raw_payload,
        legacy_ids=legacy_ids,
    )


async def _resolve(payload: Mapping[str, object], conn: aiosqlite.Connection) -> int | None:
    return await resolve_account_id(
        conn,
        account_id=_int(payload, "account_id"),
        account_name=_text(payload, "account"),
    )


async def plan_legacy_row(
    conn: aiosqlite.Connection,
    row: LegacyRow,
    *,
    paired_sibling: LegacyRow | None = None,
    already_posted: set[str],
) -> PlannedMigrate:
    """Plan one legacy transaction, quarantining records that cannot be safely posted."""
    payload = _payload(row)
    legacy_id = _int(payload, "id")
    if legacy_id is None:
        raise ValueError("Legacy transaction row has no id")
    legacy_ids = (legacy_id,)

    if _is_deleted(payload):
        return _planned(kind="skip_deleted", external_key=None, legacy_ids=legacy_ids)

    transaction_type = _text(payload, "transaction_type") or "debit"
    pair_id = _text(payload, "transfer_pair_id")
    external_key = (
        f"legacy:pair:{pair_id}"
        if transaction_type == "transfer" and pair_id
        else f"legacy:txn:{legacy_id}"
    )
    if external_key in already_posted:
        return _planned(kind="noop", external_key=external_key, legacy_ids=legacy_ids)

    if transaction_type == "transfer":
        if paired_sibling is None:
            return _planned(
                kind="quarantine",
                external_key=external_key,
                legacy_ids=legacy_ids,
                quarantine_reason="legacy_migration:orphan_transfer",
                raw_payload=payload,
            )
        sibling_payload = _payload(paired_sibling)
        sibling_id = _int(sibling_payload, "id")
        if sibling_id is None:
            raise ValueError("Legacy transfer sibling has no id")
        from_account_id = await _resolve(payload, conn)
        to_account_id = await _resolve(sibling_payload, conn)
        transfer_ids = (legacy_id, sibling_id)
        if (
            _text(sibling_payload, "transaction_type") != "transfer"
            or _text(sibling_payload, "transfer_pair_id") != pair_id
            or _is_deleted(sibling_payload)
        ):
            return _planned(
                kind="quarantine",
                external_key=external_key,
                legacy_ids=transfer_ids,
                quarantine_reason="legacy_migration:invalid_transfer",
                raw_payload=payload,
            )
        if from_account_id is None or to_account_id is None:
            return _planned(
                kind="quarantine",
                external_key=external_key,
                legacy_ids=transfer_ids,
                quarantine_reason="legacy_migration:missing_account",
                raw_payload=payload,
            )
        try:
            post_input = await plan_transfer(
                conn,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                amount_paise=_required_int(payload, "amount_paise"),
                tx_date=_date(payload),
                source=_text(payload, "source") or "migration",
                payee=_text(payload, "merchant"),
                notes=_text(payload, "notes"),
                external_key=external_key,
            )
        except IntakePlanError:
            return _planned(
                kind="quarantine",
                external_key=external_key,
                legacy_ids=transfer_ids,
                quarantine_reason="legacy_migration:missing_account",
                raw_payload=payload,
            )
        return _planned(
            kind="post",
            external_key=external_key,
            post_input=post_input,
            legacy_ids=transfer_ids,
        )

    account_id = await _resolve(payload, conn)
    if account_id is None:
        return _planned(
            kind="quarantine",
            external_key=external_key,
            legacy_ids=legacy_ids,
            quarantine_reason="legacy_migration:missing_account",
            raw_payload=payload,
        )

    candidate = Candidate(
        source=_text(payload, "source") or "migration",
        tx_date=_date(payload),
        amount_paise=_required_int(payload, "amount_paise"),
        direction="in" if transaction_type == "credit" else "out",
        suggested_account_id=account_id,
        payee=_text(payload, "merchant"),
        narration=_text(payload, "notes"),
        suggested_category=_text(payload, "category"),
        external_key=external_key,
        raw_payload=payload,
    )
    try:
        post_input = await plan_postings(conn, candidate)
    except IntakePlanError:
        return _planned(
            kind="quarantine",
            external_key=external_key,
            legacy_ids=legacy_ids,
            quarantine_reason="legacy_migration:missing_account",
            raw_payload=payload,
        )
    return _planned(
        kind="post",
        external_key=external_key,
        post_input=post_input,
        legacy_ids=legacy_ids,
    )
