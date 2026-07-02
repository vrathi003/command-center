"""Liveness and readiness."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from finance_api.deps import get_settings
from finance_api.settings import ApiSettings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(api: Annotated[ApiSettings, Depends(get_settings)]) -> dict:
    return {"status": "ok", "auth_required": bool(api.app_secret_key)}
