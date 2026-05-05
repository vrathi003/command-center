"""Financial goals API."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn
from finance_api.schemas.goal import GoalCreate, GoalOut, GoalPut
from finance_common.repositories import goals as goals_repo
from finance_common.repositories.goals import GoalRow

router = APIRouter(prefix="/goals", tags=["goals"])


def _progress(row: GoalRow) -> float | None:
    if row.target_amount_paise <= 0:
        return None
    return min(100.0, 100.0 * row.current_amount_paise / row.target_amount_paise)


def _to_out(row: GoalRow) -> GoalOut:
    return GoalOut(
        id=row.id,
        name=row.name,
        category=row.category,
        target_amount_paise=row.target_amount_paise,
        current_amount_paise=row.current_amount_paise,
        monthly_contribution_paise=row.monthly_contribution_paise,
        target_date=row.target_date,
        progress_pct=_progress(row),
    )


@router.get("/", response_model=list[GoalOut])
async def list_goals(conn: Annotated[aiosqlite.Connection, Depends(get_conn)]) -> list[GoalOut]:
    rows = await goals_repo.list_goals(conn)
    return [_to_out(r) for r in rows]


@router.post("/", response_model=GoalOut, status_code=201)
async def create_goal(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: GoalCreate,
) -> GoalOut:
    gid = await goals_repo.insert_goal(
        conn,
        name=body.name,
        category=body.category,
        target_amount_paise=body.target_amount_paise,
        current_amount_paise=body.current_amount_paise,
        monthly_contribution_paise=body.monthly_contribution_paise,
        target_date=body.target_date,
    )
    row = await goals_repo.get_goal(conn, gid)
    if row is None:
        raise HTTPException(status_code=500, detail="goal not found after insert")
    return _to_out(row)


@router.get("/{goal_id}", response_model=GoalOut)
async def get_goal(
    goal_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> GoalOut:
    row = await goals_repo.get_goal(conn, goal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="goal not found")
    return _to_out(row)


@router.put("/{goal_id}", response_model=GoalOut)
async def put_goal(
    goal_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: GoalPut,
) -> GoalOut:
    existing = await goals_repo.get_goal(conn, goal_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="goal not found")
    await goals_repo.update_goal(
        conn,
        goal_id=goal_id,
        name=body.name,
        category=body.category,
        target_amount_paise=body.target_amount_paise,
        current_amount_paise=body.current_amount_paise,
        monthly_contribution_paise=body.monthly_contribution_paise,
        target_date=body.target_date,
    )
    row = await goals_repo.get_goal(conn, goal_id)
    if row is None:
        raise HTTPException(status_code=500, detail="goal not found after update")
    return _to_out(row)


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> None:
    ok = await goals_repo.delete_goal(conn, goal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="goal not found")
