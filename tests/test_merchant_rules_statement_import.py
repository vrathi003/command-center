"""Merchant rules applied to statement-import snapshots."""

from __future__ import annotations

import json

import pytest

from finance_common.config import AppSettings
from finance_common.db import ensure_database, open_db
from finance_common.repositories import merchant_rules as mr_repo
from finance_common.repositories import statement_import as si_repo


@pytest.mark.asyncio
async def test_bulk_apply_rule_updates_statement_import_snapshot() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as db_conn:
        rid = await mr_repo.create_rule(
            db_conn,
            match_type="contains",
            match_value="zzunique_swiggy_test",
            canonical_merchant="Swiggy",
            merchant_type="Food Delivery",
            category="Food",
            source="user",
        )
        txs = [
            {
                "id": "a1",
                "date": "2026-01-10",
                "description": "ZZUNIQUE_SWIGGY_TEST BANGALORE",
                "amount": 450.0,
                "category": "Other",
                "tx_kind": "spend",
            },
            {
                "id": "a2",
                "date": "2026-01-11",
                "description": "PAYMENT RECEIVED",
                "amount": -5000.0,
                "category": "Transfer",
                "tx_kind": "payment",
            },
        ]
        await si_repo.insert_snapshot(
            db_conn,
            gmail_scanned=1,
            statements_parsed=1,
            skipped=[],
            transactions=txs,
            source_gmail_ids=[],
        )

        ledger_n, statement_n = await mr_repo.bulk_apply_rule(db_conn, rid)
        assert ledger_n == 0
        assert statement_n == 1

        snap = await si_repo.get_latest_snapshot(db_conn)
        assert snap is not None
        updated = json.loads(snap.transactions_json)
        assert updated[0]["category"] == "Food"
        assert updated[0]["description"] == "Swiggy"
        assert updated[0]["category_source"] == "rules"
        assert updated[1]["category"] == "Transfer"


@pytest.mark.asyncio
async def test_uncategorized_includes_statement_import() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as db_conn:
        txs = [
            {
                "id": "b1",
                "description": "UNKNOWN MERCHANT XYZ",
                "amount": 100.0,
                "category": "Other",
                "tx_kind": "spend",
            }
        ]
        await si_repo.insert_snapshot(
            db_conn,
            gmail_scanned=1,
            statements_parsed=1,
            skipped=[],
            transactions=txs,
            source_gmail_ids=[],
        )

        groups = await mr_repo.list_uncategorized_grouped(db_conn)
        matching = [g for g in groups if g.merchant == "UNKNOWN MERCHANT XYZ"]
        assert len(matching) == 1
        assert matching[0].sources == ("statement_import",)
