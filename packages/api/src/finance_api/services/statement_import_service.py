"""Gmail OAuth fetch + bank-parser preview for statement import."""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
import uuid
from dataclasses import dataclass, field
import calendar
from datetime import UTC, date
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import aiosqlite

from finance_api.services.credit_card_statement_service import build_credit_card_statement_payload
from finance_api.services.gmail_sync import get_gmail_service, header_value
from finance_api.settings import ApiSettings
from finance_common.classification.cc_statement_llm import enrich_cc_line_items_with_llm
from finance_common.parsing.bank_parsers.registry import issuer_to_bank_slug
from finance_common.parsing.statement_tags import CompiledTagRule, compile_tag_rules, compute_tags
from finance_common.repositories import statement_import as si_repo

logger = logging.getLogger(__name__)

_MAX_MESSAGES_PER_RULE = 50

CSV_COLUMNS = [
    "id",
    "date",
    "bank",
    "card",
    "description",
    "amount",
    "currency",
    "category",
    "transaction_type",
    "tx_kind",
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
    llm_model: str | None = None
    tags_source: str = "regex"
    category_source: str = "rules"


def gmail_after_date(fetch_months: int) -> str:
    """Rolling calendar date N months before today (Gmail `after:YYYY/MM/DD`)."""
    months = max(1, int(fetch_months))
    today = date.today()
    month = today.month - months
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(today.day, last_day)
    return f"{year}/{month:02d}/{day:02d}"


def max_messages_for_fetch(fetch_months: int) -> int:
    """Cap Gmail list size — one statement email per month plus buffer, or 50 when unlimited."""
    if int(fetch_months) <= 0:
        return _MAX_MESSAGES_PER_RULE
    months = max(1, int(fetch_months))
    return min(_MAX_MESSAGES_PER_RULE, months + 3)


def build_gmail_query_for_rule(
    from_emails: list[str],
    subject_contains: str | None,
    *,
    fetch_months: int = 3,
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
    if fetch_months > 0:
        parts.append(f"after:{gmail_after_date(fetch_months)}")
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
    tx_kind = str(line.get("tx_kind") or ("payment" if tx_type == "credit" else "spend"))
    # Positive = spend/charges, negative = credits (payment, refund, cashback)
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
        "tx_kind": tx_kind,
        "category_source": line.get("category_source") or "rules",
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


def _snapshot_has_gmail_message(transactions: list[dict[str, Any]], gmail_message_id: str) -> bool:
    return any(str(t.get("gmail_message_id") or "") == gmail_message_id for t in transactions)


async def _try_load_existing_transactions(
    conn: aiosqlite.Connection,
) -> tuple[int | None, list[dict[str, Any]]]:
    row = await si_repo.get_latest_snapshot(conn)
    if row is None:
        return None, []
    try:
        snapshot_id, transactions = await _load_latest_mutable(conn)
    except ValueError:
        return row.id, []
    return snapshot_id, transactions


async def fetch_and_parse(
    conn: aiosqlite.Connection,
    credentials_path: Path,
    token_path: Path,
    settings: ApiSettings,
    *,
    force: bool = False,
) -> FetchPreviewResult:
    """Scan Gmail per enabled rule, parse PDFs, return preview rows and save snapshot."""
    result = FetchPreviewResult()
    rules = await si_repo.list_rules(conn, enabled_only=True)
    if not rules:
        return result

    tag_rules = await _load_compiled_tags(conn)
    existing_snapshot_id, existing_transactions = await _try_load_existing_transactions(conn)

    try:
        service = get_gmail_service(credentials_path, token_path)
    except Exception as e:
        logger.exception("Gmail service init failed (statement import)")
        raise RuntimeError(f"Gmail authentication failed: {e}") from e

    all_transactions: list[dict[str, Any]] = []
    source_gmail_ids: list[str] = []
    scanned_ids: set[str] = set()
    pending_lines: list[dict[str, Any]] = []

    for rule in rules:
        if not rule.from_emails:
            result.skipped.append(
                {"rule_id": str(rule.id), "reason": "no_from_emails", "bank": rule.bank}
            )
            continue

        query = build_gmail_query_for_rule(
            rule.from_emails,
            rule.subject_contains,
            fetch_months=rule.fetch_months,
        )
        max_results = max_messages_for_fetch(rule.fetch_months)
        try:
            list_result = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
        except Exception as e:
            logger.warning("Gmail list failed for rule %s: %s", rule.id, e)
            result.skipped.append(
                {"rule_id": str(rule.id), "reason": "gmail_list_failed", "bank": rule.bank}
            )
            continue

        messages = list_result.get("messages") or []
        if not messages:
            result.skipped.append(
                {
                    "rule_id": str(rule.id),
                    "reason": "no_emails_in_window",
                    "bank": rule.bank,
                    "fetch_months": str(rule.fetch_months),
                }
            )
            logger.info(
                "Gmail returned 0 messages for rule %s (%s), fetch_months=%s, q=%s",
                rule.id,
                rule.bank,
                rule.fetch_months,
                query,
            )
        for msg_ref in messages:
            msg_id = str(msg_ref["id"])
            if msg_id in scanned_ids:
                continue
            scanned_ids.add(msg_id)
            result.gmail_scanned += 1

            if (
                not force
                and await si_repo.is_gmail_message_fetched(conn, msg_id)
                and _snapshot_has_gmail_message(existing_transactions, msg_id)
            ):
                result.skipped.append(
                    {
                        "gmail_message_id": msg_id,
                        "reason": "already_fetched",
                        "bank": rule.bank,
                    }
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
                    include_payments=True,
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
                pending_lines.append(
                    {
                        **line,
                        "_bank": rule.bank,
                        "_card": rule.card,
                        "_statement_period": statement_period,
                        "_gmail_message_id": msg_id,
                    }
                )

            await si_repo.record_fetched_message(
                conn, gmail_message_id=msg_id, rule_id=rule.id
            )
            source_gmail_ids.append(msg_id)
            result.statements_parsed += 1

    enriched_lines, llm_model = await enrich_cc_line_items_with_llm(pending_lines, settings)
    result.llm_model = llm_model
    if llm_model:
        result.category_source = "llm"

    for line in enriched_lines:
        all_transactions.append(
            _line_item_to_preview_row(
                line,
                bank=str(line.pop("_bank")),
                card=str(line.pop("_card")),
                statement_period=str(line.pop("_statement_period")),
                gmail_message_id=str(line.pop("_gmail_message_id")),
                tag_rules=tag_rules,
            )
        )

    all_transactions.sort(key=lambda r: (r.get("date") or "", r.get("bank") or ""))
    all_transactions = ensure_transaction_ids(all_transactions)

    newly_parsed_ids = set(source_gmail_ids)
    kept = [
        t
        for t in existing_transactions
        if not str(t.get("gmail_message_id") or "")
        or str(t.get("gmail_message_id") or "") not in newly_parsed_ids
    ]
    merged = sorted(
        kept + all_transactions,
        key=lambda r: (r.get("date") or "", r.get("bank") or ""),
    )
    merged = ensure_transaction_ids(merged)

    if not all_transactions and existing_transactions:
        result.transactions = existing_transactions
        result.snapshot_id = existing_snapshot_id
        return result

    result.transactions = merged

    if existing_snapshot_id is not None:
        await si_repo.update_snapshot_transactions(conn, existing_snapshot_id, merged)
        result.snapshot_id = existing_snapshot_id
    else:
        snapshot_id = await si_repo.insert_snapshot(
            conn,
            gmail_scanned=result.gmail_scanned,
            statements_parsed=result.statements_parsed,
            skipped=result.skipped,
            transactions=merged,
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


def ensure_transaction_ids(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign stable string ids for CRUD in the UI."""
    out: list[dict[str, Any]] = []
    for tx in transactions:
        row = dict(tx)
        if not row.get("id"):
            row["id"] = str(uuid.uuid4())
        out.append(row)
    return out


def _tx_kind_to_type(tx_kind: str) -> str:
    if tx_kind in ("payment", "refund", "cashback"):
        return "credit"
    return "debit"


def amount_from_kind(raw_amount: float, tx_kind: str) -> float:
    """Positive spend/charges; negative credits (payment, refund, cashback)."""
    amt = abs(float(raw_amount))
    if tx_kind in ("payment", "refund", "cashback"):
        return -amt
    return amt


def body_to_transaction_row(body: dict[str, Any], *, tx_id: str | None = None) -> dict[str, Any]:
    tx_kind = str(body.get("tx_kind") or "spend").strip().lower()
    amount = amount_from_kind(float(body.get("amount") or 0), tx_kind)
    return {
        "id": tx_id or str(uuid.uuid4()),
        "date": str(body.get("date") or "").strip(),
        "bank": str(body.get("bank") or "").strip(),
        "card": str(body.get("card") or "").strip(),
        "description": str(body.get("description") or "").strip(),
        "amount": amount,
        "currency": str(body.get("currency") or "INR").strip(),
        "category": body.get("category"),
        "transaction_type": _tx_kind_to_type(tx_kind),
        "tx_kind": tx_kind,
        "tags": str(body.get("tags") or "").strip(),
        "statement_period": str(body.get("statement_period") or "").strip(),
        "gmail_message_id": str(body.get("gmail_message_id") or "").strip(),
        "category_source": body.get("category_source") or "manual",
    }


async def _load_latest_mutable(conn: aiosqlite.Connection) -> tuple[int, list[dict[str, Any]]]:
    row = await si_repo.get_latest_snapshot(conn)
    if row is None:
        raise ValueError("no_snapshot")
    try:
        raw = json.loads(row.transactions_json)
    except json.JSONDecodeError as e:
        raise ValueError("invalid_snapshot") from e
    if not isinstance(raw, list):
        raw = []
    transactions = ensure_transaction_ids([dict(x) for x in raw if isinstance(x, dict)])
    if json.dumps(transactions, ensure_ascii=False) != row.transactions_json:
        await si_repo.update_snapshot_transactions(conn, row.id, transactions)
    return row.id, transactions


async def _save_latest(conn: aiosqlite.Connection, transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshot_id, _ = await _load_latest_mutable(conn)
    sorted_tx = sorted(transactions, key=lambda r: (r.get("date") or "", r.get("bank") or ""))
    await si_repo.update_snapshot_transactions(conn, snapshot_id, sorted_tx)
    await si_repo.release_fetched_messages_without_transactions(conn, sorted_tx)
    return sorted_tx


async def create_snapshot_transaction(
    conn: aiosqlite.Connection,
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    _, transactions = await _load_latest_mutable(conn)
    transactions.append(body_to_transaction_row(body))
    return await _save_latest(conn, transactions)


async def update_snapshot_transaction(
    conn: aiosqlite.Connection,
    tx_id: str,
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    _, transactions = await _load_latest_mutable(conn)
    found = False
    updated: list[dict[str, Any]] = []
    for tx in transactions:
        if str(tx.get("id")) == tx_id:
            updated.append(body_to_transaction_row(body, tx_id=tx_id))
            found = True
        else:
            updated.append(tx)
    if not found:
        raise ValueError("not_found")
    return await _save_latest(conn, updated)


async def delete_snapshot_transactions(
    conn: aiosqlite.Connection,
    tx_ids: list[str],
) -> list[dict[str, Any]]:
    id_set = {str(i) for i in tx_ids if str(i).strip()}
    if not id_set:
        raise ValueError("empty_ids")
    _, transactions = await _load_latest_mutable(conn)
    remaining = [tx for tx in transactions if str(tx.get("id")) not in id_set]
    if len(remaining) == len(transactions):
        raise ValueError("not_found")
    return await _save_latest(conn, remaining)


async def get_latest_transactions(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    _, transactions = await _load_latest_mutable(conn)
    return transactions
