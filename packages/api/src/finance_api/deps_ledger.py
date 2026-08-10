"""Ledger-specific FastAPI dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request


def require_ledger_writes(request: Request) -> None:
    if getattr(request.app.state, "ledger_writes_enabled", True) is False:
        raise HTTPException(
            status_code=503,
            detail="Ledger writes disabled due to integrity failure",
        )
