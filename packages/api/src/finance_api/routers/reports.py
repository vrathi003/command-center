"""FY reports (spending by month, summary)."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from finance_api.deps import get_conn
from finance_api.schemas.reports import FYMonthSpendingRow, FYSpendingReport, FYSummaryReport
from finance_api.services.pdf_report import build_fy_pdf
from finance_api.services.reports_service import build_fy_spending, build_fy_summary
from finance_common.fy import fy_start
from finance_common.repositories import settings_repo
from finance_common.types import FYYear

router = APIRouter(prefix="/reports", tags=["reports"])


async def _resolve_fy(conn: aiosqlite.Connection, fy: str | None) -> FYYear:
    if fy is None:
        return await settings_repo.get_current_fy(conn)
    try:
        fy_start(FYYear(fy.strip()))
    except Exception as e:
        raise HTTPException(status_code=422, detail="Invalid FY format") from e
    return FYYear(fy.strip())


@router.get("/fy-spending", response_model=FYSpendingReport)
async def fy_spending(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    fy: str | None = Query(default=None, description="YYYY-YY; defaults to settings current FY"),
) -> FYSpendingReport:
    fy_obj = await _resolve_fy(conn, fy)
    fy_s, rows, total = await build_fy_spending(conn, fy_obj)
    return FYSpendingReport(
        fy=fy_s,
        rows=[FYMonthSpendingRow.model_validate(r) for r in rows],
        total_spent_paise=total,
    )


@router.get("/fy-summary", response_model=FYSummaryReport)
async def fy_summary(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    fy: str | None = Query(default=None, description="YYYY-YY; defaults to settings current FY"),
) -> FYSummaryReport:
    fy_obj = await _resolve_fy(conn, fy)
    fy_s, spent, run_rate, implied = await build_fy_summary(conn, fy_obj)
    return FYSummaryReport(
        fy=fy_s,
        total_spent_paise=spent,
        total_monthly_income_run_rate_paise=run_rate,
        implied_savings_paise=implied,
    )


@router.get("/fy-summary.pdf")
async def fy_summary_pdf(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    fy: str | None = Query(default=None, description="YYYY-YY; defaults to settings current FY"),
) -> Response:
    """Download FY spending + summary as PDF."""
    fy_obj = await _resolve_fy(conn, fy)
    fy_s, rows, _ = await build_fy_spending(conn, fy_obj)
    _, spent, run_rate, implied = await build_fy_summary(conn, fy_obj)
    table_rows = [(str(r["label"]), int(r["spent_paise"])) for r in rows]
    pdf_bytes = build_fy_pdf(
        fy_label=fy_s,
        rows=table_rows,
        total_spent_paise=spent,
        income_run_rate_annual_paise=run_rate,
        implied_savings_paise=implied,
    )
    safe = fy_s.replace("/", "-")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="fy-{safe}-summary.pdf"',
        },
    )
