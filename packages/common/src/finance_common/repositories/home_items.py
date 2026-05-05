"""Home inventory items and service history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class HomeItemRow:
    id: int
    name: str
    category: str
    brand: str | None
    model: str | None
    serial_number: str | None
    room_location: str | None
    purchase_date: str | None
    purchase_price_paise: int | None
    retailer: str | None
    warranty_end_date: str | None
    extended_warranty: bool
    condition_status: str
    notes: str | None
    created_at: str
    updated_at: str
    is_deleted: bool


@dataclass(frozen=True, slots=True)
class HomeItemServiceEventRow:
    id: int
    home_item_id: int
    service_date: str
    event_type: str
    vendor: str | None
    description: str | None
    cost_paise: int | None
    next_service_due: str | None
    notes: str | None
    created_at: str
    updated_at: str


def _item_row(r: tuple[Any, ...]) -> HomeItemRow:
    return HomeItemRow(
        id=int(r[0]),
        name=str(r[1]),
        category=str(r[2]),
        brand=str(r[3]) if r[3] is not None else None,
        model=str(r[4]) if r[4] is not None else None,
        serial_number=str(r[5]) if r[5] is not None else None,
        room_location=str(r[6]) if r[6] is not None else None,
        purchase_date=str(r[7]) if r[7] is not None else None,
        purchase_price_paise=int(r[8]) if r[8] is not None else None,
        retailer=str(r[9]) if r[9] is not None else None,
        warranty_end_date=str(r[10]) if r[10] is not None else None,
        extended_warranty=bool(int(r[11])),
        condition_status=str(r[12]),
        notes=str(r[13]) if r[13] is not None else None,
        created_at=str(r[14]),
        updated_at=str(r[15]),
        is_deleted=bool(int(r[16])),
    )


def _event_row(r: tuple[Any, ...]) -> HomeItemServiceEventRow:
    return HomeItemServiceEventRow(
        id=int(r[0]),
        home_item_id=int(r[1]),
        service_date=str(r[2]),
        event_type=str(r[3]),
        vendor=str(r[4]) if r[4] is not None else None,
        description=str(r[5]) if r[5] is not None else None,
        cost_paise=int(r[6]) if r[6] is not None else None,
        next_service_due=str(r[7]) if r[7] is not None else None,
        notes=str(r[8]) if r[8] is not None else None,
        created_at=str(r[9]),
        updated_at=str(r[10]),
    )


_ITEM_SELECT = """
    SELECT id, name, category, brand, model, serial_number, room_location,
           purchase_date, purchase_price_paise, retailer, warranty_end_date,
           extended_warranty, condition_status, notes, created_at, updated_at, is_deleted
    FROM home_items
"""


async def list_home_items(
    conn: aiosqlite.Connection,
    *,
    category: str | None = None,
    room: str | None = None,
) -> list[HomeItemRow]:
    clauses = ["is_deleted = 0"]
    params: list[Any] = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if room:
        clauses.append("room_location = ?")
        params.append(room)
    where = " AND ".join(clauses)
    cur = await conn.execute(
        f"{_ITEM_SELECT} WHERE {where} ORDER BY name COLLATE NOCASE",
        params,
    )
    rows = await cur.fetchall()
    return [_item_row(tuple(x)) for x in rows]


async def get_home_item(conn: aiosqlite.Connection, item_id: int) -> HomeItemRow | None:
    cur = await conn.execute(f"{_ITEM_SELECT} WHERE id = ?", (item_id,))
    r = await cur.fetchone()
    return _item_row(tuple(r)) if r else None


async def insert_home_item(
    conn: aiosqlite.Connection,
    *,
    name: str,
    category: str,
    brand: str | None,
    model: str | None,
    serial_number: str | None,
    room_location: str | None,
    purchase_date: str | None,
    purchase_price_paise: int | None,
    retailer: str | None,
    warranty_end_date: str | None,
    extended_warranty: bool,
    condition_status: str,
    notes: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO home_items (
            name, category, brand, model, serial_number, room_location,
            purchase_date, purchase_price_paise, retailer, warranty_end_date,
            extended_warranty, condition_status, notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            name,
            category,
            brand,
            model,
            serial_number,
            room_location,
            purchase_date,
            purchase_price_paise,
            retailer,
            warranty_end_date,
            1 if extended_warranty else 0,
            condition_status,
            notes,
        ),
    )
    await conn.commit()
    lid = cur.lastrowid
    if lid is None:
        msg = "INSERT home_items did not set lastrowid"
        raise RuntimeError(msg)
    return int(lid)


async def update_home_item(
    conn: aiosqlite.Connection,
    *,
    item_id: int,
    name: str,
    category: str,
    brand: str | None,
    model: str | None,
    serial_number: str | None,
    room_location: str | None,
    purchase_date: str | None,
    purchase_price_paise: int | None,
    retailer: str | None,
    warranty_end_date: str | None,
    extended_warranty: bool,
    condition_status: str,
    notes: str | None,
) -> bool:
    cur = await conn.execute(
        """
        UPDATE home_items SET
            name = ?, category = ?, brand = ?, model = ?, serial_number = ?,
            room_location = ?, purchase_date = ?, purchase_price_paise = ?,
            retailer = ?, warranty_end_date = ?, extended_warranty = ?,
            condition_status = ?, notes = ?, updated_at = datetime('now')
        WHERE id = ? AND is_deleted = 0
        """,
        (
            name,
            category,
            brand,
            model,
            serial_number,
            room_location,
            purchase_date,
            purchase_price_paise,
            retailer,
            warranty_end_date,
            1 if extended_warranty else 0,
            condition_status,
            notes,
            item_id,
        ),
    )
    await conn.commit()
    return cur.rowcount > 0


async def soft_delete_home_item(conn: aiosqlite.Connection, item_id: int) -> bool:
    cur = await conn.execute(
        """
        UPDATE home_items SET is_deleted = 1, updated_at = datetime('now')
        WHERE id = ? AND is_deleted = 0
        """,
        (item_id,),
    )
    await conn.commit()
    return cur.rowcount > 0


async def list_service_events(
    conn: aiosqlite.Connection,
    home_item_id: int,
) -> list[HomeItemServiceEventRow]:
    cur = await conn.execute(
        """
        SELECT id, home_item_id, service_date, event_type, vendor, description,
               cost_paise, next_service_due, notes, created_at, updated_at
        FROM home_item_service_events
        WHERE home_item_id = ?
        ORDER BY service_date DESC, id DESC
        """,
        (home_item_id,),
    )
    rows = await cur.fetchall()
    return [_event_row(tuple(x)) for x in rows]


async def get_service_event(
    conn: aiosqlite.Connection,
    event_id: int,
    home_item_id: int,
) -> HomeItemServiceEventRow | None:
    cur = await conn.execute(
        """
        SELECT id, home_item_id, service_date, event_type, vendor, description,
               cost_paise, next_service_due, notes, created_at, updated_at
        FROM home_item_service_events
        WHERE id = ? AND home_item_id = ?
        """,
        (event_id, home_item_id),
    )
    r = await cur.fetchone()
    return _event_row(tuple(r)) if r else None


async def insert_service_event(
    conn: aiosqlite.Connection,
    *,
    home_item_id: int,
    service_date: str,
    event_type: str,
    vendor: str | None,
    description: str | None,
    cost_paise: int | None,
    next_service_due: str | None,
    notes: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO home_item_service_events (
            home_item_id, service_date, event_type, vendor, description,
            cost_paise, next_service_due, notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            home_item_id,
            service_date,
            event_type,
            vendor,
            description,
            cost_paise,
            next_service_due,
            notes,
        ),
    )
    await conn.commit()
    lid = cur.lastrowid
    if lid is None:
        msg = "INSERT service event did not set lastrowid"
        raise RuntimeError(msg)
    return int(lid)


async def update_service_event(
    conn: aiosqlite.Connection,
    *,
    event_id: int,
    home_item_id: int,
    service_date: str,
    event_type: str,
    vendor: str | None,
    description: str | None,
    cost_paise: int | None,
    next_service_due: str | None,
    notes: str | None,
) -> bool:
    cur = await conn.execute(
        """
        UPDATE home_item_service_events SET
            service_date = ?, event_type = ?, vendor = ?, description = ?,
            cost_paise = ?, next_service_due = ?, notes = ?,
            updated_at = datetime('now')
        WHERE id = ? AND home_item_id = ?
        """,
        (
            service_date,
            event_type,
            vendor,
            description,
            cost_paise,
            next_service_due,
            notes,
            event_id,
            home_item_id,
        ),
    )
    await conn.commit()
    return cur.rowcount > 0


async def delete_service_event(
    conn: aiosqlite.Connection,
    *,
    event_id: int,
    home_item_id: int,
) -> bool:
    cur = await conn.execute(
        "DELETE FROM home_item_service_events WHERE id = ? AND home_item_id = ?",
        (event_id, home_item_id),
    )
    await conn.commit()
    return cur.rowcount > 0


async def summary_stats(conn: aiosqlite.Connection) -> dict[str, Any]:
    cur = await conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            COALESCE(SUM(purchase_price_paise), 0) AS purchase_total
        FROM home_items WHERE is_deleted = 0
        """
    )
    r1 = await cur.fetchone()
    n = int(r1[0]) if r1 else 0
    purchase_total = int(r1[1]) if r1 else 0

    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(e.cost_paise), 0)
        FROM home_item_service_events e
        INNER JOIN home_items i ON i.id = e.home_item_id AND i.is_deleted = 0
        """
    )
    r2 = await cur.fetchone()
    service_total = int(r2[0]) if r2 and r2[0] is not None else 0

    cur = await conn.execute(
        """
        SELECT category, COUNT(*) FROM home_items
        WHERE is_deleted = 0
        GROUP BY category ORDER BY COUNT(*) DESC
        """
    )
    by_cat = {str(row[0]): int(row[1]) for row in await cur.fetchall()}

    cur = await conn.execute(
        """
        SELECT COUNT(*) FROM home_items
        WHERE is_deleted = 0
          AND warranty_end_date IS NOT NULL
          AND warranty_end_date >= date('now')
          AND warranty_end_date <= date('now', '+90 days')
        """
    )
    r3 = await cur.fetchone()
    warranty_expiring_90d = int(r3[0]) if r3 else 0

    return {
        "item_count": n,
        "purchase_value_total_paise": purchase_total,
        "service_spend_total_paise": service_total,
        "count_by_category": by_cat,
        "warranty_expiring_within_90_days": warranty_expiring_90d,
    }


async def total_service_for_item(conn: aiosqlite.Connection, home_item_id: int) -> int:
    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(cost_paise), 0) FROM home_item_service_events
        WHERE home_item_id = ?
        """,
        (home_item_id,),
    )
    r = await cur.fetchone()
    return int(r[0]) if r and r[0] is not None else 0
