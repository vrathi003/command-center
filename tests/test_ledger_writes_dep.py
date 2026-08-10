"""Tests for require_ledger_writes dependency."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from finance_api.deps_ledger import require_ledger_writes


def test_require_ledger_writes_returns_503_when_disabled() -> None:
    app = FastAPI()

    @app.get("/ledger-write")
    def _ledger_write(_: None = Depends(require_ledger_writes)) -> dict[str, str]:
        return {"status": "ok"}

    app.state.ledger_writes_enabled = False

    with TestClient(app) as client:
        response = client.get("/ledger-write")

    assert response.status_code == 503
    assert response.json()["detail"] == "Ledger writes disabled due to integrity failure"


def test_require_ledger_writes_allows_when_enabled() -> None:
    app = FastAPI()

    @app.get("/ledger-write")
    def _ledger_write(_: None = Depends(require_ledger_writes)) -> dict[str, str]:
        return {"status": "ok"}

    app.state.ledger_writes_enabled = True

    with TestClient(app) as client:
        response = client.get("/ledger-write")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
