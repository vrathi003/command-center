"""Asset persistence — real estate, vehicles, costs, payments, and loan linkages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite

# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AssetRow:
    id: int
    name: str
    type: str
    status: str
    purchase_date: str | None
    purchase_price_paise: int | None
    current_value_paise: int | None
    ownership_percent: float
    co_owner: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class AssetRealEstateRow:
    id: int
    asset_id: int
    address: str | None
    city: str | None
    state: str | None
    pin_code: str | None
    builder: str | None
    project_name: str | None
    unit_details: str | None
    carpet_area_sqft: float | None
    builtin_area_sqft: float | None
    super_builtin_area_sqft: float | None
    purchase_psf_paise: int | None
    current_psf_paise: int | None
    psf_area_type: str
    possession_status: str
    possession_date_estimated: str | None
    possession_date_actual: str | None
    agreement_value_paise: int | None
    circle_rate_psf_paise: int | None


@dataclass(frozen=True, slots=True)
class AssetVehicleRow:
    id: int
    asset_id: int
    make: str | None
    model: str | None
    variant: str | None
    year: int | None
    registration_number: str | None
    fuel_type: str | None
    color: str | None
    depreciation_rate_percent: float


@dataclass(frozen=True, slots=True)
class AssetCostRow:
    id: int
    asset_id: int
    cost_type: str
    description: str | None
    amount_paise: int
    date: str | None
    is_paid: bool


@dataclass(frozen=True, slots=True)
class AssetLoanRow:
    id: int
    asset_id: int
    debt_id: int
    debt_name: str
    sanctioned_amount_paise: int | None
    disbursed_amount_paise: int | None
    pre_emi_paise: int | None
    final_emi_paise: int | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class AssetPaymentRow:
    id: int
    asset_id: int
    payment_date: str
    amount_paise: int
    amount_cash_paise: int
    amount_loan_paise: int
    milestone: str | None
    payment_mode: str | None
    reference_number: str | None
    receipt_number: str | None
    receipt_date: str | None
    notes: str | None
    is_paid: bool
    due_date: str | None
    paid_date: str | None
    fund_source: str


# ── Helper converters ──────────────────────────────────────────────────────────


def _asset_from_row(r: tuple[Any, ...]) -> AssetRow:
    return AssetRow(
        id=int(r[0]),
        name=str(r[1]),
        type=str(r[2]),
        status=str(r[3]),
        purchase_date=str(r[4]) if r[4] is not None else None,
        purchase_price_paise=int(r[5]) if r[5] is not None else None,
        current_value_paise=int(r[6]) if r[6] is not None else None,
        ownership_percent=float(r[7]),
        co_owner=str(r[8]) if r[8] is not None else None,
        notes=str(r[9]) if r[9] is not None else None,
    )


def _re_from_row(r: tuple[Any, ...]) -> AssetRealEstateRow:
    return AssetRealEstateRow(
        id=int(r[0]),
        asset_id=int(r[1]),
        address=str(r[2]) if r[2] is not None else None,
        city=str(r[3]) if r[3] is not None else None,
        state=str(r[4]) if r[4] is not None else None,
        pin_code=str(r[5]) if r[5] is not None else None,
        builder=str(r[6]) if r[6] is not None else None,
        project_name=str(r[7]) if r[7] is not None else None,
        unit_details=str(r[8]) if r[8] is not None else None,
        carpet_area_sqft=float(r[9]) if r[9] is not None else None,
        builtin_area_sqft=float(r[10]) if r[10] is not None else None,
        super_builtin_area_sqft=float(r[11]) if r[11] is not None else None,
        purchase_psf_paise=int(r[12]) if r[12] is not None else None,
        current_psf_paise=int(r[13]) if r[13] is not None else None,
        psf_area_type=str(r[14]),
        possession_status=str(r[15]),
        possession_date_estimated=str(r[16]) if r[16] is not None else None,
        possession_date_actual=str(r[17]) if r[17] is not None else None,
        agreement_value_paise=int(r[18]) if r[18] is not None else None,
        circle_rate_psf_paise=int(r[19]) if r[19] is not None else None,
    )


def _vehicle_from_row(r: tuple[Any, ...]) -> AssetVehicleRow:
    return AssetVehicleRow(
        id=int(r[0]),
        asset_id=int(r[1]),
        make=str(r[2]) if r[2] is not None else None,
        model=str(r[3]) if r[3] is not None else None,
        variant=str(r[4]) if r[4] is not None else None,
        year=int(r[5]) if r[5] is not None else None,
        registration_number=str(r[6]) if r[6] is not None else None,
        fuel_type=str(r[7]) if r[7] is not None else None,
        color=str(r[8]) if r[8] is not None else None,
        depreciation_rate_percent=float(r[9]),
    )


def _cost_from_row(r: tuple[Any, ...]) -> AssetCostRow:
    return AssetCostRow(
        id=int(r[0]),
        asset_id=int(r[1]),
        cost_type=str(r[2]),
        description=str(r[3]) if r[3] is not None else None,
        amount_paise=int(r[4]),
        date=str(r[5]) if r[5] is not None else None,
        is_paid=bool(r[6]) if r[6] is not None else True,
    )


def _loan_from_row(r: tuple[Any, ...]) -> AssetLoanRow:
    return AssetLoanRow(
        id=int(r[0]),
        asset_id=int(r[1]),
        debt_id=int(r[2]),
        debt_name=str(r[3]) if r[3] is not None else "",
        sanctioned_amount_paise=int(r[4]) if r[4] is not None else None,
        disbursed_amount_paise=int(r[5]) if r[5] is not None else None,
        pre_emi_paise=int(r[6]) if r[6] is not None else None,
        final_emi_paise=int(r[7]) if r[7] is not None else None,
        notes=str(r[8]) if r[8] is not None else None,
    )


def _payment_from_row(r: tuple[Any, ...]) -> AssetPaymentRow:
    return AssetPaymentRow(
        id=int(r[0]),
        asset_id=int(r[1]),
        payment_date=str(r[2]),
        amount_paise=int(r[3]),
        amount_cash_paise=int(r[4]),
        amount_loan_paise=int(r[5]),
        milestone=str(r[6]) if r[6] is not None else None,
        payment_mode=str(r[7]) if r[7] is not None else None,
        reference_number=str(r[8]) if r[8] is not None else None,
        receipt_number=str(r[9]) if r[9] is not None else None,
        receipt_date=str(r[10]) if r[10] is not None else None,
        notes=str(r[11]) if r[11] is not None else None,
        is_paid=bool(r[12]),
        due_date=str(r[13]) if r[13] is not None else None,
        paid_date=str(r[14]) if r[14] is not None else None,
        fund_source=str(r[15]) if r[15] else "cash",
    )


# ── Assets CRUD ────────────────────────────────────────────────────────────────


async def list_assets(
    conn: aiosqlite.Connection,
    *,
    include_deleted: bool = False,
) -> list[AssetRow]:
    where = "" if include_deleted else "WHERE is_deleted = 0"
    cur = await conn.execute(
        f"""
        SELECT id, name, type, status, purchase_date, purchase_price_paise,
               current_value_paise, ownership_percent, co_owner, notes
        FROM assets {where}
        ORDER BY type, name
        """
    )
    rows = await cur.fetchall()
    return [_asset_from_row(tuple(r)) for r in rows]


async def get_asset(conn: aiosqlite.Connection, asset_id: int) -> AssetRow | None:
    cur = await conn.execute(
        """
        SELECT id, name, type, status, purchase_date, purchase_price_paise,
               current_value_paise, ownership_percent, co_owner, notes
        FROM assets WHERE id = ? AND is_deleted = 0
        """,
        (asset_id,),
    )
    r = await cur.fetchone()
    return _asset_from_row(tuple(r)) if r else None


async def insert_asset(
    conn: aiosqlite.Connection,
    *,
    name: str,
    type_: str,
    status: str = "active",
    purchase_date: str | None,
    purchase_price_paise: int | None,
    current_value_paise: int | None,
    ownership_percent: float = 100.0,
    co_owner: str | None,
    notes: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO assets (name, type, status, purchase_date, purchase_price_paise,
            current_value_paise, ownership_percent, co_owner, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (name, type_, status, purchase_date, purchase_price_paise,
         current_value_paise, ownership_percent, co_owner, notes),
    )
    await conn.commit()
    if cur.lastrowid is None:
        raise RuntimeError("INSERT INTO assets did not return lastrowid")
    return int(cur.lastrowid)


async def update_asset(
    conn: aiosqlite.Connection,
    asset_id: int,
    *,
    name: str,
    type_: str,
    status: str,
    purchase_date: str | None,
    purchase_price_paise: int | None,
    current_value_paise: int | None,
    ownership_percent: float,
    co_owner: str | None,
    notes: str | None,
) -> None:
    await conn.execute(
        """
        UPDATE assets SET name=?, type=?, status=?, purchase_date=?,
            purchase_price_paise=?, current_value_paise=?, ownership_percent=?,
            co_owner=?, notes=?, updated_at=datetime('now')
        WHERE id=? AND is_deleted=0
        """,
        (name, type_, status, purchase_date, purchase_price_paise,
         current_value_paise, ownership_percent, co_owner, notes, asset_id),
    )
    await conn.commit()


async def delete_asset(conn: aiosqlite.Connection, asset_id: int) -> bool:
    cur = await conn.execute(
        "UPDATE assets SET is_deleted=1, updated_at=datetime('now') WHERE id=? AND is_deleted=0",
        (asset_id,),
    )
    await conn.commit()
    return cur.rowcount > 0


async def total_active_value(conn: aiosqlite.Connection) -> int:
    """Sum of current_value_paise for non-deleted active assets (for Net Worth)."""
    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(current_value_paise), 0)
        FROM assets WHERE is_deleted=0 AND status='active' AND current_value_paise IS NOT NULL
        """
    )
    r = await cur.fetchone()
    return int(r[0]) if r else 0


# ── Real estate detail ─────────────────────────────────────────────────────────


async def get_real_estate(
    conn: aiosqlite.Connection, asset_id: int
) -> AssetRealEstateRow | None:
    cur = await conn.execute(
        """
        SELECT id, asset_id, address, city, state, pin_code, builder, project_name,
               unit_details, carpet_area_sqft, builtin_area_sqft, super_builtin_area_sqft,
               purchase_psf_paise, current_psf_paise, psf_area_type, possession_status,
               possession_date_estimated, possession_date_actual, agreement_value_paise,
               circle_rate_psf_paise
        FROM asset_real_estate WHERE asset_id=?
        """,
        (asset_id,),
    )
    r = await cur.fetchone()
    return _re_from_row(tuple(r)) if r else None


async def upsert_real_estate(
    conn: aiosqlite.Connection,
    asset_id: int,
    *,
    address: str | None,
    city: str | None,
    state: str | None,
    pin_code: str | None,
    builder: str | None,
    project_name: str | None,
    unit_details: str | None,
    carpet_area_sqft: float | None,
    builtin_area_sqft: float | None,
    super_builtin_area_sqft: float | None,
    purchase_psf_paise: int | None,
    current_psf_paise: int | None,
    psf_area_type: str,
    possession_status: str,
    possession_date_estimated: str | None,
    possession_date_actual: str | None,
    agreement_value_paise: int | None,
    circle_rate_psf_paise: int | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO asset_real_estate (
            asset_id, address, city, state, pin_code, builder, project_name, unit_details,
            carpet_area_sqft, builtin_area_sqft, super_builtin_area_sqft,
            purchase_psf_paise, current_psf_paise, psf_area_type, possession_status,
            possession_date_estimated, possession_date_actual, agreement_value_paise,
            circle_rate_psf_paise, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(asset_id) DO UPDATE SET
            address=excluded.address, city=excluded.city, state=excluded.state,
            pin_code=excluded.pin_code, builder=excluded.builder,
            project_name=excluded.project_name, unit_details=excluded.unit_details,
            carpet_area_sqft=excluded.carpet_area_sqft,
            builtin_area_sqft=excluded.builtin_area_sqft,
            super_builtin_area_sqft=excluded.super_builtin_area_sqft,
            purchase_psf_paise=excluded.purchase_psf_paise,
            current_psf_paise=excluded.current_psf_paise,
            psf_area_type=excluded.psf_area_type,
            possession_status=excluded.possession_status,
            possession_date_estimated=excluded.possession_date_estimated,
            possession_date_actual=excluded.possession_date_actual,
            agreement_value_paise=excluded.agreement_value_paise,
            circle_rate_psf_paise=excluded.circle_rate_psf_paise,
            updated_at=datetime('now')
        """,
        (asset_id, address, city, state, pin_code, builder, project_name, unit_details,
         carpet_area_sqft, builtin_area_sqft, super_builtin_area_sqft,
         purchase_psf_paise, current_psf_paise, psf_area_type, possession_status,
         possession_date_estimated, possession_date_actual, agreement_value_paise,
         circle_rate_psf_paise),
    )
    await conn.commit()


# ── Vehicle detail ─────────────────────────────────────────────────────────────


async def get_vehicle(
    conn: aiosqlite.Connection, asset_id: int
) -> AssetVehicleRow | None:
    cur = await conn.execute(
        """
        SELECT id, asset_id, make, model, variant, year, registration_number,
               fuel_type, color, depreciation_rate_percent
        FROM asset_vehicles WHERE asset_id=?
        """,
        (asset_id,),
    )
    r = await cur.fetchone()
    return _vehicle_from_row(tuple(r)) if r else None


async def upsert_vehicle(
    conn: aiosqlite.Connection,
    asset_id: int,
    *,
    make: str | None,
    model: str | None,
    variant: str | None,
    year: int | None,
    registration_number: str | None,
    fuel_type: str | None,
    color: str | None,
    depreciation_rate_percent: float,
) -> None:
    await conn.execute(
        """
        INSERT INTO asset_vehicles (
            asset_id, make, model, variant, year, registration_number,
            fuel_type, color, depreciation_rate_percent, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(asset_id) DO UPDATE SET
            make=excluded.make, model=excluded.model, variant=excluded.variant,
            year=excluded.year, registration_number=excluded.registration_number,
            fuel_type=excluded.fuel_type, color=excluded.color,
            depreciation_rate_percent=excluded.depreciation_rate_percent,
            updated_at=datetime('now')
        """,
        (asset_id, make, model, variant, year, registration_number,
         fuel_type, color, depreciation_rate_percent),
    )
    await conn.commit()


# ── Asset costs ────────────────────────────────────────────────────────────────


async def list_costs(
    conn: aiosqlite.Connection, asset_id: int
) -> list[AssetCostRow]:
    cur = await conn.execute(
        """
        SELECT id, asset_id, cost_type, description, amount_paise, date, is_paid
        FROM asset_costs WHERE asset_id=? ORDER BY date, id
        """,
        (asset_id,),
    )
    rows = await cur.fetchall()
    return [_cost_from_row(tuple(r)) for r in rows]


async def insert_cost(
    conn: aiosqlite.Connection,
    asset_id: int,
    *,
    cost_type: str,
    description: str | None,
    amount_paise: int,
    date: str | None,
    is_paid: bool = True,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO asset_costs (asset_id, cost_type, description, amount_paise, date, is_paid)
        VALUES (?,?,?,?,?,?)
        """,
        (asset_id, cost_type, description, amount_paise, date, int(is_paid)),
    )
    await conn.commit()
    if cur.lastrowid is None:
        raise RuntimeError("INSERT INTO asset_costs did not return lastrowid")
    return int(cur.lastrowid)


async def update_cost(
    conn: aiosqlite.Connection,
    cost_id: int,
    *,
    cost_type: str,
    description: str | None,
    amount_paise: int,
    date: str | None,
    is_paid: bool = True,
) -> None:
    await conn.execute(
        """
        UPDATE asset_costs SET cost_type=?, description=?, amount_paise=?, date=?, is_paid=?
        WHERE id=?
        """,
        (cost_type, description, amount_paise, date, int(is_paid), cost_id),
    )
    await conn.commit()


async def delete_cost(conn: aiosqlite.Connection, cost_id: int) -> bool:
    cur = await conn.execute("DELETE FROM asset_costs WHERE id=?", (cost_id,))
    await conn.commit()
    return cur.rowcount > 0


# ── Asset loan linkages ────────────────────────────────────────────────────────


async def list_loans(
    conn: aiosqlite.Connection, asset_id: int
) -> list[AssetLoanRow]:
    cur = await conn.execute(
        """
        SELECT al.id, al.asset_id, al.debt_id, COALESCE(d.name, '') AS debt_name,
               al.sanctioned_amount_paise, al.disbursed_amount_paise,
               al.pre_emi_paise, al.final_emi_paise, al.notes
        FROM asset_loans al
        LEFT JOIN debts d ON d.id = al.debt_id
        WHERE al.asset_id=? ORDER BY al.id
        """,
        (asset_id,),
    )
    rows = await cur.fetchall()
    return [_loan_from_row(tuple(r)) for r in rows]


async def upsert_loan(
    conn: aiosqlite.Connection,
    asset_id: int,
    debt_id: int,
    *,
    sanctioned_amount_paise: int | None,
    disbursed_amount_paise: int | None,
    pre_emi_paise: int | None,
    final_emi_paise: int | None,
    notes: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO asset_loans (
            asset_id, debt_id, sanctioned_amount_paise, disbursed_amount_paise,
            pre_emi_paise, final_emi_paise, notes, updated_at
        ) VALUES (?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(asset_id, debt_id) DO UPDATE SET
            sanctioned_amount_paise=excluded.sanctioned_amount_paise,
            disbursed_amount_paise=excluded.disbursed_amount_paise,
            pre_emi_paise=excluded.pre_emi_paise,
            final_emi_paise=excluded.final_emi_paise,
            notes=excluded.notes,
            updated_at=datetime('now')
        """,
        (asset_id, debt_id, sanctioned_amount_paise, disbursed_amount_paise,
         pre_emi_paise, final_emi_paise, notes),
    )
    await conn.commit()
    if cur.lastrowid is None:
        raise RuntimeError("upsert asset_loans did not return lastrowid")
    return int(cur.lastrowid)


async def delete_loan(conn: aiosqlite.Connection, loan_id: int) -> bool:
    cur = await conn.execute("DELETE FROM asset_loans WHERE id=?", (loan_id,))
    await conn.commit()
    return cur.rowcount > 0


# ── Asset payments ─────────────────────────────────────────────────────────────


async def list_payments(
    conn: aiosqlite.Connection, asset_id: int
) -> list[AssetPaymentRow]:
    cur = await conn.execute(
        """
        SELECT id, asset_id, payment_date, amount_paise, amount_cash_paise, amount_loan_paise,
               milestone, payment_mode, reference_number, receipt_number, receipt_date, notes,
               is_paid, due_date, paid_date, fund_source
        FROM asset_payments
        WHERE asset_id=?
        ORDER BY COALESCE(paid_date, due_date, payment_date), id
        """,
        (asset_id,),
    )
    rows = await cur.fetchall()
    return [_payment_from_row(tuple(r)) for r in rows]


async def insert_payment(
    conn: aiosqlite.Connection,
    asset_id: int,
    *,
    payment_date: str,
    amount_paise: int,
    amount_cash_paise: int,
    amount_loan_paise: int,
    milestone: str | None,
    payment_mode: str | None,
    reference_number: str | None,
    receipt_number: str | None,
    receipt_date: str | None,
    notes: str | None,
    is_paid: bool,
    due_date: str | None,
    paid_date: str | None,
    fund_source: str,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO asset_payments (
            asset_id, payment_date, amount_paise, amount_cash_paise, amount_loan_paise,
            milestone, payment_mode, reference_number, receipt_number, receipt_date, notes,
            is_paid, due_date, paid_date, fund_source
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            asset_id,
            payment_date,
            amount_paise,
            amount_cash_paise,
            amount_loan_paise,
            milestone,
            payment_mode,
            reference_number,
            receipt_number,
            receipt_date,
            notes,
            1 if is_paid else 0,
            due_date,
            paid_date,
            fund_source,
        ),
    )
    await conn.commit()
    if cur.lastrowid is None:
        raise RuntimeError("INSERT INTO asset_payments did not return lastrowid")
    return int(cur.lastrowid)


async def update_payment(
    conn: aiosqlite.Connection,
    payment_id: int,
    *,
    payment_date: str,
    amount_paise: int,
    amount_cash_paise: int,
    amount_loan_paise: int,
    milestone: str | None,
    payment_mode: str | None,
    reference_number: str | None,
    receipt_number: str | None,
    receipt_date: str | None,
    notes: str | None,
    is_paid: bool,
    due_date: str | None,
    paid_date: str | None,
    fund_source: str,
) -> None:
    await conn.execute(
        """
        UPDATE asset_payments SET payment_date=?, amount_paise=?, amount_cash_paise=?, amount_loan_paise=?,
            milestone=?, payment_mode=?, reference_number=?, receipt_number=?,
            receipt_date=?, notes=?,
            is_paid=?, due_date=?, paid_date=?, fund_source=?
        WHERE id=?
        """,
        (
            payment_date,
            amount_paise,
            amount_cash_paise,
            amount_loan_paise,
            milestone,
            payment_mode,
            reference_number,
            receipt_number,
            receipt_date,
            notes,
            1 if is_paid else 0,
            due_date,
            paid_date,
            fund_source,
            payment_id,
        ),
    )
    await conn.commit()


async def delete_payment(conn: aiosqlite.Connection, payment_id: int) -> bool:
    cur = await conn.execute("DELETE FROM asset_payments WHERE id=?", (payment_id,))
    await conn.commit()
    return cur.rowcount > 0
