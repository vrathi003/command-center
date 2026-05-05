"""Savings / financial goals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class GoalRow:
    id: int
    name: str
    category: str | None
    target_amount_paise: int
    current_amount_paise: int
    monthly_contribution_paise: int | None
    target_date: str | None


def _row(r: tuple[Any, ...]) -> GoalRow:
    return GoalRow(
        id=int(r[0]),
        name=str(r[1]),
        category=str(r[2]) if r[2] is not None else None,
        target_amount_paise=int(r[3]),
        current_amount_paise=int(r[4]),
        monthly_contribution_paise=int(r[5]) if r[5] is not None else None,
        target_date=str(r[6]) if r[6] is not None else None,
    )


async def list_goals(conn: aiosqlite.Connection) -> list[GoalRow]:
    cur = await conn.execute(
        """
        SELECT id, name, category, target_amount_paise, current_amount_paise,
               monthly_contribution_paise, target_date
        FROM goals
        ORDER BY target_date IS NULL, target_date, name
        """,
    )
    rows = await cur.fetchall()
    return [_row(tuple(x)) for x in rows]


async def get_goal(conn: aiosqlite.Connection, goal_id: int) -> GoalRow | None:
    cur = await conn.execute(
        """
        SELECT id, name, category, target_amount_paise, current_amount_paise,
               monthly_contribution_paise, target_date
        FROM goals WHERE id = ?
        """,
        (goal_id,),
    )
    r = await cur.fetchone()
    return _row(tuple(r)) if r else None


async def insert_goal(
    conn: aiosqlite.Connection,
    *,
    name: str,
    category: str | None,
    target_amount_paise: int,
    current_amount_paise: int = 0,
    monthly_contribution_paise: int | None,
    target_date: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO goals (
            name, category, target_amount_paise, current_amount_paise,
            monthly_contribution_paise, target_date, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            name,
            category,
            target_amount_paise,
            current_amount_paise,
            monthly_contribution_paise,
            target_date,
        ),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO goals did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def update_goal(
    conn: aiosqlite.Connection,
    *,
    goal_id: int,
    name: str,
    category: str | None,
    target_amount_paise: int,
    current_amount_paise: int,
    monthly_contribution_paise: int | None,
    target_date: str | None,
) -> None:
    await conn.execute(
        """
        UPDATE goals SET
            name = ?, category = ?, target_amount_paise = ?, current_amount_paise = ?,
            monthly_contribution_paise = ?, target_date = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            name,
            category,
            target_amount_paise,
            current_amount_paise,
            monthly_contribution_paise,
            target_date,
            goal_id,
        ),
    )
    await conn.commit()


async def delete_goal(conn: aiosqlite.Connection, goal_id: int) -> bool:
    cur = await conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    await conn.commit()
    return cur.rowcount > 0
