"""Append-only domain event persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

import aiosqlite


@dataclass(frozen=True, slots=True)
class DomainEventRow:
    """Persisted domain event awaiting or after outbox processing."""

    id: int
    event_type: str
    payload_json: str
    created_at: str
    processed_at: str | None

_EVENT_COLUMNS = "id, event_type, payload_json, created_at, processed_at"


def _event_from_row(row: tuple[object, ...]) -> DomainEventRow:
    return DomainEventRow(
        id=int(row[0]),
        event_type=str(row[1]),
        payload_json=str(row[2]),
        created_at=str(row[3]),
        processed_at=str(row[4]) if row[4] is not None else None,
    )


async def append_event(
    conn: aiosqlite.Connection,
    *,
    event_type: str,
    payload: Mapping[str, object],
) -> int:
    """Append a domain event and return its identifier."""
    cursor = await conn.execute(
        "INSERT INTO domain_events (event_type, payload_json) VALUES (?, ?)",
        (event_type, json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)),
    )
    await conn.commit()
    if cursor.lastrowid is None:
        raise RuntimeError("INSERT INTO domain_events did not set lastrowid")
    return int(cursor.lastrowid)


async def list_unprocessed(
    conn: aiosqlite.Connection,
    *,
    limit: int = 100,
) -> list[DomainEventRow]:
    """Return unprocessed domain events in insertion order."""
    cursor = await conn.execute(
        f"""
        SELECT {_EVENT_COLUMNS}
        FROM domain_events
        WHERE processed_at IS NULL
        ORDER BY id ASC
        LIMIT ?
        """,
        (limit,),
    )
    rows = await cursor.fetchall()
    return [_event_from_row(row) for row in rows]


async def mark_processed(
    conn: aiosqlite.Connection,
    event_id: int,
    *,
    when: str | None = None,
) -> None:
    """Mark a domain event as processed."""
    if when is None:
        await conn.execute(
            "UPDATE domain_events SET processed_at = datetime('now') WHERE id = ?",
            (event_id,),
        )
    else:
        await conn.execute(
            "UPDATE domain_events SET processed_at = ? WHERE id = ?",
            (when, event_id),
        )
    await conn.commit()
