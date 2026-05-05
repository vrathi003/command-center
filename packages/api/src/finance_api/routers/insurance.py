"""Insurance policies and premium payments API."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn
from finance_api.schemas.insurance import (
    InsurancePolicyCreateBody,
    InsurancePolicyOut,
    InsurancePolicyUpdateBody,
    InsurancePremiumBody,
    InsurancePremiumOut,
    InsuranceSummaryOut,
)
from finance_common.repositories import insurance as ins_repo

router = APIRouter(prefix="/insurance", tags=["insurance"])

_FREQ_TO_ANNUAL = {"annual": 1, "semi_annual": 2, "quarterly": 4, "monthly": 12}
_80D_SECTIONS = {"80D", "80D_parents"}
_80C_SECTIONS = {"80C"}


def _annual_premium(paise: int, freq: str) -> int:
    return paise * _FREQ_TO_ANNUAL.get(freq, 1)


def _policy_out(row: ins_repo.InsurancePolicyRow) -> InsurancePolicyOut:
    return InsurancePolicyOut(
        id=row.id,
        name=row.name,
        type=row.type,
        provider=row.provider,
        policy_number=row.policy_number,
        sum_insured_paise=row.sum_insured_paise,
        premium_paise=row.premium_paise,
        premium_frequency=row.premium_frequency,
        start_date=row.start_date,
        end_date=row.end_date,
        renewal_date=row.renewal_date,
        policyholder=row.policyholder,
        covered_members=row.covered_members,
        asset_id=row.asset_id,
        tax_deduction_section=row.tax_deduction_section,
        status=row.status,
        notes=row.notes,
        annual_premium_paise=_annual_premium(row.premium_paise, row.premium_frequency),
    )


def _premium_out(row: ins_repo.InsurancePremiumRow) -> InsurancePremiumOut:
    return InsurancePremiumOut(
        id=row.id,
        policy_id=row.policy_id,
        payment_date=row.payment_date,
        amount_paise=row.amount_paise,
        period_start=row.period_start,
        period_end=row.period_end,
        payment_mode=row.payment_mode,
        reference_number=row.reference_number,
        notes=row.notes,
    )


# ── Policy endpoints ───────────────────────────────────────────────────────────


@router.get("/", response_model=list[InsurancePolicyOut])
async def list_policies(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[InsurancePolicyOut]:
    rows = await ins_repo.list_policies(conn)
    return [_policy_out(r) for r in rows]


@router.get("/summary", response_model=InsuranceSummaryOut)
async def insurance_summary(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> InsuranceSummaryOut:
    rows = await ins_repo.list_policies(conn)
    active = [r for r in rows if r.status == "active"]
    total_annual = sum(_annual_premium(r.premium_paise, r.premium_frequency) for r in active)
    renewing = await ins_repo.policies_renewing_soon(conn, days=60)
    d80_self = sum(
        _annual_premium(r.premium_paise, r.premium_frequency)
        for r in active if r.tax_deduction_section == "80D"
    )
    d80_parents = sum(
        _annual_premium(r.premium_paise, r.premium_frequency)
        for r in active if r.tax_deduction_section == "80D_parents"
    )
    c80 = sum(
        _annual_premium(r.premium_paise, r.premium_frequency)
        for r in active if r.tax_deduction_section == "80C"
    )
    return InsuranceSummaryOut(
        active_policy_count=len(active),
        total_annual_premium_paise=total_annual,
        renewing_within_60_days=len(renewing),
        total_80d_self_paise=d80_self,
        total_80d_parents_paise=d80_parents,
        total_80c_paise=c80,
    )


@router.post("/", response_model=InsurancePolicyOut, status_code=201)
async def create_policy(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: InsurancePolicyCreateBody,
) -> InsurancePolicyOut:
    pid = await ins_repo.insert_policy(
        conn,
        name=body.name,
        type_=body.type,
        provider=body.provider,
        policy_number=body.policy_number,
        sum_insured_paise=body.sum_insured_paise,
        premium_paise=body.premium_paise,
        premium_frequency=body.premium_frequency,
        start_date=body.start_date,
        end_date=body.end_date,
        renewal_date=body.renewal_date,
        policyholder=body.policyholder,
        covered_members=body.covered_members,
        asset_id=body.asset_id,
        tax_deduction_section=body.tax_deduction_section,
        status=body.status,
        notes=body.notes,
    )
    row = await ins_repo.get_policy(conn, pid)
    if row is None:
        raise HTTPException(status_code=500, detail="Policy not found after insert")
    return _policy_out(row)


@router.get("/{policy_id}", response_model=InsurancePolicyOut)
async def get_policy(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    policy_id: int,
) -> InsurancePolicyOut:
    row = await ins_repo.get_policy(conn, policy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return _policy_out(row)


@router.put("/{policy_id}", response_model=InsurancePolicyOut)
async def update_policy(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    policy_id: int,
    body: InsurancePolicyUpdateBody,
) -> InsurancePolicyOut:
    existing = await ins_repo.get_policy(conn, policy_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    await ins_repo.update_policy(
        conn, policy_id,
        name=body.name if body.name is not None else existing.name,
        type_=body.type if body.type is not None else existing.type,
        provider=body.provider if body.provider is not None else existing.provider,
        policy_number=body.policy_number if body.policy_number is not None else existing.policy_number,
        sum_insured_paise=body.sum_insured_paise if body.sum_insured_paise is not None else existing.sum_insured_paise,
        premium_paise=body.premium_paise if body.premium_paise is not None else existing.premium_paise,
        premium_frequency=body.premium_frequency if body.premium_frequency is not None else existing.premium_frequency,
        start_date=body.start_date if body.start_date is not None else existing.start_date,
        end_date=body.end_date if body.end_date is not None else existing.end_date,
        renewal_date=body.renewal_date if body.renewal_date is not None else existing.renewal_date,
        policyholder=body.policyholder if body.policyholder is not None else existing.policyholder,
        covered_members=body.covered_members if body.covered_members is not None else existing.covered_members,
        asset_id=body.asset_id if body.asset_id is not None else existing.asset_id,
        tax_deduction_section=body.tax_deduction_section if body.tax_deduction_section is not None else existing.tax_deduction_section,
        status=body.status if body.status is not None else existing.status,
        notes=body.notes if body.notes is not None else existing.notes,
    )
    row = await ins_repo.get_policy(conn, policy_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Policy not found after update")
    return _policy_out(row)


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    policy_id: int,
) -> None:
    ok = await ins_repo.delete_policy(conn, policy_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Policy not found")


# ── Premium payment endpoints ──────────────────────────────────────────────────


@router.get("/{policy_id}/premiums", response_model=list[InsurancePremiumOut])
async def list_premiums(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    policy_id: int,
) -> list[InsurancePremiumOut]:
    if await ins_repo.get_policy(conn, policy_id) is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    rows = await ins_repo.list_premiums(conn, policy_id)
    return [_premium_out(r) for r in rows]


@router.post("/{policy_id}/premiums", response_model=InsurancePremiumOut, status_code=201)
async def add_premium(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    policy_id: int,
    body: InsurancePremiumBody,
) -> InsurancePremiumOut:
    if await ins_repo.get_policy(conn, policy_id) is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    prid = await ins_repo.insert_premium(
        conn, policy_id,
        payment_date=body.payment_date,
        amount_paise=body.amount_paise,
        period_start=body.period_start,
        period_end=body.period_end,
        payment_mode=body.payment_mode,
        reference_number=body.reference_number,
        notes=body.notes,
    )
    rows = await ins_repo.list_premiums(conn, policy_id)
    for r in rows:
        if r.id == prid:
            return _premium_out(r)
    raise HTTPException(status_code=500, detail="Premium not found after insert")


@router.delete("/{policy_id}/premiums/{premium_id}", status_code=204)
async def delete_premium(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    policy_id: int,
    premium_id: int,
) -> None:
    ok = await ins_repo.delete_premium(conn, premium_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Premium not found")
