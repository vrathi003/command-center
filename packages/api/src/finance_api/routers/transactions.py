"""Transactions listing and import."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from finance_api.deps import get_conn, get_settings
from finance_api.schemas.transactions import (
    TransactionBulkDeleteBody,
    TransactionBulkDeleteResponse,
    TransactionCreate,
    TransactionCreated,
    TransactionDashboardUpdate,
    TransactionImportResponse,
    TransactionImportRowError,
    TransactionUpdated,
    TransferCreate,
    TransferResponse,
)
from finance_api.services.transaction_import_service import (
    MAX_BYTES,
    import_transactions_from_rows,
    load_rows_from_upload,
)
from finance_api.settings import ApiSettings
from finance_common.parsing.bank_statement_pdf import (
    BankStatementPdfError,
    pdf_bytes_to_import_rows,
)
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import transactions as tx_repo
from finance_common.types import Paise

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _tx_row_dict(r: tx_repo.TransactionRow) -> dict[str, object]:
    return {
        "id": r.id,
        "date": r.date,
        "amount_paise": r.amount_paise,
        "category": r.category,
        "merchant": r.merchant,
        "payment_mode": r.payment_mode,
        "account": r.account,
        "notes": r.notes,
        "transaction_type": r.transaction_type,
        "source": r.source,
        "account_id": r.account_id,
        "transfer_pair_id": r.transfer_pair_id,
        "tags": r.tags,
    }


@router.get("/")
async def list_transactions(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    limit: int = Query(default=50, ge=1, le=5000),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    account: str | None = Query(default=None),
) -> list[dict[str, object]]:
    rows = await tx_repo.list_recent(
        conn, limit=limit, start_date=start_date, end_date=end_date, account=account
    )
    return [_tx_row_dict(r) for r in rows]


@router.get("/{transaction_id}")
async def get_transaction(
    transaction_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> dict[str, object]:
    """Single transaction for editing; includes ``transfer_sibling`` when part of a pair."""
    if transaction_id <= 0:
        raise HTTPException(status_code=422, detail="transaction_id must be positive")
    row = await tx_repo.get_by_id(conn, transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    out: dict[str, object] = {**_tx_row_dict(row)}
    sibling: tx_repo.TransactionRow | None = None
    if row.transfer_pair_id:
        sibling = await tx_repo.get_transfer_pair_sibling(
            conn, pair_id=row.transfer_pair_id, exclude_id=transaction_id
        )
    out["transfer_sibling"] = _tx_row_dict(sibling) if sibling else None
    return out


@router.post("/", response_model=TransactionCreated, status_code=201)
async def create_transaction(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: TransactionCreate,
) -> TransactionCreated:
    """Create a single debit or credit transaction from the dashboard."""
    try:
        d = date.fromisoformat(body.date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid date") from e
    acc_name = body.account
    aid = body.account_id
    if aid is not None:
        row = await accounts_repo.get_account(conn, aid)
        if row is None:
            raise HTTPException(status_code=404, detail="account_id not found")
        acc_name = row.name
    tid = await tx_repo.insert_transaction(
        conn,
        tx_date=d,
        amount_paise=Paise(body.amount_paise),
        category=body.category,
        merchant=body.merchant,
        payment_mode=body.payment_mode,
        account=acc_name,
        notes=body.notes,
        source=body.source,
        transaction_type=body.transaction_type,
        account_id=aid,
        tags=body.tags,
    )
    return TransactionCreated(id=tid)


@router.put("/{transaction_id}", response_model=TransactionUpdated)
async def update_transaction(
    transaction_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: TransactionDashboardUpdate,
) -> TransactionUpdated:
    """Update a single debit/credit row or both legs of a transfer (by any leg id)."""
    if transaction_id <= 0:
        raise HTTPException(status_code=422, detail="transaction_id must be positive")
    row = await tx_repo.get_by_id(conn, transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    try:
        d = date.fromisoformat(body.date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid date") from e

    if row.transaction_type in ("debit", "credit") and (
        body.from_account_id is not None and body.to_account_id is not None
    ):
        if body.from_account_id == body.to_account_id:
            raise HTTPException(
                status_code=400,
                detail="from_account_id and to_account_id must differ",
            )
        from_a = await accounts_repo.get_account(conn, body.from_account_id)
        to_a = await accounts_repo.get_account(conn, body.to_account_id)
        if from_a is None or to_a is None:
            raise HTTPException(status_code=404, detail="account not found")
        converted = await tx_repo.convert_debit_credit_to_transfer_pair(
            conn,
            transaction_id,
            tx_date=d,
            amount_paise=body.amount_paise,
            from_account_id=body.from_account_id,
            to_account_id=body.to_account_id,
            from_account_name=from_a.name,
            to_account_name=to_a.name,
            notes=body.notes,
            tags=body.tags,
        )
        if converted is None:
            raise HTTPException(
                status_code=409,
                detail="could not convert transaction to transfer (already paired?)",
            )
        return TransactionUpdated(id=transaction_id)

    if row.transaction_type == "transfer":
        if row.transfer_pair_id is None:
            if body.category is None or body.payment_mode is None:
                raise HTTPException(
                    status_code=422,
                    detail="category and payment_mode are required for single-leg transfer edits",
                )
            o_acc: str | None = None
            o_aid = body.account_id
            if o_aid is not None:
                acc_row = await accounts_repo.get_account(conn, o_aid)
                if acc_row is None:
                    raise HTTPException(status_code=404, detail="account_id not found")
                o_acc = acc_row.name
            ok = await tx_repo.update_dashboard_transfer_orphan(
                conn,
                transaction_id,
                tx_date=d,
                amount_paise=body.amount_paise,
                category=body.category,
                merchant=body.merchant,
                payment_mode=body.payment_mode,
                notes=body.notes,
                account=o_acc,
                account_id=o_aid,
                tags=body.tags,
            )
            if not ok:
                raise HTTPException(status_code=409, detail="update failed")
            return TransactionUpdated(id=transaction_id)
        if body.from_account_id is None or body.to_account_id is None:
            raise HTTPException(
                status_code=422,
                detail="from_account_id and to_account_id are required for transfer edits",
            )
        if body.from_account_id == body.to_account_id:
            raise HTTPException(
                status_code=400,
                detail="from_account_id and to_account_id must differ",
            )
        from_a = await accounts_repo.get_account(conn, body.from_account_id)
        to_a = await accounts_repo.get_account(conn, body.to_account_id)
        if from_a is None or to_a is None:
            raise HTTPException(status_code=404, detail="account not found")
        ok = await tx_repo.update_transfer_pair_dashboard(
            conn,
            pair_id=row.transfer_pair_id,
            tx_date=d,
            amount_paise=body.amount_paise,
            from_account_id=body.from_account_id,
            to_account_id=body.to_account_id,
            from_account_name=from_a.name,
            to_account_name=to_a.name,
            notes=body.notes,
            tags=body.tags,
        )
        if not ok:
            raise HTTPException(
                status_code=409,
                detail="could not update transfer pair (missing Transfer in/out rows?)",
            )
        return TransactionUpdated(id=transaction_id)

    if body.category is None or body.payment_mode is None or body.transaction_type is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "category, payment_mode, and transaction_type are required "
                "for debit/credit edits"
            ),
        )
    acc_name: str | None = None
    aid = body.account_id
    if aid is not None:
        acc_row = await accounts_repo.get_account(conn, aid)
        if acc_row is None:
            raise HTTPException(status_code=404, detail="account_id not found")
        acc_name = acc_row.name

    ok = await tx_repo.update_dashboard_debit_credit(
        conn,
        transaction_id,
        tx_date=d,
        amount_paise=body.amount_paise,
        category=body.category,
        merchant=body.merchant,
        payment_mode=body.payment_mode,
        notes=body.notes,
        transaction_type=body.transaction_type,
        account=acc_name,
        account_id=aid,
        tags=body.tags,
    )
    if not ok:
        raise HTTPException(status_code=409, detail="update failed")
    return TransactionUpdated(id=transaction_id)


@router.post("/transfer", response_model=TransferResponse, status_code=201)
async def create_transfer(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: TransferCreate,
) -> TransferResponse:
    """Create two linked transfer rows (excluded from spend totals)."""
    if body.from_account_id == body.to_account_id:
        raise HTTPException(status_code=400, detail="from_account_id and to_account_id must differ")
    try:
        d = date.fromisoformat(body.date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid date") from e
    from_a = await accounts_repo.get_account(conn, body.from_account_id)
    to_a = await accounts_repo.get_account(conn, body.to_account_id)
    if from_a is None or to_a is None:
        raise HTTPException(status_code=404, detail="account not found")
    out_id, in_id, pair_id = await tx_repo.insert_transfer_pair(
        conn,
        amount_paise=body.amount_paise,
        tx_date=d,
        from_account_id=body.from_account_id,
        to_account_id=body.to_account_id,
        from_account_name=from_a.name,
        to_account_name=to_a.name,
        notes=body.notes,
        tags=body.tags,
        source="dashboard",
    )
    return TransferResponse(
        transfer_pair_id=pair_id,
        debit_transaction_id=out_id,
        credit_transaction_id=in_id,
    )


@router.post("/bulk-delete", response_model=TransactionBulkDeleteResponse)
async def bulk_delete_transactions(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: TransactionBulkDeleteBody,
) -> TransactionBulkDeleteResponse:
    """Soft-delete multiple transactions by id (same as Discord undo semantics)."""
    unique = list(dict.fromkeys(body.ids))
    if any(i <= 0 for i in unique):
        raise HTTPException(status_code=422, detail="ids must be positive integers")
    n = await tx_repo.soft_delete_by_ids(conn, unique)
    return TransactionBulkDeleteResponse(deleted=n)


@router.post("/import", response_model=TransactionImportResponse)
async def import_transactions(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    api_settings: Annotated[ApiSettings, Depends(get_settings)],
    file: UploadFile = File(...),
    pdf_password: str | None = Form(default=None),
    account_name: str | None = Form(default=None),
) -> TransactionImportResponse:
    """Upload a `.csv`, `.xlsx`, `.xlsm`, `.xls` (Excel 97–2003), or `.pdf` bank statement.

    Tabular files need a header row. Required: **date** (or booking date / value date) and
    **amount** (₹), or separate **debit** / **credit** columns. **category** defaults to Other if
    omitted. Optional: merchant, payment_mode, notes, account.

    For **encrypted PDFs** or **password-protected Excel**, send form field ``pdf_password``
    (same field) together with ``file``.

    PDFs: text is extracted with PyMuPDF; simple line layouts are parsed without an LLM. If that
    yields no rows and `LM_STUDIO_ENABLED` is true, local LM Studio (`LM_STUDIO_URL`) is used —
    may take a minute for long PDFs.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="file name is required")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="file is empty")
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"file too large (max {MAX_BYTES // (1024 * 1024)} MB)",
        )
    try:
        pw = pdf_password.strip() if pdf_password else None
        if file.filename.lower().strip().endswith(".pdf"):
            rows = await pdf_bytes_to_import_rows(content, api_settings, password=pw)
        else:
            rows = load_rows_from_upload(file.filename, content, password=pw)
    except BankStatementPdfError as e:
        msg = str(e)
        client_error = (
            "Heuristic parsing found no transaction lines" in msg
            or "Could not parse transaction lines" in msg
            or "Refusing" in msg
            or "LM_STUDIO_URL" in msg
            or "LM_STUDIO_ENABLED" in msg
            or "LM Studio is disabled" in msg
            or "too large" in msg
            or "no text extracted" in msg
            or "unreadable PDF" in msg
            or "too many pages" in msg
            or "password-protected" in msg
            or "incorrect PDF password" in msg
        )
        if client_error:
            raise HTTPException(status_code=400, detail=msg) from e
        raise HTTPException(status_code=503, detail=msg) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not rows:
        raise HTTPException(status_code=400, detail="no data rows found")
    acct = account_name.strip() if account_name else None
    imported, failed, errs = await import_transactions_from_rows(
        conn, rows, account_name=acct or None
    )
    return TransactionImportResponse(
        imported=imported,
        failed=failed,
        errors=[TransactionImportRowError(row=r, message=m) for r, m in errs[:50]],
    )
