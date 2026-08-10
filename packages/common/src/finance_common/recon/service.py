"""Application service for statement-to-ledger reconciliation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import cast

import aiosqlite

from finance_common.ledger import builders
from finance_common.ledger import service as ledger_service
from finance_common.ledger.balances import account_balance_paise
from finance_common.ledger.models import PostTransactionInput
from finance_common.parsing.transaction_import import ParsedImportRow
from finance_common.project_config import load_project_config
from finance_common.recon.models import (
    MatchMethod,
    NewStatement,
    NewStatementLine,
    ReconStatementLine,
    StatementWorkspace,
)
from finance_common.recon.suggest import LedgerMatchCandidate, MatchProposal
from finance_common.recon.suggest import suggest_matches as score_matches
from finance_common.repositories import recon


class ReconciliationError(ValueError):
    """Raised when a reconciliation operation violates a control-book rule."""


@dataclass(frozen=True, slots=True)
class PeriodStatus:
    """Balance and completeness state used to determine whether a period closes."""

    statement_id: int
    ledger_balance_paise: int
    statement_closing_balance_paise: int
    balance_difference_paise: int
    unmatched_line_count: int
    unmatched_ledger_count: int

    @property
    def is_balanced(self) -> bool:
        """Whether the ledger has the statement closing balance as-of period end."""
        return self.balance_difference_paise == 0

    @property
    def can_soft_close(self) -> bool:
        """Whether the two soft-close gates are both satisfied."""
        return self.unmatched_line_count == 0 and self.is_balanced


class ReconciliationService:
    """Coordinate recon persistence with read-only ledger matching and controls."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def import_rows(
        self,
        statement: NewStatement,
        rows: Iterable[ParsedImportRow | NewStatementLine],
    ) -> int:
        """Create a statement workspace from normalized import rows without ledger writes."""
        statement_id = await recon.create_statement(self._conn, statement)
        lines = tuple(self._to_statement_line(row) for row in rows)
        await recon.insert_statement_lines(self._conn, statement_id, lines)
        return statement_id

    async def suggest_matches(self, statement_id: int) -> tuple[MatchProposal, ...]:
        """Return ephemeral best-match proposals for a statement's unmatched lines."""
        workspace = await self._workspace(statement_id)
        config = await load_project_config(self._conn)
        window = config.recon_match_date_window_days
        candidates = await self._ledger_candidates(
            account_id=workspace.statement.account_id,
            start=workspace.statement.period_start,
            end=workspace.statement.period_end,
            window_days=window,
        )
        matched_ids = await self._matched_ledger_transaction_ids()
        return score_matches(
            lines=workspace.lines,
            candidates=candidates,
            account_id=workspace.statement.account_id,
            matched_ledger_transaction_ids=matched_ids,
            date_window_days=window,
        )

    async def confirm_match(
        self,
        statement_id: int,
        line_id: int,
        ledger_transaction_id: int,
        *,
        method: str = "manual",
    ) -> int:
        """Confirm an eligible ledger transaction against one open statement line."""
        workspace = await self._open_workspace(statement_id)
        line = self._line_for_workspace(workspace, line_id)
        if line.status != "unmatched":
            raise ReconciliationError("Statement line is not unmatched")
        if method not in {"manual", "suggested"}:
            raise ReconciliationError("Match method must be manual or suggested")
        if not await self._transaction_posts_to_account(
            ledger_transaction_id, workspace.statement.account_id
        ):
            raise ReconciliationError("Ledger transaction does not post to this statement account")
        if ledger_transaction_id in await self._matched_ledger_transaction_ids():
            raise ReconciliationError("Ledger transaction is already matched")

        match_id = await recon.insert_match(
            self._conn,
            line_id=line_id,
            ledger_transaction_id=ledger_transaction_id,
            method=cast(MatchMethod, method),
        )
        await recon.update_line_status(self._conn, line_id, status="matched")
        return match_id

    async def unmatch(self, statement_id: int, line_id: int) -> None:
        """Remove a confirmed match from an open statement line."""
        workspace = await self._open_workspace(statement_id)
        line = self._line_for_workspace(workspace, line_id)
        if line.status != "matched":
            raise ReconciliationError("Statement line is not matched")
        if not await recon.delete_match(self._conn, line_id):
            raise ReconciliationError("Statement line has no confirmed match")
        await recon.update_line_status(self._conn, line_id, status="unmatched")

    async def ignore_line(self, statement_id: int, line_id: int, reason: str | None = None) -> None:
        """Mark an open, unmatched statement line as intentionally excluded."""
        workspace = await self._open_workspace(statement_id)
        line = self._line_for_workspace(workspace, line_id)
        if line.status != "unmatched":
            raise ReconciliationError("Only unmatched statement lines can be ignored")
        await recon.update_line_status(self._conn, line_id, status="ignored", ignore_reason=reason)

    async def period_status(self, statement_id: int) -> PeriodStatus:
        """Return the soft-close gates, comparing ledger balance at statement end."""
        workspace = await self._workspace(statement_id)
        statement = workspace.statement
        ledger_balance = await account_balance_paise(
            self._conn, statement.account_id, as_of=statement.period_end
        )
        unmatched_lines = sum(line.status == "unmatched" for line in workspace.lines)
        unmatched_ledger = await self._unmatched_ledger_count(
            account_id=statement.account_id,
            start=statement.period_start,
            end=statement.period_end,
        )
        return PeriodStatus(
            statement_id=statement_id,
            ledger_balance_paise=ledger_balance,
            statement_closing_balance_paise=statement.closing_balance_paise,
            balance_difference_paise=ledger_balance - statement.closing_balance_paise,
            unmatched_line_count=unmatched_lines,
            unmatched_ledger_count=unmatched_ledger,
        )

    async def soft_close(self, statement_id: int) -> PeriodStatus:
        """Soft-close a period only after every line clears and balances agree."""
        workspace = await self._open_workspace(statement_id)
        status = await self.period_status(workspace.statement.id)
        if status.unmatched_line_count:
            raise ReconciliationError("Cannot close statement with unmatched lines")
        if not status.is_balanced:
            raise ReconciliationError("Cannot close statement while ledger balance differs")
        await recon.set_statement_status(self._conn, workspace.statement.id, status="reconciled")
        return status

    async def reopen(self, statement_id: int) -> None:
        """Reopen a soft-closed statement for explicit further reconciliation."""
        workspace = await self._workspace(statement_id)
        if workspace.statement.status != "reconciled":
            raise ReconciliationError("Statement is already open")
        await recon.set_statement_status(self._conn, statement_id, status="open")

    async def create_adjustment(
        self,
        statement_id: int,
        line_id: int,
        *,
        counterpart_account_id: int,
        category: str,
        payee: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Post an explicit bank income or expense adjustment and match its line."""
        workspace = await self._open_workspace(statement_id)
        line = self._line_for_workspace(workspace, line_id)
        if line.status != "unmatched":
            raise ReconciliationError("Only unmatched statement lines can be adjusted")

        if line.direction == "out":
            postings = builders.build_bank_expense(
                bank_id=workspace.statement.account_id,
                expense_account_id=counterpart_account_id,
                amount_paise=line.amount_paise,
                category=category,
            )
        else:
            postings = builders.build_bank_income(
                bank_id=workspace.statement.account_id,
                income_account_id=counterpart_account_id,
                amount_paise=line.amount_paise,
                category=category,
            )
        transaction_id = await ledger_service.post(
            self._conn,
            PostTransactionInput(
                tx_date=line.tx_date,
                postings=postings,
                payee=payee or line.payee,
                notes=notes or line.narration,
                source="recon_adjustment",
                external_key=f"recon-adjustment:{statement_id}:{line_id}",
            ),
        )
        await self.confirm_match(statement_id, line_id, transaction_id)
        return transaction_id

    @staticmethod
    def _to_statement_line(row: ParsedImportRow | NewStatementLine) -> NewStatementLine:
        if isinstance(row, NewStatementLine):
            return row
        return NewStatementLine(
            tx_date=row.tx_date,
            amount_paise=abs(row.amount_paise),
            direction="in" if row.transaction_type == "credit" else "out",
            payee=row.merchant,
            narration=row.notes,
        )

    async def _workspace(self, statement_id: int) -> StatementWorkspace:
        workspace = await recon.get_statement_workspace(self._conn, statement_id)
        if workspace is None:
            raise ReconciliationError(f"Statement {statement_id} does not exist")
        return workspace

    async def _open_workspace(self, statement_id: int) -> StatementWorkspace:
        workspace = await self._workspace(statement_id)
        if workspace.statement.status != "open":
            raise ReconciliationError("Statement is reconciled; reopen it first")
        return workspace

    @staticmethod
    def _line_for_workspace(workspace: StatementWorkspace, line_id: int) -> ReconStatementLine:
        for line in workspace.lines:
            if line.id == line_id:
                return line
        raise ReconciliationError("Statement line does not belong to statement")

    async def _ledger_candidates(
        self, *, account_id: int, start: date, end: date, window_days: int
    ) -> tuple[LedgerMatchCandidate, ...]:
        cursor = await self._conn.execute(
            """
            SELECT tx.id, posting.account_id, tx.date, posting.amount_paise, tx.payee
            FROM ledger_transactions AS tx
            JOIN ledger_postings AS posting ON posting.transaction_id = tx.id
            WHERE posting.account_id = ?
              AND tx.status = 'posted'
              AND tx.date BETWEEN date(?, ?) AND date(?, ?)
            ORDER BY tx.date, tx.id
            """,
            (
                account_id,
                start.isoformat(),
                f"-{window_days} days",
                end.isoformat(),
                f"+{window_days} days",
            ),
        )
        return tuple(
            LedgerMatchCandidate(
                transaction_id=int(row[0]),
                account_id=int(row[1]),
                tx_date=date.fromisoformat(str(row[2])),
                amount_paise=int(row[3]),
                payee=None if row[4] is None else str(row[4]),
            )
            for row in await cursor.fetchall()
        )

    async def _matched_ledger_transaction_ids(self) -> frozenset[int]:
        cursor = await self._conn.execute("SELECT ledger_transaction_id FROM recon_matches")
        return frozenset(int(row[0]) for row in await cursor.fetchall())

    async def _transaction_posts_to_account(self, transaction_id: int, account_id: int) -> bool:
        cursor = await self._conn.execute(
            """
            SELECT 1
            FROM ledger_transactions AS tx
            JOIN ledger_postings AS posting ON posting.transaction_id = tx.id
            WHERE tx.id = ? AND tx.status = 'posted' AND posting.account_id = ?
            """,
            (transaction_id, account_id),
        )
        return await cursor.fetchone() is not None

    async def _unmatched_ledger_count(self, *, account_id: int, start: date, end: date) -> int:
        cursor = await self._conn.execute(
            """
            SELECT COUNT(DISTINCT tx.id)
            FROM ledger_transactions AS tx
            JOIN ledger_postings AS posting ON posting.transaction_id = tx.id
            WHERE posting.account_id = ?
              AND tx.status = 'posted'
              AND tx.date BETWEEN ? AND ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM recon_matches AS matched
                  WHERE matched.ledger_transaction_id = tx.id
              )
            """,
            (account_id, start.isoformat(), end.isoformat()),
        )
        row = await cursor.fetchone()
        return 0 if row is None else int(row[0])
