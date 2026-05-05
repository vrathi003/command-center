"""Construction progress snapshots and rows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import aiosqlite

from finance_common.parsing.construction_update_pdf import normalized_activity_key


@dataclass(frozen=True, slots=True)
class ConstructionProjectRow:
    id: int
    name: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ConstructionSnapshotRow:
    id: int
    project_id: int
    as_of_date: str
    source_filename: str
    file_sha256: str | None
    parse_warnings_json: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class ConstructionProgressRow:
    id: int
    snapshot_id: int
    zone_key: str
    zone_type: str
    tower_number: int | None
    tabular_index: int | None
    section: str
    activity_raw: str
    activity_normalized_key: str | None
    floors_complete: int | None
    pct_complete: int | None
    status: str | None
    remark: str | None
    sort_order: int


def _proj(r: tuple[Any, ...]) -> ConstructionProjectRow:
    return ConstructionProjectRow(id=int(r[0]), name=str(r[1]), created_at=str(r[2]))


def _snap(r: tuple[Any, ...]) -> ConstructionSnapshotRow:
    return ConstructionSnapshotRow(
        id=int(r[0]),
        project_id=int(r[1]),
        as_of_date=str(r[2]),
        source_filename=str(r[3]),
        file_sha256=str(r[4]) if r[4] is not None else None,
        parse_warnings_json=str(r[5]) if r[5] is not None else None,
        created_at=str(r[6]),
    )


def _prow(r: tuple[Any, ...]) -> ConstructionProgressRow:
    return ConstructionProgressRow(
        id=int(r[0]),
        snapshot_id=int(r[1]),
        zone_key=str(r[2]),
        zone_type=str(r[3]),
        tower_number=int(r[4]) if r[4] is not None else None,
        tabular_index=int(r[5]) if r[5] is not None else None,
        section=str(r[6]),
        activity_raw=str(r[7]),
        activity_normalized_key=str(r[8]) if r[8] is not None else None,
        floors_complete=int(r[9]) if r[9] is not None else None,
        pct_complete=int(r[10]) if r[10] is not None else None,
        status=str(r[11]) if r[11] is not None else None,
        remark=str(r[12]) if r[12] is not None else None,
        sort_order=int(r[13]),
    )


async def get_or_create_default_project(
    conn: aiosqlite.Connection,
    *,
    name: str = "ATS Destinaire",
) -> ConstructionProjectRow:
    cur = await conn.execute(
        "SELECT id, name, created_at FROM construction_projects ORDER BY id LIMIT 1",
    )
    row = await cur.fetchone()
    if row:
        return _proj(tuple(row))
    await conn.execute(
        "INSERT INTO construction_projects (name) VALUES (?)",
        (name,),
    )
    await conn.commit()
    cur = await conn.execute(
        "SELECT id, name, created_at FROM construction_projects ORDER BY id DESC LIMIT 1",
    )
    row2 = await cur.fetchone()
    assert row2 is not None
    return _proj(tuple(row2))


async def list_projects(conn: aiosqlite.Connection) -> list[ConstructionProjectRow]:
    cur = await conn.execute(
        "SELECT id, name, created_at FROM construction_projects ORDER BY id",
    )
    rows = await cur.fetchall()
    return [_proj(tuple(r)) for r in rows]


async def list_snapshots(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
) -> list[ConstructionSnapshotRow]:
    cur = await conn.execute(
        """
        SELECT id, project_id, as_of_date, source_filename, file_sha256,
               parse_warnings_json, created_at
        FROM construction_snapshots
        WHERE project_id = ?
        ORDER BY as_of_date DESC
        """,
        (project_id,),
    )
    rows = await cur.fetchall()
    return [_snap(tuple(r)) for r in rows]


async def list_snapshots_asc(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
) -> list[ConstructionSnapshotRow]:
    cur = await conn.execute(
        """
        SELECT id, project_id, as_of_date, source_filename, file_sha256,
               parse_warnings_json, created_at
        FROM construction_snapshots
        WHERE project_id = ?
        ORDER BY as_of_date ASC
        """,
        (project_id,),
    )
    rows = await cur.fetchall()
    return [_snap(tuple(r)) for r in rows]


async def get_snapshot(
    conn: aiosqlite.Connection,
    *,
    snapshot_id: int,
) -> ConstructionSnapshotRow | None:
    cur = await conn.execute(
        """
        SELECT id, project_id, as_of_date, source_filename, file_sha256,
               parse_warnings_json, created_at
        FROM construction_snapshots WHERE id = ?
        """,
        (snapshot_id,),
    )
    row = await cur.fetchone()
    return _snap(tuple(row)) if row else None


async def get_snapshot_by_project_and_date(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
    as_of_date: str,
) -> ConstructionSnapshotRow | None:
    cur = await conn.execute(
        """
        SELECT id, project_id, as_of_date, source_filename, file_sha256,
               parse_warnings_json, created_at
        FROM construction_snapshots
        WHERE project_id = ? AND as_of_date = ?
        """,
        (project_id, as_of_date),
    )
    row = await cur.fetchone()
    return _snap(tuple(row)) if row else None


async def delete_snapshot_cascade(conn: aiosqlite.Connection, *, snapshot_id: int) -> None:
    await conn.execute("DELETE FROM construction_snapshots WHERE id = ?", (snapshot_id,))
    await conn.commit()


async def delete_all_construction_data(conn: aiosqlite.Connection) -> dict[str, int]:
    """Remove all construction projects (cascades snapshots, progress rows, zone labels)."""
    cur = await conn.execute("SELECT COUNT(*) FROM construction_snapshots")
    n_snaps = int((await cur.fetchone())[0])
    cur = await conn.execute("SELECT COUNT(*) FROM construction_zone_labels")
    n_labels = int((await cur.fetchone())[0])
    cur = await conn.execute("SELECT COUNT(*) FROM construction_projects")
    n_proj = int((await cur.fetchone())[0])
    await conn.execute("DELETE FROM construction_projects")
    await conn.commit()
    return {
        "snapshots_deleted": n_snaps,
        "zone_labels_deleted": n_labels,
        "projects_deleted": n_proj,
    }


async def list_progress_rows(
    conn: aiosqlite.Connection,
    *,
    snapshot_id: int,
) -> list[ConstructionProgressRow]:
    cur = await conn.execute(
        """
        SELECT id, snapshot_id, zone_key, zone_type, tower_number, tabular_index,
               section, activity_raw, activity_normalized_key, floors_complete,
               pct_complete, status, remark, sort_order
        FROM construction_progress_rows
        WHERE snapshot_id = ?
        ORDER BY zone_key, sort_order, id
        """,
        (snapshot_id,),
    )
    rows = await cur.fetchall()
    return [_prow(tuple(r)) for r in rows]


async def replace_snapshot(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
    as_of_date: str,
    source_filename: str,
    file_sha256: str | None,
    parse_warnings: list[str],
    zone_rows: list[dict[str, Any]],
) -> int:
    """Delete existing snapshot for same date if any; insert new snapshot and rows."""
    warnings_json = json.dumps(parse_warnings) if parse_warnings else None
    existing = await get_snapshot_by_project_and_date(
        conn,
        project_id=project_id,
        as_of_date=as_of_date,
    )
    if existing:
        await delete_snapshot_cascade(conn, snapshot_id=existing.id)

    await conn.execute(
        """
        INSERT INTO construction_snapshots (
            project_id, as_of_date, source_filename, file_sha256, parse_warnings_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (project_id, as_of_date, source_filename, file_sha256, warnings_json),
    )
    cur = await conn.execute("SELECT last_insert_rowid()")
    sid_row = await cur.fetchone()
    snapshot_id = int(sid_row[0]) if sid_row else 0

    sort_order = 0
    for z in zone_rows:
        for pr in z["rows"]:
            sort_order += 1
            norm = normalized_activity_key(str(pr["activity_raw"]))
            await conn.execute(
                """
                INSERT INTO construction_progress_rows (
                    snapshot_id, zone_key, zone_type, tower_number, tabular_index,
                    section, activity_raw, activity_normalized_key, floors_complete,
                    pct_complete, status, remark, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    z["zone_key"],
                    z["zone_type"],
                    z.get("tower_number"),
                    z.get("tabular_index"),
                    pr["section"],
                    pr["activity_raw"],
                    norm,
                    pr.get("floors_complete"),
                    pr.get("pct_complete"),
                    pr.get("status"),
                    pr.get("remark"),
                    sort_order,
                ),
            )
    await conn.commit()
    return snapshot_id


async def list_zone_keys(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
) -> list[str]:
    cur = await conn.execute(
        """
        SELECT DISTINCT r.zone_key
        FROM construction_progress_rows r
        JOIN construction_snapshots s ON s.id = r.snapshot_id
        WHERE s.project_id = ?
        ORDER BY r.zone_key
        """,
        (project_id,),
    )
    rows = await cur.fetchall()
    return [str(r[0]) for r in rows]


async def list_activities_for_zone(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
    zone_key: str,
) -> list[str]:
    cur = await conn.execute(
        """
        SELECT DISTINCT r.activity_raw
        FROM construction_progress_rows r
        JOIN construction_snapshots s ON s.id = r.snapshot_id
        WHERE s.project_id = ? AND r.zone_key = ?
        ORDER BY r.activity_raw
        """,
        (project_id, zone_key),
    )
    rows = await cur.fetchall()
    return [str(r[0]) for r in rows]


async def series_for_activity(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
    zone_key: str,
    activity_raw: str,
) -> list[tuple[str, int | None, int | None]]:
    """Return (as_of_date, pct_complete, floors_complete) ordered by date."""
    cur = await conn.execute(
        """
        SELECT s.as_of_date, r.pct_complete, r.floors_complete
        FROM construction_progress_rows r
        JOIN construction_snapshots s ON s.id = r.snapshot_id
        WHERE s.project_id = ? AND r.zone_key = ? AND r.activity_raw = ?
        ORDER BY s.as_of_date ASC
        """,
        (project_id, zone_key, activity_raw),
    )
    rows = await cur.fetchall()
    out: list[tuple[str, int | None, int | None]] = []
    for r in rows:
        pct = int(r[1]) if r[1] is not None else None
        fl = int(r[2]) if r[2] is not None else None
        out.append((str(r[0]), pct, fl))
    return out


async def get_zone_labels(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
) -> dict[str, str]:
    cur = await conn.execute(
        "SELECT zone_key, label FROM construction_zone_labels WHERE project_id = ?",
        (project_id,),
    )
    rows = await cur.fetchall()
    return {str(r[0]): str(r[1]) for r in rows}


async def upsert_zone_label(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
    zone_key: str,
    label: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO construction_zone_labels (project_id, zone_key, label)
        VALUES (?, ?, ?)
        ON CONFLICT(project_id, zone_key) DO UPDATE SET label = excluded.label
        """,
        (project_id, zone_key, label),
    )
    await conn.commit()


async def delete_zone_label(
    conn: aiosqlite.Connection,
    *,
    project_id: int,
    zone_key: str,
) -> None:
    await conn.execute(
        "DELETE FROM construction_zone_labels WHERE project_id = ? AND zone_key = ?",
        (project_id, zone_key),
    )
    await conn.commit()
