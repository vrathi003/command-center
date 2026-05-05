"""Pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from finance_api.main import create_app


@pytest.fixture(autouse=True)
def _env_db(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    db = tmp_path_factory.mktemp("data") / "test.db"
    monkeypatch.setenv("DB_PATH", str(db))


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as client:
        yield client
