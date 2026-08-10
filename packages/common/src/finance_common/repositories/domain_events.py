"""Append-only domain event persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping

import aiosqlite


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
