"""Gmail email inbox — staged transaction review API."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from finance_api.deps import get_conn, get_settings
from finance_api.settings import ApiSettings
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import email_staging as staging_repo
from finance_common.repositories import transactions as tx_repo
from finance_common.repositories.email_staging import StagedEmailRow
from finance_common.types import Paise

router = APIRouter(prefix="/email-inbox", tags=["email-inbox"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class StagedEmailOut(BaseModel):
    id: int
    gmail_message_id: str
    email_date: str
    email_subject: str | None
    email_from: str | None
    raw_snippet: str | None
    parsed_date: str | None
    parsed_amount_paise: int | None
    parsed_merchant: str | None
    parsed_category: str | None
    parsed_payment_mode: str | None
    parsed_transaction_type: str | None
    suggested_account_id: int | None
    status: str
    created_transaction_id: int | None
    created_at: str


class EmailInboxStats(BaseModel):
    pending: int
    approved: int
    rejected: int


class StagedEmailUpdate(BaseModel):
    parsed_date: str | None = None
    parsed_amount_paise: int | None = None
    parsed_merchant: str | None = None
    parsed_category: str | None = None
    parsed_payment_mode: str | None = None
    parsed_transaction_type: str | None = None
    suggested_account_id: int | None = None


class ApproveBody(BaseModel):
    parsed_date: str | None = None
    parsed_amount_paise: int | None = None
    parsed_merchant: str | None = None
    parsed_category: str | None = None
    parsed_payment_mode: str | None = None
    parsed_transaction_type: str | None = None
    account_id: int | None = None
    notes: str | None = None


class SyncResult(BaseModel):
    new_items: int


def _to_out(row: StagedEmailRow) -> StagedEmailOut:
    return StagedEmailOut(
        id=row.id,
        gmail_message_id=row.gmail_message_id,
        email_date=row.email_date,
        email_subject=row.email_subject,
        email_from=row.email_from,
        raw_snippet=row.raw_snippet,
        parsed_date=row.parsed_date,
        parsed_amount_paise=row.parsed_amount_paise,
        parsed_merchant=row.parsed_merchant,
        parsed_category=row.parsed_category,
        parsed_payment_mode=row.parsed_payment_mode,
        parsed_transaction_type=row.parsed_transaction_type,
        suggested_account_id=row.suggested_account_id,
        status=row.status,
        created_transaction_id=row.created_transaction_id,
        created_at=row.created_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=EmailInboxStats)
async def get_stats(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> EmailInboxStats:
    counts = await staging_repo.count_by_status(conn)
    return EmailInboxStats(
        pending=counts.get("pending", 0),
        approved=counts.get("approved", 0),
        rejected=counts.get("rejected", 0),
    )


@router.get("/", response_model=list[StagedEmailOut])
async def list_inbox(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    status: str | None = None,
    limit: int = 200,
) -> list[StagedEmailOut]:
    rows = await staging_repo.list_staged(conn, status=status, limit=min(limit, 500))
    return [_to_out(r) for r in rows]


@router.post("/sync", response_model=SyncResult)
async def manual_sync(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    api: Annotated[ApiSettings, Depends(get_settings)],
) -> SyncResult:
    """Manually trigger a Gmail sync outside the scheduled 3-hour window."""
    if not api.gmail_credentials_path or not api.gmail_credentials_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Gmail not configured. Set GMAIL_CREDENTIALS_PATH and run scripts/setup_gmail.py.",
        )
    from finance_api.services.gmail_sync import sync_gmail_transactions  # noqa: PLC0415
    n = await sync_gmail_transactions(
        conn,
        api.gmail_credentials_path,
        api.gmail_token_path,
        api.gmail_sync_lookback_hours,
    )
    return SyncResult(new_items=n)


@router.put("/{item_id}", response_model=StagedEmailOut)
async def update_staged(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    item_id: int,
    body: StagedEmailUpdate,
) -> StagedEmailOut:
    row = await staging_repo.get_staged(conn, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending items can be edited")

    patch = body.model_dump(exclude_unset=True)
    await staging_repo.update_staged(conn, item_id, **patch)
    updated = await staging_repo.get_staged(conn, item_id)
    assert updated is not None
    return _to_out(updated)


@router.post("/{item_id}/approve", response_model=StagedEmailOut)
async def approve_staged(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    item_id: int,
    body: ApproveBody,
) -> StagedEmailOut:
    """Approve a staged email transaction — creates it in the transactions table."""
    row = await staging_repo.get_staged(conn, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Item already approved or rejected")

    tx_date_str = body.parsed_date or row.parsed_date
    amount_paise = body.parsed_amount_paise if body.parsed_amount_paise is not None else row.parsed_amount_paise
    merchant = body.parsed_merchant if body.parsed_merchant is not None else row.parsed_merchant
    category = body.parsed_category if body.parsed_category is not None else row.parsed_category or "Other"
    payment_mode = body.parsed_payment_mode if body.parsed_payment_mode is not None else row.parsed_payment_mode or "Other"
    tx_type = body.parsed_transaction_type if body.parsed_transaction_type is not None else row.parsed_transaction_type or "debit"
    account_id = body.account_id if body.account_id is not None else row.suggested_account_id

    if not tx_date_str or not amount_paise or amount_paise <= 0:
        raise HTTPException(status_code=422, detail="date and amount are required to approve")

    try:
        tx_date = date.fromisoformat(tx_date_str)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid parsed_date") from e

    account_name: str | None = None
    if account_id is not None:
        acc_row = await accounts_repo.get_account(conn, account_id)
        if acc_row:
            account_name = acc_row.name

    tid = await tx_repo.insert_transaction(
        conn,
        tx_date=tx_date,
        amount_paise=Paise(amount_paise),
        category=category,
        merchant=merchant,
        payment_mode=payment_mode,
        account=account_name,
        notes=body.notes,
        source="gmail",
        transaction_type=tx_type,
        account_id=account_id,
    )
    await staging_repo.set_status(conn, item_id, "approved", created_transaction_id=tid)
    updated = await staging_repo.get_staged(conn, item_id)
    assert updated is not None
    return _to_out(updated)


@router.post("/{item_id}/reject", response_model=StagedEmailOut)
async def reject_staged(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    item_id: int,
) -> StagedEmailOut:
    row = await staging_repo.get_staged(conn, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Item already processed")
    await staging_repo.set_status(conn, item_id, "rejected")
    updated = await staging_repo.get_staged(conn, item_id)
    assert updated is not None
    return _to_out(updated)


@router.delete("/rejected", response_model=dict)
async def clear_rejected(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> dict:
    n = await staging_repo.delete_by_status(conn, "rejected")
    return {"deleted": n}
