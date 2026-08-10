"""Persistence operations for external transaction intake candidates."""

from __future__ import annotations

import json

import aiosqlite

from finance_common.intake.models import Candidate


async def find_posted_ledger_transaction_id(
    conn: aiosqlite.Connection, external_key: str
) -> int | None:
    """Return the posted ledger transaction for an external key, if present."""
    cursor = await conn.execute(
        """
        SELECT id FROM ledger_transactions
        WHERE external_key = ? AND status = 'posted'
        """,
        (external_key,),
    )
    row = await cursor.fetchone()
    return None if row is None else int(row[0])


async def save_candidate(
    conn: aiosqlite.Connection,
    candidate: Candidate,
    *,
    status: str,
    quarantine_reason: str | None = None,
    ledger_transaction_id: int | None = None,
) -> int:
    """Insert a candidate or update its audit row by external key."""
    values = (
        status,
        candidate.source,
        candidate.external_key,
        candidate.tx_date.isoformat(),
        candidate.amount_paise,
        candidate.direction,
        candidate.payee,
        candidate.narration,
        candidate.suggested_account_id,
        candidate.suggested_counter_account_id,
        candidate.suggested_category,
        candidate.confidence,
        quarantine_reason,
        ledger_transaction_id,
        None
        if candidate.raw_payload is None
        else json.dumps(candidate.raw_payload, ensure_ascii=False, sort_keys=True),
        candidate.email_staging_id,
    )
    if candidate.external_key is not None:
        cursor = await conn.execute(
            "SELECT id FROM intake_candidates WHERE external_key = ?",
            (candidate.external_key,),
        )
        row = await cursor.fetchone()
        if row is not None:
            candidate_id = int(row[0])
            await conn.execute(
                """
                UPDATE intake_candidates
                SET status = ?, source = ?, tx_date = ?, amount_paise = ?, direction = ?,
                    payee = ?, narration = ?, suggested_account_id = ?,
                    suggested_counter_account_id = ?, suggested_category = ?, confidence = ?,
                    quarantine_reason = ?, ledger_transaction_id = ?, raw_payload_json = ?,
                    email_staging_id = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (*values[:2], *values[3:], candidate_id),
            )
            await conn.commit()
            return candidate_id

    cursor = await conn.execute(
        """
        INSERT INTO intake_candidates (
            status, source, external_key, tx_date, amount_paise, direction, payee,
            narration, suggested_account_id, suggested_counter_account_id,
            suggested_category, confidence, quarantine_reason, ledger_transaction_id,
            raw_payload_json, email_staging_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    await conn.commit()
    if cursor.lastrowid is None:
        raise RuntimeError("INSERT INTO intake_candidates did not set lastrowid")
    return int(cursor.lastrowid)
