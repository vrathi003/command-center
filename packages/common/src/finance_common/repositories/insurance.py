"""Insurance policy and premium payment persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class InsurancePolicyRow:
    id: int
    name: str
    type: str
    provider: str | None
    policy_number: str | None
    sum_insured_paise: int | None
    premium_paise: int
    premium_frequency: str
    start_date: str | None
    end_date: str | None
    renewal_date: str | None
    policyholder: str
    covered_members: str | None
    asset_id: int | None
    tax_deduction_section: str | None
    status: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class InsurancePremiumRow:
    id: int
    policy_id: int
    payment_date: str
    amount_paise: int
    period_start: str | None
    period_end: str | None
    payment_mode: str | None
    reference_number: str | None
    notes: str | None


# ── Helper converters ──────────────────────────────────────────────────────────


def _policy_from_row(r: tuple[Any, ...]) -> InsurancePolicyRow:
    return InsurancePolicyRow(
        id=int(r[0]),
        name=str(r[1]),
        type=str(r[2]),
        provider=str(r[3]) if r[3] is not None else None,
        policy_number=str(r[4]) if r[4] is not None else None,
        sum_insured_paise=int(r[5]) if r[5] is not None else None,
        premium_paise=int(r[6]),
        premium_frequency=str(r[7]),
        start_date=str(r[8]) if r[8] is not None else None,
        end_date=str(r[9]) if r[9] is not None else None,
        renewal_date=str(r[10]) if r[10] is not None else None,
        policyholder=str(r[11]),
        covered_members=str(r[12]) if r[12] is not None else None,
        asset_id=int(r[13]) if r[13] is not None else None,
        tax_deduction_section=str(r[14]) if r[14] is not None else None,
        status=str(r[15]),
        notes=str(r[16]) if r[16] is not None else None,
    )


def _premium_from_row(r: tuple[Any, ...]) -> InsurancePremiumRow:
    return InsurancePremiumRow(
        id=int(r[0]),
        policy_id=int(r[1]),
        payment_date=str(r[2]),
        amount_paise=int(r[3]),
        period_start=str(r[4]) if r[4] is not None else None,
        period_end=str(r[5]) if r[5] is not None else None,
        payment_mode=str(r[6]) if r[6] is not None else None,
        reference_number=str(r[7]) if r[7] is not None else None,
        notes=str(r[8]) if r[8] is not None else None,
    )


# ── Policy CRUD ────────────────────────────────────────────────────────────────

_POLICY_SELECT = """
    SELECT id, name, type, provider, policy_number, sum_insured_paise,
           premium_paise, premium_frequency, start_date, end_date, renewal_date,
           policyholder, covered_members, asset_id, tax_deduction_section, status, notes
    FROM insurance_policies
"""


async def list_policies(
    conn: aiosqlite.Connection,
    *,
    include_deleted: bool = False,
) -> list[InsurancePolicyRow]:
    where = "" if include_deleted else "WHERE is_deleted=0"
    cur = await conn.execute(
        f"{_POLICY_SELECT} {where} ORDER BY renewal_date, name"
    )
    rows = await cur.fetchall()
    return [_policy_from_row(tuple(r)) for r in rows]


async def get_policy(
    conn: aiosqlite.Connection, policy_id: int
) -> InsurancePolicyRow | None:
    cur = await conn.execute(
        f"{_POLICY_SELECT} WHERE id=? AND is_deleted=0",
        (policy_id,),
    )
    r = await cur.fetchone()
    return _policy_from_row(tuple(r)) if r else None


async def insert_policy(
    conn: aiosqlite.Connection,
    *,
    name: str,
    type_: str,
    provider: str | None,
    policy_number: str | None,
    sum_insured_paise: int | None,
    premium_paise: int,
    premium_frequency: str,
    start_date: str | None,
    end_date: str | None,
    renewal_date: str | None,
    policyholder: str,
    covered_members: str | None,
    asset_id: int | None,
    tax_deduction_section: str | None,
    status: str = "active",
    notes: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO insurance_policies (
            name, type, provider, policy_number, sum_insured_paise,
            premium_paise, premium_frequency, start_date, end_date, renewal_date,
            policyholder, covered_members, asset_id, tax_deduction_section,
            status, notes, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        """,
        (name, type_, provider, policy_number, sum_insured_paise,
         premium_paise, premium_frequency, start_date, end_date, renewal_date,
         policyholder, covered_members, asset_id, tax_deduction_section,
         status, notes),
    )
    await conn.commit()
    if cur.lastrowid is None:
        raise RuntimeError("INSERT INTO insurance_policies did not return lastrowid")
    return int(cur.lastrowid)


async def update_policy(
    conn: aiosqlite.Connection,
    policy_id: int,
    *,
    name: str,
    type_: str,
    provider: str | None,
    policy_number: str | None,
    sum_insured_paise: int | None,
    premium_paise: int,
    premium_frequency: str,
    start_date: str | None,
    end_date: str | None,
    renewal_date: str | None,
    policyholder: str,
    covered_members: str | None,
    asset_id: int | None,
    tax_deduction_section: str | None,
    status: str,
    notes: str | None,
) -> None:
    await conn.execute(
        """
        UPDATE insurance_policies SET
            name=?, type=?, provider=?, policy_number=?, sum_insured_paise=?,
            premium_paise=?, premium_frequency=?, start_date=?, end_date=?,
            renewal_date=?, policyholder=?, covered_members=?, asset_id=?,
            tax_deduction_section=?, status=?, notes=?, updated_at=datetime('now')
        WHERE id=? AND is_deleted=0
        """,
        (name, type_, provider, policy_number, sum_insured_paise,
         premium_paise, premium_frequency, start_date, end_date, renewal_date,
         policyholder, covered_members, asset_id, tax_deduction_section,
         status, notes, policy_id),
    )
    await conn.commit()


async def delete_policy(conn: aiosqlite.Connection, policy_id: int) -> bool:
    cur = await conn.execute(
        "UPDATE insurance_policies SET is_deleted=1, updated_at=datetime('now') WHERE id=? AND is_deleted=0",
        (policy_id,),
    )
    await conn.commit()
    return cur.rowcount > 0


async def annual_premium_total(conn: aiosqlite.Connection) -> int:
    """Total annual premium outflow across all active policies (normalised to yearly)."""
    cur = await conn.execute(
        """
        SELECT premium_paise, premium_frequency FROM insurance_policies
        WHERE is_deleted=0 AND status='active'
        """
    )
    rows = await cur.fetchall()
    total = 0
    freq_multiplier = {"annual": 1, "semi_annual": 2, "quarterly": 4, "monthly": 12}
    for row in rows:
        paise = int(row[0])
        freq = str(row[1])
        mult = freq_multiplier.get(freq, 1)
        total += paise * mult
    return total


async def policies_renewing_soon(
    conn: aiosqlite.Connection, days: int = 60
) -> list[InsurancePolicyRow]:
    """Policies with renewal_date within the next `days` calendar days."""
    cur = await conn.execute(
        f"""
        {_POLICY_SELECT}
        WHERE is_deleted=0 AND status='active'
          AND renewal_date IS NOT NULL
          AND date(renewal_date) <= date('now', '+{days} days')
          AND date(renewal_date) >= date('now')
        ORDER BY renewal_date
        """
    )
    rows = await cur.fetchall()
    return [_policy_from_row(tuple(r)) for r in rows]


# ── Premium payment history ────────────────────────────────────────────────────


async def list_premiums(
    conn: aiosqlite.Connection, policy_id: int
) -> list[InsurancePremiumRow]:
    cur = await conn.execute(
        """
        SELECT id, policy_id, payment_date, amount_paise, period_start, period_end,
               payment_mode, reference_number, notes
        FROM insurance_premiums WHERE policy_id=? ORDER BY payment_date DESC
        """,
        (policy_id,),
    )
    rows = await cur.fetchall()
    return [_premium_from_row(tuple(r)) for r in rows]


async def insert_premium(
    conn: aiosqlite.Connection,
    policy_id: int,
    *,
    payment_date: str,
    amount_paise: int,
    period_start: str | None,
    period_end: str | None,
    payment_mode: str | None,
    reference_number: str | None,
    notes: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO insurance_premiums (
            policy_id, payment_date, amount_paise, period_start, period_end,
            payment_mode, reference_number, notes
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (policy_id, payment_date, amount_paise, period_start, period_end,
         payment_mode, reference_number, notes),
    )
    await conn.commit()
    if cur.lastrowid is None:
        raise RuntimeError("INSERT INTO insurance_premiums did not return lastrowid")
    return int(cur.lastrowid)


async def delete_premium(conn: aiosqlite.Connection, premium_id: int) -> bool:
    cur = await conn.execute("DELETE FROM insurance_premiums WHERE id=?", (premium_id,))
    await conn.commit()
    return cur.rowcount > 0
