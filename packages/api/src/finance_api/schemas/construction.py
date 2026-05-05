"""Construction progress API models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConstructionProjectOut(BaseModel):
    id: int
    name: str


class ConstructionSnapshotOut(BaseModel):
    id: int
    project_id: int
    as_of_date: str
    source_filename: str
    file_sha256: str | None
    parse_warnings: list[str] = Field(default_factory=list)
    row_count: int = 0


class ConstructionProgressRowOut(BaseModel):
    id: int
    zone_key: str
    zone_type: str
    tower_number: int | None
    section: str
    activity_raw: str
    floors_complete: int | None
    pct_complete: int | None
    status: str | None
    remark: str | None


class ConstructionSnapshotDetailOut(BaseModel):
    snapshot: ConstructionSnapshotOut
    rows: list[ConstructionProgressRowOut]


class ConstructionSeriesPoint(BaseModel):
    as_of_date: str
    pct_complete: int | None
    floors_complete: int | None


class ConstructionSeriesOut(BaseModel):
    zone_key: str
    activity_raw: str
    points: list[ConstructionSeriesPoint]


class ZoneLabelIn(BaseModel):
    zone_key: str
    label: str


class ZoneLabelsPut(BaseModel):
    labels: list[ZoneLabelIn]


class ZoneLabelsOut(BaseModel):
    labels: dict[str, str]


class ConstructionUploadResponse(BaseModel):
    snapshot_id: int
    as_of_date: str
    project_id: int
    parse_warnings: list[str]
    zones_parsed: int
    rows_parsed: int


class ConstructionDeleteAllOut(BaseModel):
    snapshots_deleted: int
    zone_labels_deleted: int
    projects_deleted: int


class TowerDashboardActivityRow(BaseModel):
    section: str
    activity_raw: str
    pct_reported: int | None
    floors_complete: int | None
    effective_pct: int | None
    floors_pct_of_total: int | None
    status: str | None = None


class TowerTrendPoint(BaseModel):
    snapshot_id: int
    as_of_date: str
    avg_effective_pct: float | None
    avg_floors_pct: float | None
    activity_count: int


class ConstructionTowerDashboardOut(BaseModel):
    zone_key: str
    total_floors: int
    latest_snapshot_id: int | None
    latest_as_of_date: str | None
    latest_snapshot_avg_effective_pct: float | None
    latest_snapshot_avg_floors_pct: float | None
    activity_rows: list[TowerDashboardActivityRow]
    trend: list[TowerTrendPoint]
