"""Gmail OAuth fetch + bank-parser preview for statement import."""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import aiosqlite

from finance_api.services.credit_card_statement_service import build_credit_card_statement_payload
from finance_api.services.gmail_sync import get_gmail_service, header_value
from finance_common.parsing.bank_parsers.registry import issuer_to_bank_slug
from finance_common.parsing.statement_tags import CompiledTagRule, compile_tag_rules, compute_tags
from finance_common.repositories import statement_import as si_repo

logger = logging.getLogger(__name__)

_MAX_MESSAGES_PER_RULE = 50

CSV_COLUMNS = [
    "date",
    "bank",
    "card",
    "description",
    "amount",
    "currency",
    "category",
    "transaction_type",
    "tags",
    "statement_period",
    "gmail_message_id",
]


@dataclass
class FetchPreviewResult:
    gmail_scanned: int = 0
    statements_parsed: int = 0
    skipped: list[dict[str, str]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    snapshot_id: int | None = None


def build_gmail_query_for_rule(
    from_emails: list[str],
    subject_contains: str | None,
) -> str:
    """Build a Gmail API search query mirroring CardQL IMAP FROM + SUBJECT filters."""
    parts: list[str] = []
    if from_emails:
        from_clause = " OR ".join(f"from:{addr.strip()}" for addr in from_emails if addr.strip())
        if len(from_emails) > 1:
            parts.append(f"({from_clause})")
        else:
            parts.append(from_clause)
    if subject_contains and subject_contains.strip():
        # Escape embedded quotes for Gmail query
        subj = subject_contains.strip().replace('"', '\\"')
        parts.append(f'subject:"{subj}"')
    parts.append("has:attachment filename:pdf")
    return " ".join(parts)


def _decode_attachment(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "==")


def _find_pdf_attachment(payload: dict[str, Any]) -> tuple[str | None, str | None]:
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


def _message_period(date_header: str | None, period_start: str | None) -> str:
    if period_start and len(period_start) >= 7:
        return period_start[:7]
    if not date_header:
        return "unknown"
    try:
        dt = parsedate_to_datetime(date_header)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).strftime("%Y-%m")
    except Exception:
        return "unknown"


def _line_item_to_preview_row(
    line: dict[str, Any],
    *,
    bank: str,
    card: str,
    statement_period: str,
    gmail_message_id: str,
    tag_rules: list[CompiledTagRule],
) -> dict[str, Any]:
    amount_paise = int(line.get("amount_paise") or 0)
    amount_rupees = round(amount_paise / 100.0, 2)
    tx_type = str(line.get("transaction_type") or "debit")
    # CardQL convention: positive spend, negative credit/refund
    amount_rupees = -abs(amount_rupees) if tx_type == "credit" else abs(amount_rupees)
    description = str(line.get("description") or "")
    tags = compute_tags(description, tag_rules)
    return {
        "date": str(line.get("date") or ""),
        "bank": bank,
        "card": card,
        "description": description,
        "amount": amount_rupees,
        "currency": "INR",
        "category": line.get("category"),
        "transaction_type": tx_type,
        "tags": tags,
        "statement_period": statement_period,
        "gmail_message_id": gmail_message_id,
    }


def transactions_to_csv(transactions: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in transactions:
        writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})
    return buf.getvalue()


async def _load_compiled_tags(conn: aiosqlite.Connection) -> list[CompiledTagRule]:
    rows = await si_repo.list_tag_rules(conn)
    enabled = [(r.tag_name, r.regex_patterns) for r in rows if r.is_enabled]
    return compile_tag_rules(enabled)


async def fetch_and_parse(
    conn: aiosqlite.Connection,
    credentials_path: Path,
    token_path: Path,
) -> FetchPreviewResult:
    """Scan Gmail per enabled rule, parse PDFs, return preview rows and save snapshot."""
    result = FetchPreviewResult()
    rules = await si_repo.list_rules(conn, enabled_only=True)
    if not rules:
        return result

    tag_rules = await _load_compiled_tags(conn)

    try:
        service = get_gmail_service(credentials_path, token_path)
    except Exception as e:
        logger.exception("Gmail service init failed (statement import)")
        raise RuntimeError(f"Gmail authentication failed: {e}") from e

    all_transactions: list[dict[str, Any]] = []
    source_gmail_ids: list[str] = []
    scanned_ids: set[str] = set()

    for rule in rules:
        if not rule.from_emails:
            result.skipped.append(
                {"rule_id": str(rule.id), "reason": "no_from_emails", "bank": rule.bank}
            )
            continue

        query = build_gmail_query_for_rule(rule.from_emails, rule.subject_contains)
        try:
            list_result = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=_MAX_MESSAGES_PER_RULE)
                .execute()
            )
        except Exception as e:
            logger.warning("Gmail list failed for rule %s: %s", rule.id, e)
            result.skipped.append(
                {"rule_id": str(rule.id), "reason": "gmail_list_failed", "bank": rule.bank}
            )
            continue

        messages = list_result.get("messages") or []
        for msg_ref in messages:
            msg_id = str(msg_ref["id"])
            if msg_id in scanned_ids:
                continue
            scanned_ids.add(msg_id)
            result.gmail_scanned += 1

            if await si_repo.is_gmail_message_fetched(conn, msg_id):
                result.skipped.append(
                    {"gmail_message_id": msg_id, "reason": "already_fetched", "bank": rule.bank}
                )
                continue

            try:
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )
            except Exception:
                result.skipped.append(
                    {
                        "gmail_message_id": msg_id,
                        "reason": "message_fetch_failed",
                        "bank": rule.bank,
                    }
                )
                continue

            payload = msg.get("payload", {})
            headers = payload.get("headers", [])
            subject = header_value(headers, "Subject") or ""
            date_hdr = header_value(headers, "Date")

            attachment_id, attachment_filename = _find_pdf_attachment(payload)
            if attachment_id is None:
                result.skipped.append(
                    {
                        "gmail_message_id": msg_id,
                        "reason": "no_pdf_attachment",
                        "bank": rule.bank,
                        "subject": subject[:120],
                    }
                )
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
                result.skipped.append(
                    {
                        "gmail_message_id": msg_id,
                        "reason": "attachment_download_failed",
                        "bank": rule.bank,
                    }
                )
                continue

            filename = attachment_filename or "statement.pdf"
            bank_slug = issuer_to_bank_slug(rule.bank)
            if not bank_slug:
                result.skipped.append(
                    {
                        "gmail_message_id": msg_id,
                        "reason": "unsupported_bank",
                        "bank": rule.bank,
                    }
                )
                continue

            try:
                summary, line_items, _preview = await build_credit_card_statement_payload(
                    filename,
                    pdf_bytes,
                    pdf_password=rule.pdf_password,
                    issuer=rule.bank,
                    conn=conn,
                )
            except ValueError as e:
                result.skipped.append(
                    {
                        "gmail_message_id": msg_id,
                        "reason": "parse_failed",
                        "bank": rule.bank,
                        "detail": str(e)[:200],
                    }
                )
                continue

            period_start = summary.get("period_start") if isinstance(summary, dict) else None
            statement_period = _message_period(date_hdr, period_start)
            for line in line_items:
                all_transactions.append(
                    _line_item_to_preview_row(
                        line,
                        bank=rule.bank,
                        card=rule.card,
                        statement_period=statement_period,
                        gmail_message_id=msg_id,
                        tag_rules=tag_rules,
                    )
                )

            await si_repo.record_fetched_message(
                conn, gmail_message_id=msg_id, rule_id=rule.id
            )
            source_gmail_ids.append(msg_id)
            result.statements_parsed += 1

    all_transactions.sort(key=lambda r: (r.get("date") or "", r.get("bank") or ""))
    result.transactions = all_transactions

    snapshot_id = await si_repo.insert_snapshot(
        conn,
        gmail_scanned=result.gmail_scanned,
        statements_parsed=result.statements_parsed,
        skipped=result.skipped,
        transactions=all_transactions,
        source_gmail_ids=source_gmail_ids,
    )
    result.snapshot_id = snapshot_id
    return result


def _find_local_config_dir() -> Path | None:
    """Locate `.local/config` by walking up from cwd."""
    start = Path.cwd().resolve()
    for candidate in [start, *start.parents]:
        cfg = candidate / ".local" / "config"
        if cfg.is_dir():
            return cfg
    return None


async def migrate_from_local_config(conn: aiosqlite.Connection) -> bool:
    """One-time seed from `.local/config/card_rules.json` and `tags.json`."""
    if await si_repo.count_rules(conn) > 0:
        return False

    cfg_dir = _find_local_config_dir()
    if cfg_dir is None:
        return False

    migrated = False
    card_rules_path = cfg_dir / "card_rules.json"
    if card_rules_path.is_file():
        try:
            raw = json.loads(card_rules_path.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                bank = str(item.get("bank") or "").strip()
                card = str(item.get("card") or bank or "Card").strip()
                from_emails = item.get("from_emails") or []
                if not isinstance(from_emails, list):
                    from_emails = [str(from_emails)]
                from_emails = [str(e).strip() for e in from_emails if str(e).strip()]
                if not bank or not from_emails:
                    continue
                passwords = item.get("passwords") or []
                pwd = None
                if isinstance(passwords, list) and passwords:
                    pwd = str(passwords[0])
                elif item.get("password"):
                    pwd = str(item["password"])
                await si_repo.create_rule(
                    conn,
                    bank=bank,
                    card=card,
                    from_emails=from_emails,
                    subject_contains=str(item["subject_contains"])
                    if item.get("subject_contains")
                    else None,
                    pdf_password=pwd,
                    is_enabled=True,
                )
                migrated = True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not migrate card_rules.json: %s", e)

    tags_path = cfg_dir / "tags.json"
    if tags_path.is_file():
        try:
            raw = json.loads(tags_path.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else []
            tag_rules: list[tuple[str, list[str], bool]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                tag_name = str(item.get("tag_name") or "").strip()
                patterns = item.get("regex_patterns") or []
                if not tag_name or not isinstance(patterns, list):
                    continue
                tag_rules.append(
                    (tag_name, [str(p) for p in patterns if str(p).strip()], True)
                )
            if tag_rules:
                await si_repo.replace_tag_rules(conn, tag_rules)
                migrated = True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not migrate tags.json: %s", e)

    if migrated:
        logger.info("Migrated statement import config from %s", cfg_dir)
    return migrated
