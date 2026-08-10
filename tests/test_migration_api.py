"""HTTP tests for the legacy ledger migration endpoints."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from starlette.testclient import TestClient


def _seed_legacy_transaction() -> None:
    with sqlite3.connect(os.environ["DB_PATH"]) as conn:
        account_id = conn.execute(
            """
            INSERT INTO accounts (name, type, account_class)
            VALUES ('Migration API Bank', 'savings', 'asset_cash')
            RETURNING id
            """
        ).fetchone()
        assert account_id is not None
        conn.execute(
            """
            INSERT INTO transactions (
                date, amount_paise, category, merchant, payment_mode, account,
                account_id, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-08-10",
                10_000,
                "Food",
                "Migration fixture",
                "upi",
                "Migration API Bank",
                account_id[0],
                "import",
            ),
        )


def _table_count(table: str) -> int:
    with sqlite3.connect(os.environ["DB_PATH"]) as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
    assert row is not None
    return int(row[0])


def test_dry_run_reports_legacy_rows_without_writing(api_client: TestClient) -> None:
    _seed_legacy_transaction()

    response = api_client.post("/api/migration/legacy-ledger/dry-run")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "migrated": 1,
        "quarantined": 0,
        "skipped_deleted": 0,
        "noop": 0,
        "backup_path": None,
        "cutover_at": None,
        "backup_sha256": None,
    }
    assert _table_count("ledger_transactions") == 0


def test_apply_migrates_legacy_rows_and_returns_backup(api_client: TestClient) -> None:
    _seed_legacy_transaction()

    response = api_client.post("/api/migration/legacy-ledger/apply")

    assert response.status_code == 200, response.text
    report = response.json()
    assert report["migrated"] == 1
    assert report["quarantined"] == 0
    assert report["skipped_deleted"] == 0
    assert report["noop"] == 0
    assert report["cutover_at"] is not None
    assert report["backup_path"] is not None
    backup = Path(report["backup_path"])
    assert backup.is_file()
    assert report["backup_sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
    assert _table_count("ledger_transactions") == 1
    assert _table_count("legacy_transactions") == 1


def test_apply_requires_ledger_writes(api_client: TestClient) -> None:
    api_client.app.state.ledger_writes_enabled = False

    response = api_client.post("/api/migration/legacy-ledger/apply")

    assert response.status_code == 503
    assert response.json()["detail"] == "Ledger writes disabled due to integrity failure"
