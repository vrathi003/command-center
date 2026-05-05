"""Daily journal API."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder

from finance_api.deps import get_conn
from finance_api.schemas.journal import JournalEntryOut, JournalPut
from finance_common.repositories import journal as journal_repo

router = APIRouter(prefix="/journal", tags=["journal"])


def _parse_iso_date(label: str, value: str) -> str:
    try:
        d = date.fromisoformat(value)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"invalid {label}") from e
    return d.isoformat()


@router.get("/", response_model=list[JournalEntryOut])
async def list_journal_entries(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
) -> list[JournalEntryOut]:
    today = date.today()
    if date_from is None and date_to is None:
        df = (today - timedelta(days=90)).isoformat()
        dt = today.isoformat()
    else:
        if date_from is None or date_to is None:
            raise HTTPException(
                status_code=422, detail="from and to must both be set or both omitted"
            )
        df = _parse_iso_date("from", date_from)
        dt = _parse_iso_date("to", date_to)
        if df > dt:
            raise HTTPException(status_code=422, detail="from must be <= to")

    rows = await journal_repo.list_between(conn, date_from=df, date_to=dt)
    return [
        JournalEntryOut(
            entry_date=r.entry_date,
            body=r.body,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get("/{entry_date}", response_model=JournalEntryOut)
async def get_journal_entry(
    entry_date: str,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> JournalEntryOut:
    d = _parse_iso_date("entry_date", entry_date)
    row = await journal_repo.get_by_date(conn, d)
    if row is None:
        raise HTTPException(status_code=404, detail="journal entry not found")
    return JournalEntryOut(
        entry_date=row.entry_date,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.put("/{entry_date}")
async def put_journal_entry(
    entry_date: str,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: JournalPut,
) -> Response:
    d = _parse_iso_date("entry_date", entry_date)
    text = body.body.strip()
    if text == "":
        await journal_repo.delete_by_date(conn, d)
        return Response(status_code=204)

    row = await journal_repo.upsert(conn, entry_date=d, body=text)
    out = JournalEntryOut(
        entry_date=row.entry_date,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return Response(
        content=json.dumps(jsonable_encoder(out.model_dump())),
        media_type="application/json",
        status_code=200,
    )
