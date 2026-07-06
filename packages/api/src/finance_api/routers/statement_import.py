"""Statement import: Gmail fetch rules, tags, fetch + preview."""

from __future__ import annotations

import json
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from finance_api.deps import get_conn, get_settings
from finance_api.schemas.statement_import import (
    GmailStatusOut,
    StatementImportFetchResponse,
    StatementImportRuleCreate,
    StatementImportRuleOut,
    StatementImportRuleUpdate,
    StatementImportSnapshotOut,
    StatementImportTransactionBody,
    StatementImportTransactionBulkDeleteBody,
    StatementTagRuleOut,
    StatementTagRulesPutBody,
)
from finance_api.services.statement_import_service import (
    create_snapshot_transaction,
    delete_snapshot_transactions,
    ensure_transaction_ids,
    fetch_and_parse,
    get_latest_transactions,
    migrate_from_local_config,
    transactions_to_csv,
    update_snapshot_transaction,
)
from finance_api.settings import ApiSettings
from finance_common.repositories import statement_import as si_repo

router = APIRouter(prefix="/statement-import", tags=["statement-import"])


def _rule_out(row: si_repo.StatementImportRuleRow) -> StatementImportRuleOut:
    return StatementImportRuleOut(
        id=row.id,
        bank=row.bank,
        card=row.card,
        from_emails=row.from_emails,
        subject_contains=row.subject_contains,
        pdf_password=row.pdf_password,
        credit_card_id=row.credit_card_id,
        is_enabled=row.is_enabled,
        fetch_months=row.fetch_months,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _tag_out(row: si_repo.StatementTagRuleRow) -> StatementTagRuleOut:
    return StatementTagRuleOut(
        id=row.id,
        tag_name=row.tag_name,
        regex_patterns=row.regex_patterns,
        is_enabled=row.is_enabled,
    )


def _snapshot_out(row: si_repo.StatementImportSnapshotRow) -> StatementImportSnapshotOut:
    skipped: list[dict[str, str]] = []
    if row.skipped_json:
        try:
            raw = json.loads(row.skipped_json)
            if isinstance(raw, list):
                skipped = [dict(x) for x in raw if isinstance(x, dict)]
        except json.JSONDecodeError:
            pass
    transactions: list[dict] = []
    try:
        raw_tx = json.loads(row.transactions_json)
        if isinstance(raw_tx, list):
            transactions = ensure_transaction_ids([dict(x) for x in raw_tx if isinstance(x, dict)])
    except json.JSONDecodeError:
        pass
    return StatementImportSnapshotOut(
        id=row.id,
        fetched_at=row.fetched_at,
        gmail_scanned=row.gmail_scanned,
        statements_parsed=row.statements_parsed,
        skipped=skipped,
        transactions=transactions,
    )


@router.get("/gmail-status", response_model=GmailStatusOut)
async def gmail_status(
    settings: Annotated[ApiSettings, Depends(get_settings)],
) -> GmailStatusOut:
    creds = settings.gmail_credentials_path
    return GmailStatusOut(
        configured=creds is not None and creds.is_file(),
        credentials_path=str(creds) if creds else None,
        llm_enabled=settings.local_llm_active,
        llm_model=settings.local_llm_model if settings.local_llm_active else None,
    )


@router.get("/rules", response_model=list[StatementImportRuleOut])
async def list_rules(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[StatementImportRuleOut]:
    await migrate_from_local_config(conn)
    rows = await si_repo.list_rules(conn)
    return [_rule_out(r) for r in rows]


@router.post("/rules", response_model=StatementImportRuleOut, status_code=201)
async def create_rule(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: StatementImportRuleCreate,
) -> StatementImportRuleOut:
    rid = await si_repo.create_rule(
        conn,
        bank=body.bank,
        card=body.card,
        from_emails=body.from_emails,
        subject_contains=body.subject_contains,
        pdf_password=body.pdf_password,
        credit_card_id=body.credit_card_id,
        is_enabled=body.is_enabled,
        fetch_months=body.fetch_months,
    )
    row = await si_repo.get_rule(conn, rid)
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create rule")
    return _rule_out(row)


@router.put("/rules/{rule_id}", response_model=StatementImportRuleOut)
async def update_rule(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    rule_id: int,
    body: StatementImportRuleUpdate,
) -> StatementImportRuleOut:
    ok = await si_repo.update_rule(
        conn,
        rule_id,
        bank=body.bank,
        card=body.card,
        from_emails=body.from_emails,
        subject_contains=body.subject_contains,
        pdf_password=body.pdf_password,
        credit_card_id=body.credit_card_id,
        is_enabled=body.is_enabled,
        fetch_months=body.fetch_months,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    row = await si_repo.get_rule(conn, rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _rule_out(row)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    rule_id: int,
) -> None:
    ok = await si_repo.delete_rule(conn, rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")


@router.get("/tags", response_model=list[StatementTagRuleOut])
async def list_tags(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[StatementTagRuleOut]:
    await migrate_from_local_config(conn)
    rows = await si_repo.list_tag_rules(conn)
    return [_tag_out(r) for r in rows]


@router.put("/tags", response_model=list[StatementTagRuleOut])
async def replace_tags(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: StatementTagRulesPutBody,
) -> list[StatementTagRuleOut]:
    rules = [(t.tag_name, t.regex_patterns, t.is_enabled) for t in body.tags]
    await si_repo.replace_tag_rules(conn, rules)
    rows = await si_repo.list_tag_rules(conn)
    return [_tag_out(r) for r in rows]


@router.post("/fetch", response_model=StatementImportFetchResponse)
async def fetch_statements(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
    force: bool = False,
) -> StatementImportFetchResponse:
    if settings.gmail_credentials_path is None or not settings.gmail_credentials_path.is_file():
        raise HTTPException(
            status_code=400,
            detail="Gmail is not configured (GMAIL_CREDENTIALS_PATH). Run scripts/setup_gmail.py.",
        )
    try:
        result = await fetch_and_parse(
            conn,
            settings.gmail_credentials_path,
            settings.gmail_token_path,
            settings,
            force=force,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return StatementImportFetchResponse(
        gmail_scanned=result.gmail_scanned,
        statements_parsed=result.statements_parsed,
        skipped=result.skipped,
        transactions=result.transactions,
        snapshot_id=result.snapshot_id,
        llm_model=result.llm_model,
        tags_source=result.tags_source,
        category_source=result.category_source,
    )


@router.get("/snapshots/latest", response_model=StatementImportSnapshotOut | None)
async def get_latest_snapshot(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> StatementImportSnapshotOut | None:
    row = await si_repo.get_latest_snapshot(conn)
    if row is None:
        return None
    try:
        transactions = await get_latest_transactions(conn)
    except ValueError:
        transactions = []
    base = _snapshot_out(row)
    return StatementImportSnapshotOut(
        id=base.id,
        fetched_at=base.fetched_at,
        gmail_scanned=base.gmail_scanned,
        statements_parsed=base.statements_parsed,
        skipped=base.skipped,
        transactions=transactions,
    )


@router.get("/snapshots/latest/csv")
async def download_latest_csv(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> PlainTextResponse:
    try:
        transactions = await get_latest_transactions(conn)
    except ValueError as e:
        if str(e) == "no_snapshot":
            raise HTTPException(status_code=404, detail="No snapshot available") from e
        raise HTTPException(status_code=500, detail="Invalid snapshot data") from e
    csv_text = transactions_to_csv(transactions)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="statement_import.csv"'},
    )


async def _latest_snapshot_out(
    conn: aiosqlite.Connection,
    transactions: list[dict],
) -> StatementImportSnapshotOut:
    row = await si_repo.get_latest_snapshot(conn)
    if row is None:
        raise HTTPException(status_code=404, detail="No snapshot available")
    base = _snapshot_out(row)
    return StatementImportSnapshotOut(
        id=base.id,
        fetched_at=base.fetched_at,
        gmail_scanned=base.gmail_scanned,
        statements_parsed=base.statements_parsed,
        skipped=base.skipped,
        transactions=transactions,
    )


@router.post("/snapshots/latest/transactions", response_model=StatementImportSnapshotOut)
async def create_snapshot_transaction_route(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: StatementImportTransactionBody,
) -> StatementImportSnapshotOut:
    try:
        transactions = await create_snapshot_transaction(conn, body.model_dump())
    except ValueError as e:
        if str(e) == "no_snapshot":
            raise HTTPException(status_code=404, detail="No snapshot available") from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await _latest_snapshot_out(conn, transactions)


@router.put("/snapshots/latest/transactions/{tx_id}", response_model=StatementImportSnapshotOut)
async def update_snapshot_transaction_route(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    tx_id: str,
    body: StatementImportTransactionBody,
) -> StatementImportSnapshotOut:
    try:
        transactions = await update_snapshot_transaction(conn, tx_id, body.model_dump())
    except ValueError as e:
        if str(e) == "no_snapshot":
            raise HTTPException(status_code=404, detail="No snapshot available") from e
        if str(e) == "not_found":
            raise HTTPException(status_code=404, detail="Transaction not found") from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await _latest_snapshot_out(conn, transactions)


@router.post("/snapshots/latest/transactions/bulk-delete", response_model=StatementImportSnapshotOut)
async def bulk_delete_snapshot_transactions(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: StatementImportTransactionBulkDeleteBody,
) -> StatementImportSnapshotOut:
    try:
        transactions = await delete_snapshot_transactions(conn, body.ids)
    except ValueError as e:
        if str(e) == "no_snapshot":
            raise HTTPException(status_code=404, detail="No snapshot available") from e
        if str(e) in ("not_found", "empty_ids"):
            raise HTTPException(status_code=404, detail="Transaction not found") from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await _latest_snapshot_out(conn, transactions)
