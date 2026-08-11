"""HTTP API for reviewing quarantined intake candidates."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, cast

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from finance_api.deps import get_conn
from finance_api.deps_ledger import require_ledger_writes
from finance_api.schemas.intake import (
    ApproveBody,
    CandidateApprovedResponse,
    CandidateRejectedResponse,
    CandidateStatus,
    IntakeCandidateResponse,
)
from finance_common.intake.models import Candidate
from finance_common.intake.posting_plan import IntakePlanError, plan_postings, plan_transfer
from finance_common.ledger import service as ledger_service
from finance_common.ledger.errors import LedgerError
from finance_common.ledger.models import NewPosting, PostTransactionInput
from finance_common.repositories import email_staging as staging_repo
from finance_common.repositories.domain_events import append_event
from finance_common.repositories.intake_candidates import (
    get_candidate,
    list_candidates,
    update_candidate_status,
)

router = APIRouter(prefix="/intake", tags=["intake"])


def _candidate_response(row: dict[str, object]) -> IntakeCandidateResponse:
    return IntakeCandidateResponse.model_validate(row)


def _candidate_from_row(row: dict[str, object], body: ApproveBody) -> Candidate:
    account_id = body.account_id
    if account_id is None:
        account_id = cast(int | None, row["suggested_account_id"])
    counter_account_id = body.counter_account_id
    if counter_account_id is None:
        counter_account_id = cast(int | None, row["suggested_counter_account_id"])
    category = body.category
    if category is None:
        category = cast(str | None, row["suggested_category"])
    return Candidate(
        source=cast(str, row["source"]),
        tx_date=date.fromisoformat(cast(str, row["tx_date"])),
        amount_paise=cast(int, row["amount_paise"]),
        direction=cast(Literal["out", "in"], row["direction"]),
        suggested_account_id=account_id,
        payee=cast(str | None, row["payee"]),
        narration=cast(str | None, row["narration"]),
        suggested_category=category,
        suggested_counter_account_id=counter_account_id,
        external_key=cast(str | None, row["external_key"]),
        confidence=cast(float, row["confidence"]),
    )


async def _pending_candidate(
    conn: aiosqlite.Connection, candidate_id: int
) -> dict[str, object]:
    candidate = await get_candidate(conn, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Intake candidate not found")
    if candidate["status"] != "pending":
        raise HTTPException(status_code=409, detail="Intake candidate is no longer pending")
    return candidate


async def _linked_staging_rows(
    conn: aiosqlite.Connection,
    candidate_id: int,
    email_staging_id: int | None,
) -> list[int]:
    """Collect staging row ids linked directly or via intake_candidate_id."""
    row_ids: list[int] = []
    seen: set[int] = set()
    if email_staging_id is not None:
        row = await staging_repo.get_staged(conn, email_staging_id)
        if row is not None:
            row_ids.append(row.id)
            seen.add(row.id)
    for row in await staging_repo.get_by_intake_candidate_id(conn, candidate_id):
        if row.id not in seen:
            row_ids.append(row.id)
            seen.add(row.id)
    return row_ids


async def _sync_staging_on_candidate_approve(
    conn: aiosqlite.Connection,
    candidate_id: int,
    *,
    email_staging_id: int | None,
    ledger_transaction_id: int,
) -> None:
    for staging_id in await _linked_staging_rows(conn, candidate_id, email_staging_id):
        await staging_repo.set_status(
            conn,
            staging_id,
            "approved",
            ledger_transaction_id=ledger_transaction_id,
        )


async def _sync_staging_on_candidate_reject(
    conn: aiosqlite.Connection,
    candidate_id: int,
    *,
    email_staging_id: int | None,
) -> None:
    for staging_id in await _linked_staging_rows(conn, candidate_id, email_staging_id):
        await staging_repo.set_status(conn, staging_id, "rejected")


async def _opening_balance_plan(
    conn: aiosqlite.Connection, candidate: Candidate, amount_paise: int
) -> PostTransactionInput:
    """Create an opening-balance entry against the system equity account."""
    if candidate.suggested_account_id is None:
        raise HTTPException(status_code=422, detail="account_id is required for opening balances")

    account_cursor = await conn.execute(
        "SELECT account_class FROM accounts WHERE id = ?", (candidate.suggested_account_id,)
    )
    account_row = await account_cursor.fetchone()
    if account_row is None:
        raise HTTPException(status_code=422, detail="account_id does not reference an account")

    equity_cursor = await conn.execute(
        "SELECT id FROM accounts WHERE name = 'Opening Balance Equity'"
    )
    equity_row = await equity_cursor.fetchone()
    if equity_row is None:
        raise HTTPException(status_code=422, detail="Opening Balance Equity account is unavailable")

    if str(account_row[0]) == "liability_cc":
        postings = (
            NewPosting(candidate.suggested_account_id, -amount_paise),
            NewPosting(int(equity_row[0]), amount_paise),
        )
    else:
        postings = (
            NewPosting(candidate.suggested_account_id, amount_paise),
            NewPosting(int(equity_row[0]), -amount_paise),
        )
    return PostTransactionInput(
        tx_date=candidate.tx_date,
        postings=postings,
        payee=candidate.payee,
        notes=candidate.narration,
        source=candidate.source,
        external_key=candidate.external_key,
    )


@router.get("/candidates", response_model=list[IntakeCandidateResponse])
async def get_candidates(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    status: CandidateStatus = Query(default="pending"),
) -> list[IntakeCandidateResponse]:
    """List intake candidates in a review status."""
    return [_candidate_response(row) for row in await list_candidates(conn, status=status)]


@router.post(
    "/candidates/{candidate_id}/approve",
    response_model=CandidateApprovedResponse,
)
async def approve_candidate(
    candidate_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    _: Annotated[None, Depends(require_ledger_writes)],
    body: ApproveBody = ApproveBody(),
) -> CandidateApprovedResponse:
    """Post a reviewed candidate to the immutable ledger."""
    row = await _pending_candidate(conn, candidate_id)
    candidate = _candidate_from_row(row, body)
    try:
        if row["quarantine_reason"] == "needs_opening_balance":
            if body.amount_paise is None:
                raise HTTPException(
                    status_code=422, detail="amount_paise is required for opening balances"
                )
            posting_plan = await _opening_balance_plan(conn, candidate, body.amount_paise)
        elif body.as_transfer:
            if body.to_account_id is None:
                raise HTTPException(
                    status_code=422, detail="to_account_id is required for transfers"
                )
            if candidate.suggested_account_id is None:
                raise HTTPException(status_code=422, detail="account_id is required for transfers")
            posting_plan = await plan_transfer(
                conn,
                from_account_id=candidate.suggested_account_id,
                to_account_id=body.to_account_id,
                amount_paise=candidate.amount_paise,
                tx_date=candidate.tx_date,
                source=candidate.source,
                payee=candidate.payee,
                notes=candidate.narration,
                external_key=candidate.external_key,
            )
        else:
            posting_plan = await plan_postings(conn, candidate)
        ledger_transaction_id = await ledger_service.post(conn, posting_plan)
    except (IntakePlanError, LedgerError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await update_candidate_status(
        conn,
        candidate_id,
        status="posted",
        ledger_transaction_id=ledger_transaction_id,
        clear_quarantine_reason=True,
    )
    await append_event(
        conn,
        event_type="intake.candidate_approved",
        payload={"candidate_id": candidate_id, "ledger_transaction_id": ledger_transaction_id},
    )
    email_staging_id = cast(int | None, row.get("email_staging_id"))
    if email_staging_id is not None or await staging_repo.get_by_intake_candidate_id(
        conn, candidate_id
    ):
        await _sync_staging_on_candidate_approve(
            conn,
            candidate_id,
            email_staging_id=email_staging_id,
            ledger_transaction_id=ledger_transaction_id,
        )
    return CandidateApprovedResponse(
        candidate_id=candidate_id,
        ledger_transaction_id=ledger_transaction_id,
        status="posted",
    )


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=CandidateRejectedResponse,
)
async def reject_candidate(
    candidate_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> CandidateRejectedResponse:
    """Reject a quarantined candidate without posting it."""
    row = await _pending_candidate(conn, candidate_id)
    await update_candidate_status(conn, candidate_id, status="rejected")
    await append_event(
        conn,
        event_type="intake.candidate_rejected",
        payload={"candidate_id": candidate_id},
    )
    email_staging_id = cast(int | None, row.get("email_staging_id"))
    if email_staging_id is not None or await staging_repo.get_by_intake_candidate_id(
        conn, candidate_id
    ):
        await _sync_staging_on_candidate_reject(
            conn,
            candidate_id,
            email_staging_id=email_staging_id,
        )
    return CandidateRejectedResponse(candidate_id=candidate_id, status="rejected")
