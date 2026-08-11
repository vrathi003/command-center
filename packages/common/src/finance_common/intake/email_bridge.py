"""Hybrid email staging → intake bridge for approve and transfer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import aiosqlite

from finance_common.intake.dedupe import find_soft_duplicate, make_external_key
from finance_common.intake.models import Candidate
from finance_common.intake.posting_plan import IntakePlanError, plan_postings, plan_transfer
from finance_common.intake.service import Decision, ingest
from finance_common.ledger import service as ledger_service
from finance_common.ledger.errors import LedgerError
from finance_common.project_config import load_project_config
from finance_common.repositories import email_staging as staging_repo
from finance_common.repositories.domain_events import append_event
from finance_common.repositories.email_staging import StagedEmailRow
from finance_common.repositories.intake_candidates import save_candidate


class EmailStagingNotFoundError(LookupError):
    """Staging row does not exist."""


class EmailStagingStatusError(ValueError):
    """Staging row is not approvable in its current status."""


@dataclass(frozen=True, slots=True)
class ApproveOverrides:
    parsed_date: str | None = None
    parsed_amount_paise: int | None = None
    parsed_merchant: str | None = None
    parsed_category: str | None = None
    parsed_payment_mode: str | None = None
    parsed_transaction_type: str | None = None
    account_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class TransferOverrides:
    from_account_id: int | None = None
    to_account_id: int | None = None
    tx_date: str | None = None
    amount_paise: int | None = None
    notes: str | None = None


def _assert_approvable(row: StagedEmailRow, *, force: bool) -> None:
    if row.status == "pending":
        return
    if row.status == "quarantined" and force:
        return
    raise EmailStagingStatusError(
        f"Staging item {row.id} has status {row.status!r} and cannot be approved"
    )


def _resolve_staging_fields(
    row: StagedEmailRow, overrides: ApproveOverrides
) -> tuple[str, int, str | None, str, str, int]:
    tx_date_str = overrides.parsed_date or row.parsed_date
    amount_paise = (
        overrides.parsed_amount_paise
        if overrides.parsed_amount_paise is not None
        else row.parsed_amount_paise
    )
    merchant = (
        overrides.parsed_merchant if overrides.parsed_merchant is not None else row.parsed_merchant
    )
    category = (
        overrides.parsed_category
        if overrides.parsed_category is not None
        else row.parsed_category or "Other"
    )
    tx_type = (
        overrides.parsed_transaction_type
        if overrides.parsed_transaction_type is not None
        else row.parsed_transaction_type or "debit"
    )
    account_id = overrides.account_id if overrides.account_id is not None else row.suggested_account_id

    if not tx_date_str:
        raise ValueError("date is required to approve")
    if amount_paise is None or amount_paise <= 0:
        raise ValueError("amount is required to approve")
    if account_id is None:
        raise ValueError("account_id is required to approve")

    return tx_date_str, amount_paise, merchant, category, tx_type, account_id


def _build_candidate(
    row: StagedEmailRow,
    *,
    staging_id: int,
    overrides: ApproveOverrides,
    tx_date: date,
    amount_paise: int,
    merchant: str | None,
    category: str,
    tx_type: str,
    account_id: int,
) -> Candidate:
    direction: Literal["out", "in"] = "in" if tx_type == "credit" else "out"
    narration = overrides.notes or row.raw_snippet or merchant
    return Candidate(
        source="email",
        tx_date=tx_date,
        amount_paise=amount_paise,
        direction=direction,
        suggested_account_id=account_id,
        payee=merchant,
        narration=narration,
        suggested_category=category,
        external_key=make_external_key(
            source="gmail",
            provider_id=row.gmail_message_id,
            date=tx_date.isoformat(),
            amount_paise=amount_paise,
            narration=narration or "",
            account_id=account_id,
        ),
        confidence=1.0,
        email_staging_id=staging_id,
    )


async def _quarantine_transfer(
    conn: aiosqlite.Connection,
    candidate: Candidate,
    reason: str,
    *,
    debit_id: int,
    credit_id: int,
) -> int:
    candidate_id = await save_candidate(
        conn,
        candidate,
        status="pending",
        quarantine_reason=reason,
    )
    await append_event(
        conn,
        event_type="intake.quarantine_created",
        payload={
            "candidate_id": candidate_id,
            "reason": reason,
            "source": candidate.source,
            "external_key": candidate.external_key,
        },
    )
    await staging_repo.set_status(
        conn,
        debit_id,
        "quarantined",
        intake_candidate_id=candidate_id,
    )
    await staging_repo.set_status(
        conn,
        credit_id,
        "quarantined",
        intake_candidate_id=candidate_id,
    )
    return candidate_id


async def approve_staged_item(
    conn: aiosqlite.Connection,
    *,
    staging_id: int,
    overrides: ApproveOverrides,
    force: bool,
) -> StagedEmailRow:
    """Approve one staged email through ingest or forced ledger post."""
    row = await staging_repo.get_staged(conn, staging_id)
    if row is None:
        raise EmailStagingNotFoundError(f"Staging item {staging_id} not found")
    _assert_approvable(row, force=force)

    tx_date_str, amount_paise, merchant, category, tx_type, account_id = _resolve_staging_fields(
        row, overrides
    )
    try:
        tx_date = date.fromisoformat(tx_date_str)
    except ValueError as exc:
        raise ValueError("invalid parsed_date") from exc

    candidate = _build_candidate(
        row,
        staging_id=staging_id,
        overrides=overrides,
        tx_date=tx_date,
        amount_paise=amount_paise,
        merchant=merchant,
        category=category,
        tx_type=tx_type,
        account_id=account_id,
    )

    if not force:
        decision, result_id = await ingest(conn, candidate)
        if decision in (Decision.POSTED, Decision.NOOP):
            assert result_id is not None
            await staging_repo.set_status(
                conn,
                staging_id,
                "approved",
                ledger_transaction_id=result_id,
            )
        else:
            assert result_id is not None
            await staging_repo.set_status(
                conn,
                staging_id,
                "quarantined",
                intake_candidate_id=result_id,
            )
    else:
        try:
            posting_plan = await plan_postings(conn, candidate)
            ledger_transaction_id = await ledger_service.post(conn, posting_plan)
        except (IntakePlanError, LedgerError) as exc:
            raise ValueError(str(exc)) from exc

        await save_candidate(
            conn,
            candidate,
            status="posted",
            ledger_transaction_id=ledger_transaction_id,
        )
        await staging_repo.set_status(
            conn,
            staging_id,
            "approved",
            ledger_transaction_id=ledger_transaction_id,
        )

    updated = await staging_repo.get_staged(conn, staging_id)
    assert updated is not None
    return updated


async def approve_as_transfer(
    conn: aiosqlite.Connection,
    *,
    debit_id: int,
    credit_id: int,
    overrides: TransferOverrides,
    force: bool,
) -> tuple[StagedEmailRow, StagedEmailRow, int]:
    """Approve two staged emails as one transfer."""
    debit_row = await staging_repo.get_staged(conn, debit_id)
    credit_row = await staging_repo.get_staged(conn, credit_id)

    if debit_row is None or credit_row is None:
        raise EmailStagingNotFoundError("One or both staging items not found")
    if debit_id == credit_id:
        raise ValueError("debit_id and credit_id must be different")

    _assert_approvable(debit_row, force=force)
    _assert_approvable(credit_row, force=force)

    amount_paise = (
        overrides.amount_paise
        or debit_row.parsed_amount_paise
        or credit_row.parsed_amount_paise
    )
    if not amount_paise or amount_paise <= 0:
        raise ValueError("amount_paise is required")

    date_str = overrides.tx_date or debit_row.parsed_date or credit_row.parsed_date
    if not date_str:
        raise ValueError("tx_date is required")
    try:
        tx_date = date.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError("invalid tx_date") from exc

    from_account_id = overrides.from_account_id or debit_row.suggested_account_id
    to_account_id = overrides.to_account_id or credit_row.suggested_account_id
    if not from_account_id or not to_account_id:
        raise ValueError("from_account_id and to_account_id are required")
    if from_account_id == to_account_id:
        raise ValueError("from_account_id and to_account_id must be different accounts")

    payee = debit_row.parsed_merchant or credit_row.parsed_merchant
    external_key = make_external_key(
        source="gmail",
        provider_id=f"{debit_row.gmail_message_id}:{credit_row.gmail_message_id}",
        date=tx_date.isoformat(),
        amount_paise=amount_paise,
        narration=payee or "",
        account_id=from_account_id,
    )

    if not force:
        config = await load_project_config(conn)
        duplicate_id = await find_soft_duplicate(
            conn,
            account_id=from_account_id,
            amount_paise=amount_paise,
            tx_date=tx_date,
            payee=payee,
            window_days=config.intake_duplicate_date_window_days,
        )
        if duplicate_id is not None:
            candidate = Candidate(
                source="email",
                tx_date=tx_date,
                amount_paise=amount_paise,
                direction="out",
                suggested_account_id=from_account_id,
                suggested_counter_account_id=to_account_id,
                payee=payee,
                narration=overrides.notes,
                external_key=external_key,
                confidence=1.0,
                email_staging_id=debit_id,
            )
            await _quarantine_transfer(
                conn,
                candidate,
                "possible_duplicate",
                debit_id=debit_id,
                credit_id=credit_id,
            )
            updated_debit = await staging_repo.get_staged(conn, debit_id)
            updated_credit = await staging_repo.get_staged(conn, credit_id)
            assert updated_debit and updated_credit
            return updated_debit, updated_credit, 0

    try:
        ledger_transaction_id = await ledger_service.post(
            conn,
            await plan_transfer(
                conn,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                amount_paise=amount_paise,
                tx_date=tx_date,
                source="email",
                payee=payee,
                notes=overrides.notes,
                external_key=external_key,
            ),
        )
    except (IntakePlanError, LedgerError) as exc:
        raise ValueError(str(exc)) from exc

    transfer_candidate = Candidate(
        source="email",
        tx_date=tx_date,
        amount_paise=amount_paise,
        direction="out",
        suggested_account_id=from_account_id,
        suggested_counter_account_id=to_account_id,
        payee=payee,
        narration=overrides.notes,
        external_key=external_key,
        confidence=1.0,
        email_staging_id=debit_id,
    )
    await save_candidate(
        conn,
        transfer_candidate,
        status="posted",
        ledger_transaction_id=ledger_transaction_id,
    )

    await staging_repo.set_status(
        conn,
        debit_id,
        "approved",
        ledger_transaction_id=ledger_transaction_id,
    )
    await staging_repo.set_status(
        conn,
        credit_id,
        "approved",
        ledger_transaction_id=ledger_transaction_id,
    )

    updated_debit = await staging_repo.get_staged(conn, debit_id)
    updated_credit = await staging_repo.get_staged(conn, credit_id)
    assert updated_debit and updated_credit
    return updated_debit, updated_credit, ledger_transaction_id
