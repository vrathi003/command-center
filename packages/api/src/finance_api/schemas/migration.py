"""Response schemas for legacy ledger migration."""

from __future__ import annotations

from pydantic import BaseModel

from finance_common.migration.models import MigrationReport


class MigrationReportResponse(BaseModel):
    migrated: int
    quarantined: int
    skipped_deleted: int
    noop: int
    backup_path: str | None
    cutover_at: str | None
    backup_sha256: str | None

    @classmethod
    def from_report(cls, report: MigrationReport) -> MigrationReportResponse:
        return cls(
            migrated=report.migrated,
            quarantined=report.quarantined,
            skipped_deleted=report.skipped_deleted,
            noop=report.noop,
            backup_path=report.backup_path,
            cutover_at=report.cutover_at,
            backup_sha256=report.backup_sha256,
        )
