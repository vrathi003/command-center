"""Home inventory — items and service history."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from finance_api.deps import get_conn
from finance_api.schemas.home_item import (
    HomeInventorySummaryOut,
    HomeItemCreate,
    HomeItemOut,
    HomeItemPut,
    HomeItemServiceEventCreate,
    HomeItemServiceEventOut,
    HomeItemServiceEventPut,
    HomeItemSummaryOut,
)
from finance_common.repositories import home_items as repo
from finance_common.repositories.home_items import HomeItemRow, HomeItemServiceEventRow

router = APIRouter(prefix="/home-items", tags=["home-items"])


def _item_out(row: HomeItemRow) -> HomeItemOut:
    return HomeItemOut(
        id=row.id,
        name=row.name,
        category=row.category,
        brand=row.brand,
        model=row.model,
        serial_number=row.serial_number,
        room_location=row.room_location,
        purchase_date=row.purchase_date,
        purchase_price_paise=row.purchase_price_paise,
        retailer=row.retailer,
        warranty_end_date=row.warranty_end_date,
        extended_warranty=row.extended_warranty,
        condition_status=row.condition_status,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_out(row: HomeItemServiceEventRow) -> HomeItemServiceEventOut:
    return HomeItemServiceEventOut(
        id=row.id,
        home_item_id=row.home_item_id,
        service_date=row.service_date,
        event_type=row.event_type,
        vendor=row.vendor,
        description=row.description,
        cost_paise=row.cost_paise,
        next_service_due=row.next_service_due,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/summary", response_model=HomeInventorySummaryOut)
async def get_summary(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> HomeInventorySummaryOut:
    s = await repo.summary_stats(conn)
    return HomeInventorySummaryOut(
        item_count=int(s["item_count"]),
        purchase_value_total_paise=int(s["purchase_value_total_paise"]),
        service_spend_total_paise=int(s["service_spend_total_paise"]),
        count_by_category=dict(s["count_by_category"]),
        warranty_expiring_within_90_days=int(s["warranty_expiring_within_90_days"]),
    )


@router.get("/", response_model=list[HomeItemSummaryOut])
async def list_items(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    category: Annotated[str | None, Query()] = None,
    room: Annotated[str | None, Query()] = None,
) -> list[HomeItemSummaryOut]:
    rows = await repo.list_home_items(conn, category=category, room=room)
    out: list[HomeItemSummaryOut] = []
    for r in rows:
        events = await repo.list_service_events(conn, r.id)
        n = len(events)
        total = await repo.total_service_for_item(conn, r.id)
        out.append(
            HomeItemSummaryOut(
                id=r.id,
                name=r.name,
                category=r.category,
                brand=r.brand,
                model=r.model,
                room_location=r.room_location,
                purchase_date=r.purchase_date,
                purchase_price_paise=r.purchase_price_paise,
                warranty_end_date=r.warranty_end_date,
                condition_status=r.condition_status,
                service_event_count=n,
                total_service_spend_paise=total,
            )
        )
    return out


@router.post("/", response_model=HomeItemOut, status_code=201)
async def create_item(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: HomeItemCreate,
) -> HomeItemOut:
    iid = await repo.insert_home_item(
        conn,
        name=body.name,
        category=body.category,
        brand=body.brand,
        model=body.model,
        serial_number=body.serial_number,
        room_location=body.room_location,
        purchase_date=body.purchase_date,
        purchase_price_paise=body.purchase_price_paise,
        retailer=body.retailer,
        warranty_end_date=body.warranty_end_date,
        extended_warranty=body.extended_warranty,
        condition_status=body.condition_status,
        notes=body.notes,
    )
    row = await repo.get_home_item(conn, iid)
    if row is None:
        raise HTTPException(status_code=500, detail="item not found after insert")
    return _item_out(row)


@router.get("/{item_id}", response_model=HomeItemOut)
async def get_item(
    item_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> HomeItemOut:
    row = await repo.get_home_item(conn, item_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="item not found")
    return _item_out(row)


@router.put("/{item_id}", response_model=HomeItemOut)
async def put_item(
    item_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: HomeItemPut,
) -> HomeItemOut:
    existing = await repo.get_home_item(conn, item_id)
    if existing is None or existing.is_deleted:
        raise HTTPException(status_code=404, detail="item not found")
    ok = await repo.update_home_item(
        conn,
        item_id=item_id,
        name=body.name,
        category=body.category,
        brand=body.brand,
        model=body.model,
        serial_number=body.serial_number,
        room_location=body.room_location,
        purchase_date=body.purchase_date,
        purchase_price_paise=body.purchase_price_paise,
        retailer=body.retailer,
        warranty_end_date=body.warranty_end_date,
        extended_warranty=body.extended_warranty,
        condition_status=body.condition_status,
        notes=body.notes,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="item not found")
    row = await repo.get_home_item(conn, item_id)
    if row is None:
        raise HTTPException(status_code=500, detail="item not found after update")
    return _item_out(row)


@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> None:
    ok = await repo.soft_delete_home_item(conn, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="item not found")


@router.get("/{item_id}/service-events", response_model=list[HomeItemServiceEventOut])
async def list_service_events(
    item_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[HomeItemServiceEventOut]:
    parent = await repo.get_home_item(conn, item_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="item not found")
    rows = await repo.list_service_events(conn, item_id)
    return [_event_out(r) for r in rows]


@router.post("/{item_id}/service-events", response_model=HomeItemServiceEventOut, status_code=201)
async def create_service_event(
    item_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: HomeItemServiceEventCreate,
) -> HomeItemServiceEventOut:
    parent = await repo.get_home_item(conn, item_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="item not found")
    eid = await repo.insert_service_event(
        conn,
        home_item_id=item_id,
        service_date=body.service_date,
        event_type=body.event_type,
        vendor=body.vendor,
        description=body.description,
        cost_paise=body.cost_paise,
        next_service_due=body.next_service_due,
        notes=body.notes,
    )
    row = await repo.get_service_event(conn, eid, item_id)
    if row is None:
        raise HTTPException(status_code=500, detail="event not found after insert")
    return _event_out(row)


@router.put("/{item_id}/service-events/{event_id}", response_model=HomeItemServiceEventOut)
async def put_service_event(
    item_id: int,
    event_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: HomeItemServiceEventPut,
) -> HomeItemServiceEventOut:
    parent = await repo.get_home_item(conn, item_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="item not found")
    ok = await repo.update_service_event(
        conn,
        event_id=event_id,
        home_item_id=item_id,
        service_date=body.service_date,
        event_type=body.event_type,
        vendor=body.vendor,
        description=body.description,
        cost_paise=body.cost_paise,
        next_service_due=body.next_service_due,
        notes=body.notes,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="event not found")
    row = await repo.get_service_event(conn, event_id, item_id)
    if row is None:
        raise HTTPException(status_code=500, detail="event not found after update")
    return _event_out(row)


@router.delete("/{item_id}/service-events/{event_id}", status_code=204)
async def delete_service_event(
    item_id: int,
    event_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> None:
    parent = await repo.get_home_item(conn, item_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="item not found")
    ok = await repo.delete_service_event(conn, event_id=event_id, home_item_id=item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="event not found")
