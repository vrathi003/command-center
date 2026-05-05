"""Budget API — monthly caps vs actual spend."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from finance_api.deps import get_conn
from finance_api.schemas.budget import (
    BudgetCurrentResponse,
    BudgetCurrentRow,
    BudgetHistoryResponse,
    BudgetHistoryRow,
    BudgetPutBody,
    BudgetRenameBody,
    BudgetVsActualResponse,
)
from finance_api.services.budget_service import build_vs_actual
from finance_common.repositories import budgets as budget_repo
from finance_common.repositories import settings_repo

router = APIRouter(prefix="/budget", tags=["budget"])


@router.get("/current", response_model=BudgetCurrentResponse)
async def get_budget_current(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> BudgetCurrentResponse:
    fy = await settings_repo.get_current_fy(conn)
    rows = await budget_repo.effective_budgets_for_fy(conn, str(fy))
    return BudgetCurrentResponse(
        fy=str(fy),
        budgets=[
            BudgetCurrentRow(
                category=r.category,
                monthly_amount_paise=r.monthly_amount_paise,
                effective_from=r.effective_from,
            )
            for r in rows
        ],
    )


@router.get("/vs-actual", response_model=BudgetVsActualResponse)
async def get_budget_vs_actual(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
) -> BudgetVsActualResponse:
    today = date.today()
    y = year if year is not None else today.year
    m = month if month is not None else today.month
    fy = await settings_repo.get_current_fy(conn)
    month_label, rows = await build_vs_actual(conn, fy=str(fy), year=y, month=m)
    return BudgetVsActualResponse(fy=str(fy), month=month_label, rows=rows)


@router.put("/category/{category}", response_model=BudgetCurrentRow)
async def put_budget_category(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    category: str,
    body: BudgetPutBody,
) -> BudgetCurrentRow:
    if not category.strip():
        raise HTTPException(status_code=400, detail="category is required")
    fy = await settings_repo.get_current_fy(conn)
    await budget_repo.set_monthly_budget(
        conn,
        category=category.strip(),
        fy_year=str(fy),
        monthly_amount_paise=body.monthly_amount_paise,
    )
    rows = await budget_repo.effective_budgets_for_fy(conn, str(fy))
    for r in rows:
        if r.category == category.strip():
            return BudgetCurrentRow(
                category=r.category,
                monthly_amount_paise=r.monthly_amount_paise,
                effective_from=r.effective_from,
            )
    return BudgetCurrentRow(
        category=category.strip(),
        monthly_amount_paise=body.monthly_amount_paise,
        effective_from=date.today().isoformat(),
    )


@router.post("/rename-category", status_code=204)
async def rename_budget_category(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: BudgetRenameBody,
) -> None:
    """Rename a category for the current FY (budget rows) and align transactions / maps / goals."""
    old = body.old_category.strip()
    new = body.new_category.strip()
    if not old or not new:
        raise HTTPException(status_code=400, detail="category names are required")
    if old == new:
        raise HTTPException(status_code=400, detail="old and new category must differ")
    fy = await settings_repo.get_current_fy(conn)
    try:
        await budget_repo.rename_category_for_fy(
            conn,
            old_category=old,
            new_category=new,
            fy_year=str(fy),
        )
    except ValueError as e:
        code = str(e.args[0]) if e.args else ""
        if code == "category_budget_conflict":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Both categories already have budgets for this FY; remove or merge manually."
                ),
            ) from e
        raise HTTPException(status_code=400, detail="invalid rename") from e


@router.delete("/category/{category}", status_code=204)
async def delete_budget_category(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    category: str,
) -> None:
    if not category.strip():
        raise HTTPException(status_code=400, detail="category is required")
    fy = await settings_repo.get_current_fy(conn)
    await budget_repo.delete_category_for_fy(
        conn,
        category=category.strip(),
        fy_year=str(fy),
    )


@router.get("/history", response_model=BudgetHistoryResponse)
async def get_budget_history(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    fy: str | None = Query(default=None, description="FY like 2025-26; defaults to current"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> BudgetHistoryResponse:
    target_fy = fy
    if target_fy is None:
        target_fy = str(await settings_repo.get_current_fy(conn))
    raw = await budget_repo.list_history(conn, fy_year=target_fy, limit=limit)
    return BudgetHistoryResponse(
        fy=target_fy,
        entries=[
            BudgetHistoryRow(
                category=t[0],
                monthly_amount_paise=t[1],
                effective_from=t[2],
                updated_at=t[3],
            )
            for t in raw
        ],
    )
