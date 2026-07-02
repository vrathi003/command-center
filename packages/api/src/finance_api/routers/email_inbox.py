"""Gmail email inbox — staged transaction review API."""

from __future__ import annotations

from datetime import date, timedelta
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


class HistoricalSyncBody(BaseModel):
    from_date: str   # YYYY-MM-DD
    to_date: str     # YYYY-MM-DD


class HistoricalSyncResult(BaseModel):
    new_items: int
    total_scanned: int
    from_date: str
    to_date: str


class ApproveAsTransferBody(BaseModel):
    debit_id: int             # staging item that is the debit side (money out = from_account)
    credit_id: int            # staging item that is the credit side (money in = to_account)
    from_account_id: int | None = None
    to_account_id: int | None = None
    tx_date: str | None = None        # overrides debit item's parsed_date if provided
    amount_paise: int | None = None   # overrides parsed amount if provided
    notes: str | None = None


class ApproveAsTransferResult(BaseModel):
    transfer_pair_id: str
    debit_transaction_id: int
    credit_transaction_id: int
    debit_item: StagedEmailOut
    credit_item: StagedEmailOut


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


_MAX_HISTORICAL_DAYS = 90


@router.post("/historical-sync", response_model=HistoricalSyncResult)
async def historical_sync(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    api: Annotated[ApiSettings, Depends(get_settings)],
    body: HistoricalSyncBody,
) -> HistoricalSyncResult:
    """Import emails from a specific date range (max 90 days). Does not affect the rolling sync checkpoint."""
    if not api.gmail_credentials_path or not api.gmail_credentials_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Gmail not configured. Set GMAIL_CREDENTIALS_PATH and run scripts/setup_gmail.py.",
        )

    try:
        from_date = date.fromisoformat(body.from_date)
        to_date = date.fromisoformat(body.to_date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.") from e

    today = date.today()
    if from_date > today:
        raise HTTPException(status_code=422, detail="from_date cannot be in the future.")
    if to_date > today:
        to_date = today
    if from_date > to_date:
        raise HTTPException(status_code=422, detail="from_date must be before or equal to to_date.")
    if (to_date - from_date) > timedelta(days=_MAX_HISTORICAL_DAYS):
        raise HTTPException(
            status_code=422,
            detail=f"Date range cannot exceed {_MAX_HISTORICAL_DAYS} days per import.",
        )

    from finance_api.services.gmail_sync import historical_sync_gmail_transactions  # noqa: PLC0415

    result = await historical_sync_gmail_transactions(
        conn,
        api.gmail_credentials_path,
        api.gmail_token_path,
        from_date,
        to_date,
    )
    return HistoricalSyncResult(
        new_items=result["new_items"],
        total_scanned=result["total_scanned"],
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
    )


@router.post("/approve-as-transfer", response_model=ApproveAsTransferResult)
async def approve_as_transfer(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: ApproveAsTransferBody,
) -> ApproveAsTransferResult:
    """Approve two staged email items as a linked transfer pair."""
    debit_row = await staging_repo.get_staged(conn, body.debit_id)
    credit_row = await staging_repo.get_staged(conn, body.credit_id)

    if debit_row is None or credit_row is None:
        raise HTTPException(status_code=404, detail="One or both staging items not found")
    if debit_row.status != "pending" or credit_row.status != "pending":
        raise HTTPException(status_code=409, detail="Both items must be in pending status")
    if debit_row.id == credit_row.id:
        raise HTTPException(status_code=422, detail="debit_id and credit_id must be different")

    # Determine amount and date — body overrides take precedence, then fall back to parsed values
    amount_paise = body.amount_paise or debit_row.parsed_amount_paise or credit_row.parsed_amount_paise
    if not amount_paise or amount_paise <= 0:
        raise HTTPException(status_code=422, detail="amount_paise is required (set it on the item or pass in body)")

    date_str = body.tx_date or debit_row.parsed_date or credit_row.parsed_date
    if not date_str:
        raise HTTPException(status_code=422, detail="tx_date is required (set parsed_date on the item or pass in body)")
    try:
        tx_date = date.fromisoformat(date_str)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid tx_date") from e

    # Resolve accounts
    from_account_id = body.from_account_id or debit_row.suggested_account_id
    to_account_id = body.to_account_id or credit_row.suggested_account_id

    if not from_account_id or not to_account_id:
        raise HTTPException(
            status_code=422,
            detail="from_account_id and to_account_id are required (pass them in the body or set suggested_account_id on each item)",
        )
    if from_account_id == to_account_id:
        raise HTTPException(status_code=422, detail="from_account_id and to_account_id must be different accounts")

    from_acc = await accounts_repo.get_account(conn, from_account_id)
    to_acc = await accounts_repo.get_account(conn, to_account_id)
    if from_acc is None or to_acc is None:
        raise HTTPException(status_code=404, detail="Account not found")

    out_id, in_id, pair_id = await tx_repo.insert_transfer_pair(
        conn,
        amount_paise=Paise(amount_paise),
        tx_date=tx_date,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        from_account_name=from_acc.name,
        to_account_name=to_acc.name,
        notes=body.notes,
        tags=None,
        source="gmail",
    )

    await staging_repo.set_status(conn, body.debit_id, "approved", created_transaction_id=out_id)
    await staging_repo.set_status(conn, body.credit_id, "approved", created_transaction_id=in_id)

    updated_debit = await staging_repo.get_staged(conn, body.debit_id)
    updated_credit = await staging_repo.get_staged(conn, body.credit_id)
    assert updated_debit and updated_credit

    return ApproveAsTransferResult(
        transfer_pair_id=pair_id,
        debit_transaction_id=out_id,
        credit_transaction_id=in_id,
        debit_item=_to_out(updated_debit),
        credit_item=_to_out(updated_credit),
    )


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
