"""Statement import snapshot transaction CRUD."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from finance_common.config import AppSettings
from finance_common.db import ensure_database, open_db
from finance_common.repositories import statement_import as si_repo


@pytest.fixture
async def snapshot_with_tx() -> int:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        txs = [
            {
                "id": "tx-1",
                "date": "2026-01-15",
                "bank": "ICICI",
                "card": "Card",
                "description": "ZOMATO",
                "amount": 500.0,
                "currency": "INR",
                "category": "Food Delivery",
                "transaction_type": "debit",
                "tx_kind": "spend",
                "tags": "",
                "statement_period": "2026-01",
                "gmail_message_id": "g1",
            }
        ]
        return await si_repo.insert_snapshot(
            conn,
            gmail_scanned=1,
            statements_parsed=1,
            skipped=[],
            transactions=txs,
            source_gmail_ids=["g1"],
        )


@pytest.mark.asyncio
async def test_create_update_delete_snapshot_transactions(snapshot_with_tx: int) -> None:
    from finance_api.services.statement_import_service import (
        create_snapshot_transaction,
        delete_snapshot_transactions,
        get_latest_transactions,
        update_snapshot_transaction,
    )

    settings = AppSettings()
    async with open_db(settings.db_path) as conn:
        created = await create_snapshot_transaction(
            conn,
            {
                "date": "2026-01-20",
                "bank": "ICICI",
                "card": "Card",
                "description": "BBPS Payment received",
                "amount": 1000.0,
                "tx_kind": "payment",
                "category": "Transfer",
            },
        )
        assert len(created) == 2
        assert any(t["tx_kind"] == "payment" and t["amount"] == -1000.0 for t in created)

        updated = await update_snapshot_transaction(
            conn,
            "tx-1",
            {
                "date": "2026-01-15",
                "bank": "ICICI",
                "card": "Card",
                "description": "ZOMATO UPDATED",
                "amount": 550.0,
                "tx_kind": "spend",
                "category": "Food Delivery",
            },
        )
        zomato = next(t for t in updated if t["id"] == "tx-1")
        assert zomato["description"] == "ZOMATO UPDATED"
        assert zomato["amount"] == 550.0

        remaining = await delete_snapshot_transactions(conn, ["tx-1"])
        assert len(remaining) == 1
        assert remaining[0]["tx_kind"] == "payment"

        final = await get_latest_transactions(conn)
        assert len(final) == 1


@pytest.mark.asyncio
async def test_delete_all_releases_gmail_dedup(snapshot_with_tx: int) -> None:
    from finance_api.services.statement_import_service import delete_snapshot_transactions

    settings = AppSettings()
    async with open_db(settings.db_path) as conn:
        rule_id = await si_repo.create_rule(
            conn,
            bank="ICICI",
            card="Card",
            from_emails=["a@b.com"],
        )
        await si_repo.record_fetched_message(conn, gmail_message_id="g1", rule_id=rule_id)
        remaining = await delete_snapshot_transactions(conn, ["tx-1"])
        assert remaining == []
        assert not await si_repo.is_gmail_message_fetched(conn, "g1")


@pytest.mark.asyncio
async def test_snapshot_has_gmail_message_controls_skip() -> None:
    from finance_api.services.statement_import_service import _snapshot_has_gmail_message

    txs = [{"gmail_message_id": "abc", "description": "x"}]
    assert _snapshot_has_gmail_message(txs, "abc")
    assert not _snapshot_has_gmail_message(txs, "xyz")
    assert not _snapshot_has_gmail_message([], "abc")


def test_snapshot_transaction_api_crud(api_client: TestClient) -> None:
    settings = AppSettings()

    async def _seed() -> None:
        await ensure_database(settings.db_path)
        async with open_db(settings.db_path) as conn:
            await si_repo.insert_snapshot(
                conn,
                gmail_scanned=0,
                statements_parsed=0,
                skipped=[],
                transactions=[
                    {
                        "id": "a1",
                        "date": "2026-02-01",
                        "bank": "ICICI",
                        "card": "C",
                        "description": "TEST",
                        "amount": 100.0,
                        "currency": "INR",
                        "category": "Other",
                        "transaction_type": "debit",
                        "tx_kind": "spend",
                        "tags": "",
                        "statement_period": "2026-02",
                        "gmail_message_id": "",
                    }
                ],
                source_gmail_ids=[],
            )

    import asyncio

    asyncio.run(_seed())

    create = api_client.post(
        "/api/statement-import/snapshots/latest/transactions",
        json={
            "date": "2026-02-02",
            "bank": "ICICI",
            "card": "C",
            "description": "NEW",
            "amount": 50,
            "tx_kind": "spend",
            "category": "Other",
        },
    )
    assert create.status_code == 200, create.text
    assert len(create.json()["transactions"]) == 2

    updated = api_client.put(
        "/api/statement-import/snapshots/latest/transactions/a1",
        json={
            "date": "2026-02-01",
            "bank": "ICICI",
            "card": "C",
            "description": "EDITED",
            "amount": 100,
            "tx_kind": "spend",
            "category": "Other",
        },
    )
    assert updated.status_code == 200
    assert any(t["description"] == "EDITED" for t in updated.json()["transactions"])

    deleted = api_client.post(
        "/api/statement-import/snapshots/latest/transactions/bulk-delete",
        json={"ids": ["a1"]},
    )
    assert deleted.status_code == 200
    assert len(deleted.json()["transactions"]) == 1
