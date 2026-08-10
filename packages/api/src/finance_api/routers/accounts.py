"""Accounts CRUD — bank accounts, credit cards, wallets, etc."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from finance_api.deps import get_conn
from finance_common.repositories import accounts as accounts_repo
from finance_common.types import AccountClass

router = APIRouter(prefix="/accounts", tags=["accounts"])

ACCOUNT_TYPES = [
    "savings",
    "current",
    "credit_card",
    "wallet",
    "investment",
    "loan",
    "other",
]


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=50)
    account_class: AccountClass | None = None
    institution: str | None = None
    currency: str = "INR"


class AccountUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=50)
    account_class: AccountClass | None = None
    institution: str | None = None
    currency: str = "INR"
    is_active: bool = True


def _account_dict(a: accounts_repo.AccountRow) -> dict[str, object]:
    return {
        "id": a.id,
        "name": a.name,
        "type": a.type,
        "account_class": a.account_class,
        "institution": a.institution,
        "currency": a.currency,
        "is_active": a.is_active,
    }


@router.get("/")
async def list_accounts(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    active_only: bool = False,
) -> list[dict[str, object]]:
    accounts = await accounts_repo.list_accounts(conn, active_only=active_only)
    return [_account_dict(a) for a in accounts]


@router.get("/types")
async def get_account_types() -> list[str]:
    return ACCOUNT_TYPES


@router.post("/", status_code=201)
async def create_account(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: AccountCreate,
) -> dict[str, object]:
    account_id = await accounts_repo.create_account(
        conn,
        name=body.name.strip(),
        type=body.type.strip(),
        institution=body.institution.strip() if body.institution else None,
        currency=body.currency,
        account_class=body.account_class.value if body.account_class else None,
    )
    account = await accounts_repo.get_account(conn, account_id)
    if account is None:
        raise HTTPException(status_code=500, detail="Account not found after creation")
    return _account_dict(account)


@router.put("/{account_id}")
async def update_account(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    account_id: int,
    body: AccountUpdate,
) -> dict[str, object]:
    ok = await accounts_repo.update_account(
        conn,
        account_id,
        name=body.name.strip(),
        type=body.type.strip(),
        institution=body.institution.strip() if body.institution else None,
        currency=body.currency,
        is_active=body.is_active,
        account_class=body.account_class.value if body.account_class else None,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    account = await accounts_repo.get_account(conn, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return _account_dict(account)


@router.delete("/{account_id}", status_code=204)
async def delete_account(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    account_id: int,
) -> None:
    ok = await accounts_repo.delete_account(conn, account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
