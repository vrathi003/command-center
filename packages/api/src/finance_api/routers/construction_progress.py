"""Construction progress — builder PDF uploads and time series."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Annotated, Any

import aiosqlite
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from finance_api.deps import get_conn
from finance_api.schemas.construction import (
    ConstructionDeleteAllOut,
    ConstructionProgressRowOut,
    ConstructionProjectOut,
    ConstructionSeriesOut,
    ConstructionSeriesPoint,
    ConstructionSnapshotDetailOut,
    ConstructionSnapshotOut,
    ConstructionTowerDashboardOut,
    ConstructionUploadResponse,
    TowerDashboardActivityRow,
    TowerTrendPoint,
    ZoneLabelsOut,
    ZoneLabelsPut,
)
from finance_common.construction_metrics import (
    effective_completion_pct,
    floors_pct_of_total,
)
from finance_common.parsing.construction_update_pdf import parse_construction_pdf_bytes
from finance_common.repositories import construction_progress as repo

router = APIRouter(prefix="/construction", tags=["construction"])

MAX_BYTES = 25 * 1024 * 1024

DEFAULT_TOTAL_FLOORS = 26


def _tower_row_metrics(
    r: repo.ConstructionProgressRow,
    *,
    total_floors: int,
) -> tuple[int | None, int | None]:
    eff = effective_completion_pct(
        r.pct_complete,
        r.floors_complete,
        total_floors=total_floors,
    )
    fl_pct = floors_pct_of_total(r.floors_complete, total_floors=total_floors)
    return eff, fl_pct


def _avg_metrics_for_rows(
    rows: list[repo.ConstructionProgressRow],
    *,
    total_floors: int,
) -> tuple[float | None, float | None]:
    effs: list[int] = []
    fls: list[int] = []
    for r in rows:
        eff, fl_pct = _tower_row_metrics(r, total_floors=total_floors)
        if eff is not None:
            effs.append(eff)
        if fl_pct is not None:
            fls.append(fl_pct)
    avg_e = sum(effs) / len(effs) if effs else None
    avg_f = sum(fls) / len(fls) if fls else None
    return avg_e, avg_f

_MONTH_TOKEN = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-'\s]?(\d{2,4})",
    re.IGNORECASE,
)


def _infer_date_from_filename(filename: str) -> date | None:
    m = _MONTH_TOKEN.search(filename)
    if not m:
        return None
    mon_s = m.group(1).lower()[:3]
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month = months.get(mon_s)
    if month is None:
        return None
    y_raw = m.group(2)
    year = int(y_raw)
    if year < 100:
        year += 2000
    try:
        return date(year, month, 1)
    except ValueError:
        return None


def _default_label_for_zone(zone_key: str) -> str:
    if zone_key.startswith("tower:"):
        return f"Tower {zone_key.split(':', 1)[1]}"
    if zone_key.startswith("section:"):
        return zone_key.split(":", 1)[1].replace("_", " ").title()
    return zone_key


@router.get("/projects", response_model=list[ConstructionProjectOut])
async def list_projects(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[ConstructionProjectOut]:
    rows = await repo.list_projects(conn)
    return [ConstructionProjectOut(id=r.id, name=r.name) for r in rows]


@router.delete("/all-data", response_model=ConstructionDeleteAllOut)
async def delete_all_construction_data(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> ConstructionDeleteAllOut:
    """Delete every construction snapshot, progress row, zone label, and project (full reset)."""
    counts = await repo.delete_all_construction_data(conn)
    return ConstructionDeleteAllOut(
        snapshots_deleted=counts["snapshots_deleted"],
        zone_labels_deleted=counts["zone_labels_deleted"],
        projects_deleted=counts["projects_deleted"],
    )


@router.post("/upload", response_model=ConstructionUploadResponse)
async def upload_report(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    file: UploadFile = File(...),
) -> ConstructionUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file name is required")
    name_lower = file.filename.lower().strip()
    if not name_lower.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF uploads are supported for construction reports. "
            "Convert Excel or PowerPoint to PDF and upload.",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="file is empty")
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"file too large (max {MAX_BYTES // (1024 * 1024)} MB)",
        )

    parsed = parse_construction_pdf_bytes(content)
    warnings = list(parsed.warnings)

    as_of = parsed.as_of_date
    if as_of is None:
        inferred = _infer_date_from_filename(file.filename)
        if inferred:
            as_of = inferred
            warnings.append("as_of_date inferred from filename (header not parsed).")
        else:
            as_of = date.today()
            warnings.append("as_of_date defaulted to today (could not parse header or filename).")

    as_of_str = as_of.isoformat()

    project = await repo.get_or_create_default_project(conn)
    sha = hashlib.sha256(content).hexdigest()

    zone_payload: list[dict[str, Any]] = []
    total_rows = 0
    for z in parsed.zones:
        rows = []
        for r in z.rows:
            rows.append(
                {
                    "section": r.section,
                    "activity_raw": r.activity_raw,
                    "floors_complete": r.floors_complete,
                    "pct_complete": r.pct_complete,
                    "status": r.status,
                    "remark": r.remark,
                },
            )
        total_rows += len(rows)
        zone_payload.append(
            {
                "zone_key": z.zone_key,
                "zone_type": z.zone_type,
                "tower_number": z.tower_number,
                "tabular_index": z.tabular_index,
                "rows": rows,
            },
        )

    sid = await repo.replace_snapshot(
        conn,
        project_id=project.id,
        as_of_date=as_of_str,
        source_filename=file.filename,
        file_sha256=sha,
        parse_warnings=warnings,
        zone_rows=zone_payload,
    )

    return ConstructionUploadResponse(
        snapshot_id=sid,
        as_of_date=as_of_str,
        project_id=project.id,
        parse_warnings=warnings,
        zones_parsed=len(parsed.zones),
        rows_parsed=total_rows,
    )


def _snapshot_out(
    row: repo.ConstructionSnapshotRow,
    *,
    row_count: int = 0,
) -> ConstructionSnapshotOut:
    warns: list[str] = []
    if row.parse_warnings_json:
        try:
            raw = json.loads(row.parse_warnings_json)
            if isinstance(raw, list):
                warns = [str(x) for x in raw]
        except json.JSONDecodeError:
            warns = []
    return ConstructionSnapshotOut(
        id=row.id,
        project_id=row.project_id,
        as_of_date=row.as_of_date,
        source_filename=row.source_filename,
        file_sha256=row.file_sha256,
        parse_warnings=warns,
        row_count=row_count,
    )


@router.get("/snapshots", response_model=list[ConstructionSnapshotOut])
async def list_snapshots(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    project_id: Annotated[int | None, Query()] = None,
) -> list[ConstructionSnapshotOut]:
    pid = project_id
    if pid is None:
        p = await repo.get_or_create_default_project(conn)
        pid = p.id
    snaps = await repo.list_snapshots(conn, project_id=pid)
    out: list[ConstructionSnapshotOut] = []
    for s in snaps:
        rows = await repo.list_progress_rows(conn, snapshot_id=s.id)
        out.append(_snapshot_out(s, row_count=len(rows)))
    return out


@router.get("/snapshots/{snapshot_id}", response_model=ConstructionSnapshotDetailOut)
async def get_snapshot_detail(
    snapshot_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> ConstructionSnapshotDetailOut:
    s = await repo.get_snapshot(conn, snapshot_id=snapshot_id)
    if s is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    rows = await repo.list_progress_rows(conn, snapshot_id=snapshot_id)
    prow = [
        ConstructionProgressRowOut(
            id=r.id,
            zone_key=r.zone_key,
            zone_type=r.zone_type,
            tower_number=r.tower_number,
            section=r.section,
            activity_raw=r.activity_raw,
            floors_complete=r.floors_complete,
            pct_complete=r.pct_complete,
            status=r.status,
            remark=r.remark,
        )
        for r in rows
    ]
    return ConstructionSnapshotDetailOut(
        snapshot=_snapshot_out(s, row_count=len(rows)),
        rows=prow,
    )


@router.get("/tower-dashboard", response_model=ConstructionTowerDashboardOut)
async def get_tower_dashboard(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    zone_key: Annotated[str, Query()],
    project_id: Annotated[int | None, Query()] = None,
    total_floors: Annotated[int, Query(ge=1, le=200)] = DEFAULT_TOTAL_FLOORS,
) -> ConstructionTowerDashboardOut:
    """Latest snapshot breakdown + month-on-month tower averages for one zone (e.g. tower:1)."""
    pid = project_id
    if pid is None:
        p = await repo.get_or_create_default_project(conn)
        pid = p.id

    snaps_desc = await repo.list_snapshots(conn, project_id=pid)
    if not snaps_desc:
        return ConstructionTowerDashboardOut(
            zone_key=zone_key,
            total_floors=total_floors,
            latest_snapshot_id=None,
            latest_as_of_date=None,
            latest_snapshot_avg_effective_pct=None,
            latest_snapshot_avg_floors_pct=None,
            activity_rows=[],
            trend=[],
        )

    latest = snaps_desc[0]
    latest_rows_all = await repo.list_progress_rows(conn, snapshot_id=latest.id)
    tower_latest = [r for r in latest_rows_all if r.zone_key == zone_key]
    avg_e_latest, avg_f_latest = _avg_metrics_for_rows(tower_latest, total_floors=total_floors)

    activity_rows: list[TowerDashboardActivityRow] = []
    for r in tower_latest:
        eff, fl_pct = _tower_row_metrics(r, total_floors=total_floors)
        activity_rows.append(
            TowerDashboardActivityRow(
                section=r.section,
                activity_raw=r.activity_raw,
                pct_reported=r.pct_complete,
                floors_complete=r.floors_complete,
                effective_pct=eff,
                floors_pct_of_total=fl_pct,
                status=r.status,
            ),
        )

    trend: list[TowerTrendPoint] = []
    snaps_asc = await repo.list_snapshots_asc(conn, project_id=pid)
    for s in snaps_asc:
        rows_all = await repo.list_progress_rows(conn, snapshot_id=s.id)
        tower = [r for r in rows_all if r.zone_key == zone_key]
        avg_e, avg_f = _avg_metrics_for_rows(tower, total_floors=total_floors)
        trend.append(
            TowerTrendPoint(
                snapshot_id=s.id,
                as_of_date=s.as_of_date,
                avg_effective_pct=avg_e,
                avg_floors_pct=avg_f,
                activity_count=len(tower),
            ),
        )

    return ConstructionTowerDashboardOut(
        zone_key=zone_key,
        total_floors=total_floors,
        latest_snapshot_id=latest.id,
        latest_as_of_date=latest.as_of_date,
        latest_snapshot_avg_effective_pct=avg_e_latest,
        latest_snapshot_avg_floors_pct=avg_f_latest,
        activity_rows=activity_rows,
        trend=trend,
    )


@router.get("/series", response_model=ConstructionSeriesOut)
async def get_series(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    zone_key: Annotated[str, Query()],
    activity_raw: Annotated[str, Query()],
    project_id: Annotated[int | None, Query()] = None,
) -> ConstructionSeriesOut:
    pid = project_id
    if pid is None:
        p = await repo.get_or_create_default_project(conn)
        pid = p.id
    pts = await repo.series_for_activity(
        conn,
        project_id=pid,
        zone_key=zone_key,
        activity_raw=activity_raw,
    )
    return ConstructionSeriesOut(
        zone_key=zone_key,
        activity_raw=activity_raw,
        points=[
            ConstructionSeriesPoint(
                as_of_date=d,
                pct_complete=pct,
                floors_complete=fl,
            )
            for d, pct, fl in pts
        ],
    )


@router.get("/zones", response_model=list[str])
async def list_zones(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    project_id: Annotated[int | None, Query()] = None,
) -> list[str]:
    pid = project_id
    if pid is None:
        p = await repo.get_or_create_default_project(conn)
        pid = p.id
    return await repo.list_zone_keys(conn, project_id=pid)


@router.get("/zones/{zone_key}/activities", response_model=list[str])
async def list_zone_activities(
    zone_key: str,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    project_id: Annotated[int | None, Query()] = None,
) -> list[str]:
    pid = project_id
    if pid is None:
        p = await repo.get_or_create_default_project(conn)
        pid = p.id
    return await repo.list_activities_for_zone(
        conn,
        project_id=pid,
        zone_key=zone_key,
    )


@router.get("/zone-labels", response_model=ZoneLabelsOut)
async def get_zone_labels(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    project_id: Annotated[int | None, Query()] = None,
) -> ZoneLabelsOut:
    pid = project_id
    if pid is None:
        p = await repo.get_or_create_default_project(conn)
        pid = p.id
    raw = await repo.get_zone_labels(conn, project_id=pid)
    zones = await repo.list_zone_keys(conn, project_id=pid)
    merged: dict[str, str] = {}
    for zk in zones:
        merged[zk] = raw.get(zk) or _default_label_for_zone(zk)
    for k, v in raw.items():
        if k not in merged:
            merged[k] = v
    return ZoneLabelsOut(labels=merged)


@router.put("/zone-labels", response_model=ZoneLabelsOut)
async def put_zone_labels(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: ZoneLabelsPut,
    project_id: Annotated[int | None, Query()] = None,
) -> ZoneLabelsOut:
    pid = project_id
    if pid is None:
        p = await repo.get_or_create_default_project(conn)
        pid = p.id
    for item in body.labels:
        await repo.upsert_zone_label(
            conn,
            project_id=pid,
            zone_key=item.zone_key,
            label=item.label,
        )
    return await get_zone_labels(conn, project_id=pid)
