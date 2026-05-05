"""Assets API — real estate, vehicles, costs, payments, and loan linkages."""

from __future__ import annotations

from typing import Annotated, Literal, cast

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn
from finance_api.schemas.assets import (
    AssetCostBody,
    AssetCostOut,
    AssetCreateBody,
    AssetDetailOut,
    AssetLoanBody,
    AssetLoanOut,
    AssetOut,
    AssetPaymentBody,
    AssetPaymentOut,
    AssetSummaryOut,
    AssetUpdateBody,
    RealEstateBody,
    RealEstateOut,
    VehicleBody,
    VehicleOut,
)
from finance_common.repositories import assets as asset_repo

router = APIRouter(prefix="/assets", tags=["assets"])


# ── Helpers ────────────────────────────────────────────────────────────────────


def _asset_out(row: asset_repo.AssetRow) -> AssetOut:
    return AssetOut(
        id=row.id,
        name=row.name,
        type=row.type,
        status=row.status,
        purchase_date=row.purchase_date,
        purchase_price_paise=row.purchase_price_paise,
        current_value_paise=row.current_value_paise,
        ownership_percent=row.ownership_percent,
        co_owner=row.co_owner,
        notes=row.notes,
    )


def _re_out(row: asset_repo.AssetRealEstateRow) -> RealEstateOut:
    return RealEstateOut(
        asset_id=row.asset_id,
        address=row.address,
        city=row.city,
        state=row.state,
        pin_code=row.pin_code,
        builder=row.builder,
        project_name=row.project_name,
        unit_details=row.unit_details,
        carpet_area_sqft=row.carpet_area_sqft,
        builtin_area_sqft=row.builtin_area_sqft,
        super_builtin_area_sqft=row.super_builtin_area_sqft,
        purchase_psf_paise=row.purchase_psf_paise,
        current_psf_paise=row.current_psf_paise,
        psf_area_type=row.psf_area_type,
        possession_status=row.possession_status,
        possession_date_estimated=row.possession_date_estimated,
        possession_date_actual=row.possession_date_actual,
        agreement_value_paise=row.agreement_value_paise,
        circle_rate_psf_paise=row.circle_rate_psf_paise,
    )


def _vehicle_out(row: asset_repo.AssetVehicleRow) -> VehicleOut:
    return VehicleOut(
        asset_id=row.asset_id,
        make=row.make,
        model=row.model,
        variant=row.variant,
        year=row.year,
        registration_number=row.registration_number,
        fuel_type=row.fuel_type,
        color=row.color,
        depreciation_rate_percent=row.depreciation_rate_percent,
    )


def _cost_out(row: asset_repo.AssetCostRow) -> AssetCostOut:
    return AssetCostOut(
        id=row.id,
        asset_id=row.asset_id,
        cost_type=row.cost_type,
        description=row.description,
        amount_paise=row.amount_paise,
        paid_date=row.date,
        is_paid=row.is_paid,
    )


def _loan_out(row: asset_repo.AssetLoanRow) -> AssetLoanOut:
    remaining: int | None = None
    if row.sanctioned_amount_paise is not None and row.disbursed_amount_paise is not None:
        remaining = row.sanctioned_amount_paise - row.disbursed_amount_paise
    return AssetLoanOut(
        id=row.id,
        asset_id=row.asset_id,
        debt_id=row.debt_id,
        debt_name=row.debt_name,
        sanctioned_amount_paise=row.sanctioned_amount_paise,
        disbursed_amount_paise=row.disbursed_amount_paise,
        pre_emi_paise=row.pre_emi_paise,
        final_emi_paise=row.final_emi_paise,
        notes=row.notes,
        remaining_to_disburse_paise=remaining,
    )


def _payment_out(row: asset_repo.AssetPaymentRow) -> AssetPaymentOut:
    eff = row.paid_date or row.due_date or row.payment_date
    fs = row.fund_source if row.fund_source in ("cash", "bank_loan") else "cash"
    return AssetPaymentOut(
        id=row.id,
        asset_id=row.asset_id,
        payment_date=eff,
        amount_paise=row.amount_paise,
        amount_cash_paise=row.amount_cash_paise,
        amount_loan_paise=row.amount_loan_paise,
        milestone=row.milestone,
        payment_mode=row.payment_mode,
        reference_number=row.reference_number,
        receipt_number=row.receipt_number,
        receipt_date=row.receipt_date,
        notes=row.notes,
        is_paid=row.is_paid,
        due_date=row.due_date,
        paid_date=row.paid_date,
        fund_source=cast(Literal["cash", "bank_loan"], fs),
    )


def _payment_amounts(body: AssetPaymentBody) -> tuple[int, int, int]:
    """Returns (amount_cash_paise, amount_loan_paise, amount_paise total)."""
    cash = body.amount_cash_paise
    loan = body.amount_loan_paise
    legacy = body.amount_paise
    if cash == 0 and loan == 0 and legacy is not None and legacy > 0:
        if body.fund_source == "bank_loan":
            loan = legacy
        else:
            cash = legacy
    total = cash + loan
    if total <= 0:
        raise HTTPException(
            status_code=422,
            detail="Total amount (self-funded + loan) must be positive.",
        )
    return cash, loan, total


def _payment_repo_fields(
    body: AssetPaymentBody,
) -> tuple[str, bool, str | None, str | None, str]:
    """Returns (payment_date_eff, is_paid, due_date, paid_date, fund_source)."""
    fs = body.fund_source
    if body.is_paid:
        paid = (body.paid_date or body.payment_date or "").strip()
        if not paid:
            raise HTTPException(
                status_code=422,
                detail="paid_date is required when is_paid is true (or send legacy payment_date).",
            )
        due_stored = body.due_date.strip()[:10] if body.due_date and body.due_date.strip() else None
        paid_stored = paid[:10]
        eff = paid_stored
        return eff, True, due_stored, paid_stored, fs
    due = (body.due_date or "").strip()
    if not due:
        raise HTTPException(
            status_code=422,
            detail="due_date is required when the milestone is upcoming (is_paid false).",
        )
    eff = due[:10]
    return eff, False, due[:10], None, fs


def _compute_appreciation(
    purchase_paise: int | None, current_paise: int | None
) -> float | None:
    if purchase_paise and purchase_paise > 0 and current_paise is not None:
        return round((current_paise - purchase_paise) / purchase_paise * 100, 2)
    return None


# ── Asset endpoints ────────────────────────────────────────────────────────────


@router.get("/", response_model=list[AssetOut])
async def list_assets(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[AssetOut]:
    rows = await asset_repo.list_assets(conn)
    return [_asset_out(r) for r in rows]


@router.get("/summary", response_model=AssetSummaryOut)
async def assets_summary(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> AssetSummaryOut:
    rows = await asset_repo.list_assets(conn)
    total_current = sum(r.current_value_paise or 0 for r in rows)
    total_purchase = sum(r.purchase_price_paise or 0 for r in rows)
    return AssetSummaryOut(
        total_assets=len(rows),
        total_current_value_paise=total_current,
        total_purchase_price_paise=total_purchase,
    )


@router.post("/", response_model=AssetOut, status_code=201)
async def create_asset(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: AssetCreateBody,
) -> AssetOut:
    aid = await asset_repo.insert_asset(
        conn,
        name=body.name,
        type_=body.type,
        status=body.status,
        purchase_date=body.purchase_date,
        purchase_price_paise=body.purchase_price_paise,
        current_value_paise=body.current_value_paise,
        ownership_percent=body.ownership_percent,
        co_owner=body.co_owner,
        notes=body.notes,
    )
    row = await asset_repo.get_asset(conn, aid)
    if row is None:
        raise HTTPException(status_code=500, detail="Asset not found after insert")
    return _asset_out(row)


@router.get("/{asset_id}", response_model=AssetDetailOut)
async def get_asset_detail(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
) -> AssetDetailOut:
    asset = await asset_repo.get_asset(conn, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    re = await asset_repo.get_real_estate(conn, asset_id)
    veh = await asset_repo.get_vehicle(conn, asset_id)
    costs = await asset_repo.list_costs(conn, asset_id)
    loans = await asset_repo.list_loans(conn, asset_id)
    payments = await asset_repo.list_payments(conn, asset_id)
    total_cost_breakdown = sum(c.amount_paise for c in costs)
    total_milestones = sum(p.amount_paise for p in payments)
    total_cost = total_cost_breakdown + total_milestones
    total_paid_milestones = sum(p.amount_paise for p in payments if p.is_paid)
    total_upcoming_milestones = sum(p.amount_paise for p in payments if not p.is_paid)
    return AssetDetailOut(
        asset=_asset_out(asset),
        real_estate=_re_out(re) if re else None,
        vehicle=_vehicle_out(veh) if veh else None,
        costs=[_cost_out(c) for c in costs],
        loans=[_loan_out(ln) for ln in loans],
        payments=[_payment_out(p) for p in payments],
        total_cost_paise=total_cost,
        total_paid_paise=total_paid_milestones,
        total_payment_milestones_upcoming_paise=total_upcoming_milestones,
        appreciation_pct=_compute_appreciation(
            asset.purchase_price_paise, asset.current_value_paise
        ),
    )


@router.put("/{asset_id}", response_model=AssetOut)
async def update_asset(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    body: AssetUpdateBody,
) -> AssetOut:
    existing = await asset_repo.get_asset(conn, asset_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    await asset_repo.update_asset(
        conn,
        asset_id,
        name=body.name if body.name is not None else existing.name,
        type_=body.type if body.type is not None else existing.type,
        status=body.status if body.status is not None else existing.status,
        purchase_date=body.purchase_date if body.purchase_date is not None else existing.purchase_date,
        purchase_price_paise=body.purchase_price_paise if body.purchase_price_paise is not None else existing.purchase_price_paise,
        current_value_paise=body.current_value_paise if body.current_value_paise is not None else existing.current_value_paise,
        ownership_percent=body.ownership_percent if body.ownership_percent is not None else existing.ownership_percent,
        co_owner=body.co_owner if body.co_owner is not None else existing.co_owner,
        notes=body.notes if body.notes is not None else existing.notes,
    )
    row = await asset_repo.get_asset(conn, asset_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Asset not found after update")
    return _asset_out(row)


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
) -> None:
    ok = await asset_repo.delete_asset(conn, asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Asset not found")


# ── Real estate detail ─────────────────────────────────────────────────────────


@router.put("/{asset_id}/real-estate", response_model=RealEstateOut)
async def upsert_real_estate(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    body: RealEstateBody,
) -> RealEstateOut:
    if await asset_repo.get_asset(conn, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    await asset_repo.upsert_real_estate(
        conn,
        asset_id,
        address=body.address,
        city=body.city,
        state=body.state,
        pin_code=body.pin_code,
        builder=body.builder,
        project_name=body.project_name,
        unit_details=body.unit_details,
        carpet_area_sqft=body.carpet_area_sqft,
        builtin_area_sqft=body.builtin_area_sqft,
        super_builtin_area_sqft=body.super_builtin_area_sqft,
        purchase_psf_paise=body.purchase_psf_paise,
        current_psf_paise=body.current_psf_paise,
        psf_area_type=body.psf_area_type,
        possession_status=body.possession_status,
        possession_date_estimated=body.possession_date_estimated,
        possession_date_actual=body.possession_date_actual,
        agreement_value_paise=body.agreement_value_paise,
        circle_rate_psf_paise=body.circle_rate_psf_paise,
    )
    row = await asset_repo.get_real_estate(conn, asset_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Real estate detail not found after upsert")
    return _re_out(row)


# ── Vehicle detail ─────────────────────────────────────────────────────────────


@router.put("/{asset_id}/vehicle", response_model=VehicleOut)
async def upsert_vehicle(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    body: VehicleBody,
) -> VehicleOut:
    if await asset_repo.get_asset(conn, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    await asset_repo.upsert_vehicle(
        conn,
        asset_id,
        make=body.make,
        model=body.model,
        variant=body.variant,
        year=body.year,
        registration_number=body.registration_number,
        fuel_type=body.fuel_type,
        color=body.color,
        depreciation_rate_percent=body.depreciation_rate_percent,
    )
    row = await asset_repo.get_vehicle(conn, asset_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Vehicle detail not found after upsert")
    return _vehicle_out(row)


# ── Cost line items ────────────────────────────────────────────────────────────


@router.get("/{asset_id}/costs", response_model=list[AssetCostOut])
async def list_costs(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
) -> list[AssetCostOut]:
    if await asset_repo.get_asset(conn, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    rows = await asset_repo.list_costs(conn, asset_id)
    return [_cost_out(r) for r in rows]


@router.post("/{asset_id}/costs", response_model=AssetCostOut, status_code=201)
async def add_cost(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    body: AssetCostBody,
) -> AssetCostOut:
    if await asset_repo.get_asset(conn, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    cid = await asset_repo.insert_cost(
        conn, asset_id,
        cost_type=body.cost_type,
        description=body.description,
        amount_paise=body.amount_paise,
        date=body.paid_date,
        is_paid=body.is_paid,
    )
    rows = await asset_repo.list_costs(conn, asset_id)
    for r in rows:
        if r.id == cid:
            return _cost_out(r)
    raise HTTPException(status_code=500, detail="Cost not found after insert")


@router.put("/{asset_id}/costs/{cost_id}", response_model=AssetCostOut)
async def update_cost(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    cost_id: int,
    body: AssetCostBody,
) -> AssetCostOut:
    await asset_repo.update_cost(
        conn, cost_id,
        cost_type=body.cost_type,
        description=body.description,
        amount_paise=body.amount_paise,
        date=body.paid_date,
        is_paid=body.is_paid,
    )
    rows = await asset_repo.list_costs(conn, asset_id)
    for r in rows:
        if r.id == cost_id:
            return _cost_out(r)
    raise HTTPException(status_code=404, detail="Cost not found")


@router.delete("/{asset_id}/costs/{cost_id}", status_code=204)
async def delete_cost(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    cost_id: int,
) -> None:
    ok = await asset_repo.delete_cost(conn, cost_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Cost not found")


# ── Loan linkages ──────────────────────────────────────────────────────────────


@router.get("/{asset_id}/loans", response_model=list[AssetLoanOut])
async def list_loans(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
) -> list[AssetLoanOut]:
    if await asset_repo.get_asset(conn, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    rows = await asset_repo.list_loans(conn, asset_id)
    return [_loan_out(r) for r in rows]


@router.post("/{asset_id}/loans", response_model=AssetLoanOut, status_code=201)
async def upsert_loan(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    body: AssetLoanBody,
) -> AssetLoanOut:
    if await asset_repo.get_asset(conn, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    await asset_repo.upsert_loan(
        conn, asset_id, body.debt_id,
        sanctioned_amount_paise=body.sanctioned_amount_paise,
        disbursed_amount_paise=body.disbursed_amount_paise,
        pre_emi_paise=body.pre_emi_paise,
        final_emi_paise=body.final_emi_paise,
        notes=body.notes,
    )
    rows = await asset_repo.list_loans(conn, asset_id)
    for r in rows:
        if r.debt_id == body.debt_id:
            return _loan_out(r)
    raise HTTPException(status_code=500, detail="Loan link not found after upsert")


@router.delete("/{asset_id}/loans/{loan_id}", status_code=204)
async def delete_loan(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    loan_id: int,
) -> None:
    ok = await asset_repo.delete_loan(conn, loan_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Loan link not found")


# ── Payments / receipts ────────────────────────────────────────────────────────


@router.get("/{asset_id}/payments", response_model=list[AssetPaymentOut])
async def list_payments(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
) -> list[AssetPaymentOut]:
    if await asset_repo.get_asset(conn, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    rows = await asset_repo.list_payments(conn, asset_id)
    return [_payment_out(r) for r in rows]


@router.post("/{asset_id}/payments", response_model=AssetPaymentOut, status_code=201)
async def add_payment(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    body: AssetPaymentBody,
) -> AssetPaymentOut:
    if await asset_repo.get_asset(conn, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    eff, is_paid, due_date, paid_date, fund_source = _payment_repo_fields(body)
    cash_p, loan_p, total_p = _payment_amounts(body)
    pid = await asset_repo.insert_payment(
        conn,
        asset_id,
        payment_date=eff,
        amount_paise=total_p,
        amount_cash_paise=cash_p,
        amount_loan_paise=loan_p,
        milestone=body.milestone,
        payment_mode=body.payment_mode,
        reference_number=body.reference_number,
        receipt_number=body.receipt_number,
        receipt_date=body.receipt_date,
        notes=body.notes,
        is_paid=is_paid,
        due_date=due_date,
        paid_date=paid_date,
        fund_source=fund_source,
    )
    rows = await asset_repo.list_payments(conn, asset_id)
    for r in rows:
        if r.id == pid:
            return _payment_out(r)
    raise HTTPException(status_code=500, detail="Payment not found after insert")


@router.put("/{asset_id}/payments/{payment_id}", response_model=AssetPaymentOut)
async def update_payment(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    payment_id: int,
    body: AssetPaymentBody,
) -> AssetPaymentOut:
    eff, is_paid, due_date, paid_date, fund_source = _payment_repo_fields(body)
    cash_p, loan_p, total_p = _payment_amounts(body)
    await asset_repo.update_payment(
        conn,
        payment_id,
        payment_date=eff,
        amount_paise=total_p,
        amount_cash_paise=cash_p,
        amount_loan_paise=loan_p,
        milestone=body.milestone,
        payment_mode=body.payment_mode,
        reference_number=body.reference_number,
        receipt_number=body.receipt_number,
        receipt_date=body.receipt_date,
        notes=body.notes,
        is_paid=is_paid,
        due_date=due_date,
        paid_date=paid_date,
        fund_source=fund_source,
    )
    rows = await asset_repo.list_payments(conn, asset_id)
    for r in rows:
        if r.id == payment_id:
            return _payment_out(r)
    raise HTTPException(status_code=404, detail="Payment not found")


@router.delete("/{asset_id}/payments/{payment_id}", status_code=204)
async def delete_payment(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    asset_id: int,
    payment_id: int,
) -> None:
    ok = await asset_repo.delete_payment(conn, payment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Payment not found")
