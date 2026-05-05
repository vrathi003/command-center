"""User-facing app settings (FY, tax hints)."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn
from finance_api.schemas.app_settings import SettingsOut, SettingsPatch
from finance_common.fy import fy_start
from finance_common.repositories import settings_repo
from finance_common.types import FYYear

router = APIRouter(prefix="/settings", tags=["settings"])

_KEY_TAX_REGIME = "tax_regime"
_KEY_80C = "tax_80c_annual_paise"
_KEY_80D = "tax_80d_annual_paise"


async def _load_out(conn: aiosqlite.Connection) -> SettingsOut:
    fy = await settings_repo.get_current_fy(conn)
    regime = await settings_repo.get_value(conn, _KEY_TAX_REGIME)
    raw_80c = await settings_repo.get_value(conn, _KEY_80C)
    raw_80d = await settings_repo.get_value(conn, _KEY_80D)
    v80: int | None = None
    if raw_80c is not None and raw_80c.strip() != "":
        try:
            v80 = int(raw_80c)
        except ValueError:
            v80 = None
    v80d: int | None = None
    if raw_80d is not None and raw_80d.strip() != "":
        try:
            v80d = int(raw_80d)
        except ValueError:
            v80d = None
    reg_out = regime.strip().lower() if regime else None
    if reg_out not in ("old", "new"):
        reg_out = None
    return SettingsOut(
        current_fy=str(fy),
        tax_regime=reg_out,
        tax_80c_annual_paise=v80,
        tax_80d_annual_paise=v80d,
    )


@router.get("/", response_model=SettingsOut)
async def get_settings(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> SettingsOut:
    return await _load_out(conn)


@router.put("/", response_model=SettingsOut)
async def put_settings(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: SettingsPatch,
) -> SettingsOut:
    patch = body.model_dump(exclude_unset=True)

    if "current_fy" in patch and patch["current_fy"] is not None:
        raw = str(patch["current_fy"]).strip()
        try:
            fy_start(FYYear(raw))
        except Exception as e:
            raise HTTPException(status_code=422, detail="current_fy must look like YYYY-YY") from e
        await settings_repo.set_value(conn, "current_fy", raw)

    if "tax_regime" in patch:
        tr = (patch["tax_regime"] or "").strip().lower()
        if tr not in ("", "old", "new"):
            raise HTTPException(status_code=422, detail="tax_regime must be 'old' or 'new'")
        await settings_repo.set_value(conn, _KEY_TAX_REGIME, tr)

    if "tax_80c_annual_paise" in patch and patch["tax_80c_annual_paise"] is not None:
        await settings_repo.set_value(
            conn,
            _KEY_80C,
            str(int(patch["tax_80c_annual_paise"])),
        )

    if "tax_80d_annual_paise" in patch and patch["tax_80d_annual_paise"] is not None:
        await settings_repo.set_value(
            conn,
            _KEY_80D,
            str(int(patch["tax_80d_annual_paise"])),
        )

    return await _load_out(conn)
