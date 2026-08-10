from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.ledger import service as ledger_service
from finance_common.ledger.errors import LedgerError, UnbalancedTransactionError
from finance_common.ledger.models import NewPosting, PostTransactionInput


async def _account_ids(conn: aiosqlite.Connection) -> dict[str, int]:
    await conn.execute(
        "INSERT INTO accounts (name, type, account_class) VALUES ('A', 'savings', 'asset_cash')"
    )
    await conn.execute(
        "INSERT INTO accounts (name, type, account_class) VALUES ('E', 'expense', 'expense')"
    )
    await conn.commit()
    cur = await conn.execute("SELECT id, name FROM accounts WHERE name IN ('A', 'E')")
    return {name: account_id for account_id, name in await cur.fetchall()}


@pytest.mark.asyncio
async def test_reject_unbalanced(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        with pytest.raises(UnbalancedTransactionError):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(ids["E"], 10_000, "Food Delivery"),
                        NewPosting(ids["A"], -9_000),
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_post_balanced_expense(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 1),
                postings=(
                    NewPosting(ids["E"], 50_000, "Food Delivery"),
                    NewPosting(ids["A"], -50_000),
                ),
                source="manual",
                payee="Swiggy",
            ),
        )
        posted = await ledger_service.get_transaction(conn, tx_id)
        assert posted.status == "posted"
        assert sum(posting.amount_paise for posting in posted.postings) == 0


@pytest.mark.asyncio
async def test_post_rejects_zero_amount_in_otherwise_balanced_postings(
    tmp_path: Path,
) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        with pytest.raises(LedgerError):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(ids["E"], 10_000, "Food Delivery"),
                        NewPosting(ids["A"], 0),
                        NewPosting(ids["A"], -10_000),
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_post_rejects_missing_account_id(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        with pytest.raises(LedgerError, match="Unknown account ids"):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(None, 500),  # type: ignore[arg-type]
                        NewPosting(ids["A"], -500),
                    ),
                ),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [500.0, True])
async def test_post_rejects_non_integer_amount_paise(
    tmp_path: Path, amount: float | bool
) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        with pytest.raises(LedgerError, match="integer paise"):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(ids["E"], amount),  # type: ignore[arg-type]
                        NewPosting(ids["A"], -amount),  # type: ignore[arg-type,operator]
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_post_returns_existing_id_for_malformed_idempotent_retry(
    tmp_path: Path,
) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        inp = PostTransactionInput(
            tx_date=date(2026, 8, 1),
            postings=(NewPosting(ids["E"], 500), NewPosting(ids["A"], -500)),
            external_key="import:row:1",
        )
        first_id = await ledger_service.post(conn, inp)
        second_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 2),
                postings=(NewPosting(ids["E"], 500), NewPosting(ids["A"], -400)),
                external_key="import:row:1",
            ),
        )
        assert second_id == first_id


@pytest.mark.asyncio
async def test_void_marks_header_and_rejects_double_void(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 1),
                postings=(NewPosting(ids["E"], 500), NewPosting(ids["A"], -500)),
            ),
        )
        await ledger_service.void(conn, tx_id)
        assert (await ledger_service.get_transaction(conn, tx_id)).status == "void"
        with pytest.raises(LedgerError):
            await ledger_service.void(conn, tx_id)
