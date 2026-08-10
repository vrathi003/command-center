"""HTTP API for migrating legacy transactions to the ledger."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends

from finance_api.deps import get_conn, get_settings
from finance_api.deps_ledger import require_ledger_writes
from finance_api.schemas.migration import MigrationReportResponse
from finance_api.settings import ApiSettings
from finance_common.migration import service as migration_service

router = APIRouter(prefix="/migration", tags=["migration"])


@router.post(
    "/legacy-ledger/dry-run",
    response_model=MigrationReportResponse,
)
async def dry_run_legacy_ledger_migration(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> MigrationReportResponse:
    """Preview the legacy migration without modifying the database."""
    return MigrationReportResponse.from_report(await migration_service.dry_run(conn))


@router.post(
    "/legacy-ledger/apply",
    response_model=MigrationReportResponse,
)
async def apply_legacy_ledger_migration(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
    _: Annotated[None, Depends(require_ledger_writes)],
) -> MigrationReportResponse:
    """Back up and migrate legacy transactions to the immutable ledger."""
    report = await migration_service.apply(conn, db_path=settings.db_path)
    return MigrationReportResponse.from_report(report)
