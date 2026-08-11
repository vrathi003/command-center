"""Recurring subscriptions API."""

from __future__ import annotations

from dataclasses import replace
from datetime import date as date_cls
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from finance_api.deps import get_conn
from finance_api.deps_ledger import require_ledger_writes
from finance_api.schemas.subscription import (
    RecordChargeBody,
    RecordChargeOut,
    SubscriptionCreateBody,
    SubscriptionOut,
    SubscriptionPutBody,
)
from finance_api.services.subscription_charge import post_subscription_charge
from finance_common.ledger.errors import LedgerError
from finance_common.project_config import load_project_config
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import subscriptions as sub_repo
from finance_common.repositories.subscriptions import SubscriptionRow

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

_VALID_CYCLES = frozenset({"weekly", "monthly", "quarterly", "yearly"})


def _validate_cycle(cycle: str) -> str:
    c = cycle.lower().strip()
    if c not in _VALID_CYCLES:
        raise HTTPException(
            status_code=422,
            detail=f"billing_cycle must be one of: {', '.join(sorted(_VALID_CYCLES))}",
        )
    return c


def _to_out(row: SubscriptionRow) -> SubscriptionOut:
    return SubscriptionOut(
        id=row.id,
        name=row.name,
        provider=row.provider,
        category=row.category,
        amount_paise=row.amount_paise,
        billing_cycle=row.billing_cycle,
        monthly_equivalent_paise=sub_repo.monthly_equivalent_paise(row.amount_paise, row.billing_cycle),
        next_billing_date=row.next_billing_date,
        notes=row.notes,
        is_active=row.is_active,
        account_id=row.account_id,
    )


def _merge(existing: SubscriptionRow, body: SubscriptionPutBody) -> SubscriptionRow:
    patch = body.model_dump(exclude_unset=True)
    if "billing_cycle" in patch and patch["billing_cycle"] is not None:
        patch["billing_cycle"] = _validate_cycle(patch["billing_cycle"])
    return replace(existing, **patch)


@router.get("/", response_model=list[SubscriptionOut])
async def list_subscriptions(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    active_only: Annotated[bool, Query(description="Only active subscriptions")] = False,
) -> list[SubscriptionOut]:
    rows = await sub_repo.list_subscriptions(conn, active_only=active_only)
    return [_to_out(r) for r in rows]


@router.post("/", response_model=SubscriptionOut, status_code=201)
async def create_subscription(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: SubscriptionCreateBody,
) -> SubscriptionOut:
    cycle = _validate_cycle(body.billing_cycle)
    sid = await sub_repo.insert_subscription(
        conn,
        name=body.name.strip(),
        provider=body.provider.strip() if body.provider else None,
        category=body.category.strip() if body.category else None,
        amount_paise=body.amount_paise,
        billing_cycle=cycle,
        next_billing_date=body.next_billing_date,
        notes=body.notes.strip() if body.notes else None,
        is_active=body.is_active,
        account_id=body.account_id,
    )
    row = await sub_repo.get_subscription(conn, sid)
    if row is None:
        raise HTTPException(status_code=500, detail="subscription not found after insert")
    return _to_out(row)


@router.get("/{subscription_id}", response_model=SubscriptionOut)
async def get_subscription(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    subscription_id: int,
) -> SubscriptionOut:
    row = await sub_repo.get_subscription(conn, subscription_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return _to_out(row)


@router.put("/{subscription_id}", response_model=SubscriptionOut)
async def put_subscription(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    subscription_id: int,
    body: SubscriptionPutBody,
) -> SubscriptionOut:
    existing = await sub_repo.get_subscription(conn, subscription_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    merged = _merge(existing, body)
    await sub_repo.update_subscription_row(conn, merged)
    return _to_out(merged)


@router.delete("/{subscription_id}", status_code=204)
async def delete_subscription(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    subscription_id: int,
) -> None:
    ok = await sub_repo.delete_subscription(conn, subscription_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.post(
    "/{subscription_id}/record-charge",
    response_model=RecordChargeOut,
    status_code=201,
)
async def record_charge(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    request: Request,
    subscription_id: int,
    body: RecordChargeBody,
) -> RecordChargeOut:
    """Post one subscription charge through the ledger and advance billing date."""
    row = await sub_repo.get_subscription(conn, subscription_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Subscription not found")

    project_config = await load_project_config(conn)
    if project_config.ledger_engine != "double_entry":
        raise HTTPException(
            status_code=422,
            detail="record-charge requires double_entry ledger engine",
        )

    payment_account_id = body.account_id or row.account_id
    if payment_account_id is None:
        raise HTTPException(
            status_code=422,
            detail="account_id required (on subscription or in request body)",
        )
    if await accounts_repo.get_account(conn, payment_account_id) is None:
        raise HTTPException(status_code=404, detail="account_id not found")

    try:
        date_cls.fromisoformat(body.date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid date") from e

    require_ledger_writes(request)
    try:
        ledger_transaction_id, updated = await post_subscription_charge(
            conn,
            sub=row,
            payment_date=body.date,
            amount_paise=body.amount_paise,
            account_id=body.account_id,
        )
    except LedgerError as exc:
        detail = str(exc)
        if "does not exist" in detail:
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=422, detail=detail) from exc

    return RecordChargeOut(
        ledger_transaction_id=ledger_transaction_id,
        next_billing_date=updated.next_billing_date,
        subscription=_to_out(updated),
    )
