"""Transaction quick-add templates CRUD."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn
from finance_api.schemas.transaction_templates import (
    TransactionTemplateCreate,
    TransactionTemplateOut,
    TransactionTemplateUpdate,
)
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import transaction_templates as tmpl_repo

router = APIRouter(prefix="/transaction-templates", tags=["transaction-templates"])


def _out(r: tmpl_repo.TemplateRow) -> dict[str, object]:
    return {
        "id": r.id,
        "name": r.name,
        "amount": r.amount,
        "merchant": r.merchant,
        "category": r.category,
        "account_id": r.account_id,
        "payment_mode": r.payment_mode,
        "transaction_type": r.transaction_type,
        "notes": r.notes,
        "tags": r.tags,
        "created_at": r.created_at,
    }


@router.get("/")
async def list_templates(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[dict[str, object]]:
    rows = await tmpl_repo.list_templates(conn)
    return [_out(r) for r in rows]


@router.post("/", response_model=TransactionTemplateOut, status_code=201)
async def create_template(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: TransactionTemplateCreate,
) -> dict[str, object]:
    if body.account_id is not None:
        a = await accounts_repo.get_account(conn, body.account_id)
        if a is None:
            raise HTTPException(status_code=404, detail="account_id not found")
    tid = await tmpl_repo.create_template(
        conn,
        name=body.name,
        amount=body.amount,
        merchant=body.merchant,
        category=body.category,
        account_id=body.account_id,
        payment_mode=body.payment_mode,
        transaction_type=body.transaction_type,
        notes=body.notes,
        tags=body.tags,
    )
    row = await tmpl_repo.get_template(conn, tid)
    if row is None:
        raise HTTPException(status_code=500, detail="template not found after create")
    return _out(row)


@router.put("/{template_id}", response_model=TransactionTemplateOut)
async def update_template(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    template_id: int,
    body: TransactionTemplateUpdate,
) -> dict[str, object]:
    if body.account_id is not None:
        a = await accounts_repo.get_account(conn, body.account_id)
        if a is None:
            raise HTTPException(status_code=404, detail="account_id not found")
    ok = await tmpl_repo.update_template(
        conn,
        template_id,
        name=body.name,
        amount=body.amount,
        merchant=body.merchant,
        category=body.category,
        account_id=body.account_id,
        payment_mode=body.payment_mode,
        transaction_type=body.transaction_type,
        notes=body.notes,
        tags=body.tags,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="template not found")
    row = await tmpl_repo.get_template(conn, template_id)
    if row is None:
        raise HTTPException(status_code=500, detail="template not found after update")
    return _out(row)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    template_id: int,
) -> None:
    ok = await tmpl_repo.soft_delete_template(conn, template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="template not found")
