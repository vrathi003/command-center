"""Recurring subscriptions API."""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from finance_api.deps import get_conn
from finance_api.schemas.subscription import (
    SubscriptionCreateBody,
    SubscriptionOut,
    SubscriptionPutBody,
)
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
