"""Auto-fetch credit-card statement PDF attachments from Gmail.

Reuses the app's existing Gmail OAuth client (`gmail_sync.py`) — no separate IMAP or
app-password credential story. Downloads statement-shaped emails' PDF attachments,
matches them to a card by last-four digits, and stages them through the same
bank-aware parsing pipeline as manual upload (`build_credit_card_statement_payload`),
always landing as `status='pending_review'` — auto-fetch never applies transactions on
its own, matching the human-in-the-loop review step of manual upload.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import aiosqlite

from finance_api.services.credit_card_statement_service import (
    build_credit_card_statement_payload,
    dumps_line_items,
    dumps_summary,
)
from finance_api.services.gmail_sync import get_gmail_service, header_value
from finance_common.parsing.gmail_email import BANK_DOMAINS, extract_cc_last_four
from finance_common.repositories import credit_cards as cc_repo

logger = logging.getLogger(__name__)

_MAX_MESSAGES_PER_RUN = 50

_STATEMENT_QUERY = (
    "(" + " OR ".join(f"from:{d}" for d in sorted(BANK_DOMAINS)) + ") "
    'has:attachment filename:pdf '
    '(subject:statement OR subject:"e-statement" OR subject:"credit card statement")'
)


def _decode_attachment(data: str) -> bytes:
    """Base64url-decode a Gmail attachment payload (raw bytes, not text)."""
    return base64.urlsafe_b64decode(data + "==")


def _find_pdf_attachment(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Recursively find the first PDF attachment's (attachmentId, filename) in a message payload."""
    for part in payload.get("parts", []):
        filename = str(part.get("filename") or "")
        mime = str(part.get("mimeType") or "")
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if attachment_id and (filename.lower().endswith(".pdf") or mime == "application/pdf"):
            return str(attachment_id), filename or None
        if part.get("parts"):
            found_id, found_name = _find_pdf_attachment(part)
            if found_id:
                return found_id, found_name
    return None, None


async def fetch_cc_statements(
    conn: aiosqlite.Connection,
    credentials_path: Path,
    token_path: Path,
) -> dict[str, int]:
    """Scan Gmail for statement emails, download PDF attachments, match to a card by
    last-four, and stage new statements as pending_review. Returns fetch counts."""
    counts = {"fetched": 0, "staged": 0, "skipped_unmatched": 0, "skipped_duplicate": 0}

    cards = await cc_repo.list_auto_fetch_enabled_cards(conn)
    if not cards:
        return counts

    try:
        service = get_gmail_service(credentials_path, token_path)
    except Exception:
        logger.exception("Gmail service init failed (cc statement fetch)")
        return counts

    try:
        result = (
            service.users()
            .messages()
            .list(userId="me", q=_STATEMENT_QUERY, maxResults=_MAX_MESSAGES_PER_RUN)
            .execute()
        )
    except Exception:
        logger.exception("Gmail messages.list failed (cc statement fetch)")
        return counts

    messages = result.get("messages", [])
    counts["fetched"] = len(messages)

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        existing = await cc_repo.get_statement_by_gmail_message_id(conn, msg_id)
        if existing is not None:
            counts["skipped_duplicate"] += 1
            continue

        try:
            msg = (
                service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            )
        except Exception:
            logger.warning("Failed to fetch Gmail message %s", msg_id)
            continue

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        subject = header_value(headers, "Subject") or ""
        snippet = msg.get("snippet", "")

        last_four = extract_cc_last_four(f"{subject} {snippet}")
        card = await cc_repo.find_credit_card_by_last_four(conn, last_four) if last_four else None
        if card is None:
            counts["skipped_unmatched"] += 1
            logger.info(
                "CC statement email %s: no card match for last-four %s", msg_id, last_four
            )
            continue

        attachment_id, attachment_filename = _find_pdf_attachment(payload)
        if attachment_id is None:
            continue

        try:
            att = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=msg_id, id=attachment_id)
                .execute()
            )
            pdf_bytes = _decode_attachment(att["data"])
        except Exception:
            logger.warning("Failed to download attachment for message %s", msg_id)
            continue

        filename = attachment_filename or "statement.pdf"
        try:
            summary, line_items, preview = await build_credit_card_statement_payload(
                filename,
                pdf_bytes,
                pdf_password=card.statement_pdf_password,
                issuer=card.issuer,
                conn=conn,
            )
        except ValueError:
            logger.warning(
                "Could not parse auto-fetched statement for card %s (msg %s)", card.id, msg_id
            )
            continue

        await cc_repo.insert_statement(
            conn,
            credit_card_id=card.id,
            filename=filename,
            period_start=summary.get("period_start"),
            period_end=summary.get("period_end"),
            extraction_preview=preview,
            summary_json=dumps_summary(summary),
            line_items_json=dumps_line_items(line_items),
            status="pending_review",
            source="auto_fetch",
            gmail_message_id=msg_id,
        )
        counts["staged"] += 1

    return counts
