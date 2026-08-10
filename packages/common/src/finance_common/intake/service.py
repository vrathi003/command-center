"""Decision service for posting or quarantining incoming transactions."""

from __future__ import annotations

from enum import StrEnum

import aiosqlite
from loguru import logger

from finance_common.intake.dedupe import find_soft_duplicate
from finance_common.intake.models import Candidate
from finance_common.intake.posting_plan import IntakePlanError, plan_postings
from finance_common.ledger import service as ledger_service
from finance_common.parsing.account_mentions import narration_suggests_bank_transfer
from finance_common.project_config import load_project_config
from finance_common.repositories.domain_events import append_event
from finance_common.repositories.intake_candidates import (
    find_posted_ledger_transaction_id,
    save_candidate,
)


class Decision(StrEnum):
    POSTED = "posted"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"
    NOOP = "noop"


async def _quarantine(
    conn: aiosqlite.Connection, candidate: Candidate, reason: str
) -> tuple[Decision, int]:
    candidate_id = await save_candidate(
        conn,
        candidate,
        status="pending",
        quarantine_reason=reason,
    )
    await append_event(
        conn,
        event_type="intake.quarantine_created",
        payload={
            "candidate_id": candidate_id,
            "reason": reason,
            "source": candidate.source,
            "external_key": candidate.external_key,
        },
    )
    logger.info(
        "Intake candidate {} quarantined: {}",
        candidate_id,
        reason,
    )
    return Decision.QUARANTINED, candidate_id


async def ingest(
    conn: aiosqlite.Connection, candidate: Candidate
) -> tuple[Decision, int | None]:
    """Auto-post a high-confidence candidate, or save it for review."""
    if candidate.external_key is not None:
        existing_id = await find_posted_ledger_transaction_id(conn, candidate.external_key)
        if existing_id is not None:
            return Decision.NOOP, existing_id

    if candidate.suggested_account_id is None:
        return await _quarantine(conn, candidate, "missing_account")

    config = await load_project_config(conn)
    duplicate_id = await find_soft_duplicate(
        conn,
        account_id=candidate.suggested_account_id,
        amount_paise=candidate.amount_paise,
        tx_date=candidate.tx_date,
        payee=candidate.payee,
        window_days=config.intake_duplicate_date_window_days,
    )
    if duplicate_id is not None:
        return await _quarantine(conn, candidate, "possible_duplicate")

    if narration_suggests_bank_transfer(candidate.narration or ""):
        return await _quarantine(conn, candidate, "possible_transfer")

    if candidate.confidence < config.intake_auto_post_min_confidence:
        return await _quarantine(conn, candidate, "low_confidence")

    try:
        posting_plan = await plan_postings(conn, candidate)
    except IntakePlanError as error:
        return await _quarantine(conn, candidate, str(error))

    ledger_transaction_id = await ledger_service.post(conn, posting_plan)
    await save_candidate(
        conn,
        candidate,
        status="posted",
        ledger_transaction_id=ledger_transaction_id,
    )
    return Decision.POSTED, ledger_transaction_id
