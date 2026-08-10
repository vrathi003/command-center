"""Dry-run and apply services for migrating legacy transactions to the ledger."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import aiosqlite

from finance_common.intake.models import Candidate
from finance_common.ledger import service as ledger_service
from finance_common.migration.models import MigrationReport
from finance_common.migration.plan_row import PlannedMigrate, plan_legacy_row
from finance_common.project_config import mark_legacy_cutover
from finance_common.repositories.domain_events import append_event
from finance_common.repositories.intake_candidates import save_candidate

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _legacy_rows(conn: aiosqlite.Connection) -> list[dict[str, object]]:
    cursor = await conn.execute("SELECT *, is_deleted FROM transactions ORDER BY id")
    columns = [str(column[0]) for column in cursor.description or ()]
    return [dict(zip(columns, row, strict=True)) for row in await cursor.fetchall()]


async def _processed_external_keys(conn: aiosqlite.Connection) -> set[str]:
    ledger_cursor = await conn.execute(
        "SELECT external_key FROM ledger_transactions WHERE external_key IS NOT NULL"
    )
    candidate_cursor = await conn.execute(
        "SELECT external_key FROM intake_candidates WHERE external_key IS NOT NULL"
    )
    return {
        str(row[0]) for row in [*await ledger_cursor.fetchall(), *await candidate_cursor.fetchall()]
    }


def _candidate_from_plan(plan: PlannedMigrate) -> Candidate:
    payload = plan.raw_payload or {}
    tx_date = date.fromisoformat(str(payload["date"]))
    amount_paise = int(str(payload["amount_paise"]))
    transaction_type = str(payload.get("transaction_type") or "debit")
    account_id_value = payload.get("account_id")
    account_id = None if account_id_value is None else int(str(account_id_value))
    return Candidate(
        # `intake_candidates.source` is intentionally limited to intake channels.
        source="import",
        tx_date=tx_date,
        amount_paise=amount_paise,
        direction="in" if transaction_type == "credit" else "out",
        suggested_account_id=account_id,
        payee=None if payload.get("merchant") is None else str(payload["merchant"]),
        narration=None if payload.get("notes") is None else str(payload["notes"]),
        suggested_category=None if payload.get("category") is None else str(payload["category"]),
        external_key=plan.external_key,
        raw_payload=payload,
    )


async def _quarantine_plan(conn: aiosqlite.Connection, plan: PlannedMigrate) -> None:
    candidate = _candidate_from_plan(plan)
    candidate_id = await save_candidate(
        conn,
        candidate,
        status="pending",
        quarantine_reason=plan.quarantine_reason,
    )
    await append_event(
        conn,
        event_type="migration.quarantine_created",
        payload={
            "candidate_id": candidate_id,
            "external_key": plan.external_key,
            "legacy_ids": list(plan.legacy_ids),
            "reason": plan.quarantine_reason,
        },
    )


async def _opening_balance_pass(conn: aiosqlite.Connection) -> None:
    """Quarantine account opening balances that require an operator-supplied amount."""
    cursor = await conn.execute(
        """
        SELECT DISTINCT account.id, account.name
        FROM accounts AS account
        JOIN ledger_postings AS posting ON posting.account_id = account.id
        WHERE account.account_class IN ('asset_cash', 'liability_cc')
          AND NOT EXISTS (
              SELECT 1
              FROM ledger_postings AS account_posting
              JOIN ledger_postings AS equity_posting
                ON equity_posting.transaction_id = account_posting.transaction_id
              JOIN accounts AS equity ON equity.id = equity_posting.account_id
              WHERE account_posting.account_id = account.id
                AND equity.name = 'Opening Balance Equity'
          )
        ORDER BY account.id, posting.id
        """
    )
    for account_id_value, account_name_value in await cursor.fetchall():
        account_id = int(account_id_value)
        account_name = str(account_name_value)
        external_key = f"legacy:opening-balance:{account_id}"
        existing = await conn.execute(
            "SELECT 1 FROM intake_candidates WHERE external_key = ?",
            (external_key,),
        )
        if await existing.fetchone() is not None:
            continue
        candidate = Candidate(
            source="import",
            tx_date=date.today(),
            amount_paise=0,
            direction="in",
            suggested_account_id=account_id,
            payee=account_name,
            narration="Opening balance required; amount must be supplied during approval.",
            external_key=external_key,
            raw_payload={
                "account_id": account_id,
                "amount_required": True,
                "approval_requires_user_supplied_amount": True,
            },
        )
        candidate_id = await save_candidate(
            conn,
            candidate,
            status="pending",
            quarantine_reason="needs_opening_balance",
        )
        await append_event(
            conn,
            event_type="migration.quarantine_created",
            payload={
                "candidate_id": candidate_id,
                "external_key": external_key,
                "reason": "needs_opening_balance",
            },
        )


async def _archive_legacy_transactions(conn: aiosqlite.Connection) -> None:
    table_cursor = await conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'legacy_transactions'"
    )
    if await table_cursor.fetchone() is None:
        await conn.execute("CREATE TABLE legacy_transactions AS SELECT * FROM transactions")
        await conn.commit()
        return

    row_count_cursor = await conn.execute("SELECT COUNT(*) FROM legacy_transactions")
    row_count = await row_count_cursor.fetchone()
    if row_count is not None and int(row_count[0]) == 0:
        await conn.execute("INSERT INTO legacy_transactions SELECT * FROM transactions")
        await conn.commit()


async def _run(conn: aiosqlite.Connection, *, write: bool) -> MigrationReport:
    rows = await _legacy_rows(conn)
    already_processed = await _processed_external_keys(conn)
    processed_ids: set[int] = set()
    report = MigrationReport(
        migrated=0,
        quarantined=0,
        skipped_deleted=0,
        noop=0,
        backup_path=None,
        cutover_at=None,
    )

    for row in rows:
        row_id = int(str(row["id"]))
        if row_id in processed_ids:
            continue
        pair_id = row.get("transfer_pair_id")
        sibling = (
            next(
                (
                    candidate
                    for candidate in rows
                    if candidate.get("transfer_pair_id") == pair_id
                    and int(str(candidate["id"])) != row_id
                ),
                None,
            )
            if pair_id is not None
            else None
        )
        plan = await plan_legacy_row(
            conn,
            row,
            paired_sibling=sibling,
            already_posted=already_processed,
        )
        processed_ids.update(plan.legacy_ids)
        if (
            str(row.get("transaction_type") or "debit") == "transfer"
            and sibling is not None
            and pair_id is not None
        ):
            processed_ids.add(int(str(sibling["id"])))
        if plan.kind == "post":
            report.migrated += 1
            if write:
                assert plan.post_input is not None
                await ledger_service.post(conn, plan.post_input)
                assert plan.external_key is not None
                already_processed.add(plan.external_key)
        elif plan.kind == "quarantine":
            report.quarantined += 1
            if write:
                await _quarantine_plan(conn, plan)
                if plan.external_key is not None:
                    already_processed.add(plan.external_key)
        elif plan.kind == "skip_deleted":
            report.skipped_deleted += 1
        else:
            report.noop += 1
    return report


def _backup_path(db_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return db_path.with_name(f"{db_path.stem}.pre-ledger-migrate-{timestamp}{db_path.suffix}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def dry_run(conn: aiosqlite.Connection) -> MigrationReport:
    """Return migration counts without changing the database."""
    return await _run(conn, write=False)


async def apply(conn: aiosqlite.Connection, *, db_path: Path) -> MigrationReport:
    """Back up, migrate, archive legacy history, and mark ledger cutover."""
    backup_path = _backup_path(db_path)
    await conn.commit()
    await conn.execute("VACUUM INTO ?", (str(backup_path),))
    backup_sha256 = _sha256(backup_path)
    logger.info(
        "Created pre-ledger migration backup %s sha256=%s",
        backup_path,
        backup_sha256,
    )

    report = await _run(conn, write=True)
    await _opening_balance_pass(conn)
    await _archive_legacy_transactions(conn)
    cutover_at = _now_iso()
    await mark_legacy_cutover(conn, cutover_at)
    return MigrationReport(
        migrated=report.migrated,
        quarantined=report.quarantined,
        skipped_deleted=report.skipped_deleted,
        noop=report.noop,
        backup_path=str(backup_path),
        cutover_at=cutover_at,
        backup_sha256=backup_sha256,
    )
