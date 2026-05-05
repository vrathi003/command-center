"""FY summary PDF endpoint."""

from __future__ import annotations

from starlette.testclient import TestClient

from finance_api.main import create_app


def test_fy_summary_pdf() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/reports/fy-summary.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert "attachment" in r.headers.get("content-disposition", "")
