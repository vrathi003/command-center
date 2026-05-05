"""Budget rows: versioned by FY and effective_from date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import aiosqlite


@dataclass(frozen=True, slots=True)
class EffectiveBudgetRow:
    category: str
    monthly_amount_paise: int
    effective_from: str


async def effective_budgets_for_fy(
    conn: aiosqlite.Connection, fy_year: str
) -> list[EffectiveBudgetRow]:
    """Latest budget per category for the FY where effective_from is not in the future."""
    cur = await conn.execute(
        """
        SELECT category, monthly_amount_paise, effective_from
        FROM budgets
        WHERE fy_year = ? AND effective_from <= date('now', 'localtime')
        ORDER BY category ASC, effective_from DESC
        """,
        (fy_year,),
    )
    rows = await cur.fetchall()
    seen: set[str] = set()
    out: list[EffectiveBudgetRow] = []
    for r in rows:
        cat = str(r[0])
        if cat in seen:
            continue
        seen.add(cat)
        out.append(
            EffectiveBudgetRow(
                category=cat,
                monthly_amount_paise=int(r[1]),
                effective_from=str(r[2]),
            ),
        )
    return out


async def set_monthly_budget(
    conn: aiosqlite.Connection,
    *,
    category: str,
    fy_year: str,
    monthly_amount_paise: int,
    effective_from: date | None = None,
) -> None:
    """Insert or update the budget for (category, fy_year, effective_from)."""
    ef = (effective_from or date.today()).isoformat()
    await conn.execute(
        """
        INSERT INTO budgets (
            category, monthly_amount_paise, fy_year, effective_from, updated_at
        ) VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(category, fy_year, effective_from) DO UPDATE SET
            monthly_amount_paise = excluded.monthly_amount_paise,
            updated_at = datetime('now')
        """,
        (category, monthly_amount_paise, fy_year, ef),
    )
    await conn.commit()


async def list_history(
    conn: aiosqlite.Connection,
    *,
    fy_year: str,
    limit: int = 200,
) -> list[tuple[str, int, str, str]]:
    """Return (category, monthly_amount_paise, effective_from, updated_at) rows."""
    cur = await conn.execute(
        """
        SELECT category, monthly_amount_paise, effective_from,
               datetime(updated_at) FROM budgets
        WHERE fy_year = ?
        ORDER BY effective_from DESC, category
        LIMIT ?
        """,
        (fy_year, limit),
    )
    rows = await cur.fetchall()
    return [(str(r[0]), int(r[1]), str(r[2]), str(r[3])) for r in rows]


async def delete_category_for_fy(
    conn: aiosqlite.Connection,
    *,
    category: str,
    fy_year: str,
) -> int:
    """Remove all budget rows for this category in the FY. Returns deleted row count."""
    cur = await conn.execute(
        "DELETE FROM budgets WHERE category = ? AND fy_year = ?",
        (category, fy_year),
    )
    await conn.commit()
    return int(cur.rowcount)


async def rename_category_for_fy(
    conn: aiosqlite.Connection,
    *,
    old_category: str,
    new_category: str,
    fy_year: str,
) -> None:
    """Rename a category for budgets (current FY), transactions, merchant map, and goals.

    Raises:
        ValueError: ``invalid_rename`` if names are empty or equal.
        ValueError: ``category_budget_conflict`` if both old and new already have budget
            rows for this FY (manual merge required).
    """
    old = old_category.strip()
    new = new_category.strip()
    if not old or not new or old == new:
        raise ValueError("invalid_rename")

    cur = await conn.execute(
        "SELECT COUNT(*) FROM budgets WHERE fy_year = ? AND category = ?",
        (fy_year, old),
    )
    row = await cur.fetchone()
    old_budget_rows = int(row[0]) if row else 0
    cur = await conn.execute(
        "SELECT COUNT(*) FROM budgets WHERE fy_year = ? AND category = ?",
        (fy_year, new),
    )
    row = await cur.fetchone()
    new_budget_rows = int(row[0]) if row else 0
    if old_budget_rows > 0 and new_budget_rows > 0:
        raise ValueError("category_budget_conflict")

    await conn.execute("BEGIN IMMEDIATE")
    try:
        if old_budget_rows > 0:
            await conn.execute(
                """
                UPDATE budgets
                SET category = ?, updated_at = datetime('now')
                WHERE fy_year = ? AND category = ?
                """,
                (new, fy_year, old),
            )
        await conn.execute(
            """
            UPDATE transactions
            SET category = ?, updated_at = datetime('now')
            WHERE category = ? AND is_deleted = 0
            """,
            (new, old),
        )
        await conn.execute(
            """
            UPDATE merchant_category_map
            SET category = ?, last_used = datetime('now')
            WHERE category = ?
            """,
            (new, old),
        )
        await conn.execute(
            """
            UPDATE goals
            SET category = ?, updated_at = datetime('now')
            WHERE category = ?
            """,
            (new, old),
        )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
