"""Gmail API integration — fetch and stage transaction emails."""

from __future__ import annotations

import base64
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

import aiosqlite

from finance_common.classification.matcher import ClassificationResult, match_merchant
from finance_common.parsing.gmail_email import classify_and_parse
from finance_common.repositories import credit_cards as cc_repo
from finance_common.repositories import email_staging as staging_repo
from finance_common.repositories import merchant_rules as merchant_rules_repo
from finance_common.repositories import settings_repo

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Max messages fetched per rolling sync run
_MAX_MESSAGES = 200

# Hard cap for a single historical import (safety guard against runaway API calls)
_HISTORICAL_MAX_MESSAGES = 2000

# Gmail search query — known financial senders + transaction keywords in subject
_GMAIL_QUERY = (
    "("
    "from:hdfcbank.com OR from:icicibank.com OR from:sbi.co.in OR "
    "from:axisbank.com OR from:kotak.com OR from:indusind.com OR "
    "from:idfcfirstbank.com OR from:federalbank.co.in OR from:yesbank.in OR "
    "from:pnb.co.in OR from:bankofbaroda.in OR from:rblbank.com OR "
    "from:swiggy.in OR from:zomato.com OR from:amazon.in OR from:flipkart.com OR "
    "from:myntra.com OR from:paytm.com OR from:phonepe.com OR "
    "from:makemytrip.com OR from:irctc.co.in OR from:bigbasket.com OR "
    "from:blinkit.com OR from:zepto.co OR from:airtel.in"
    ") OR subject:(debited OR credited OR \"transaction alert\" OR \"payment successful\" OR "
    "\"order confirmed\" OR \"order placed\")"
)

_SETTINGS_KEY_TS = "gmail_last_sync_ts"


def _get_service(credentials_path: Path, token_path: Path):  # type: ignore[return]
    """Build an authenticated Gmail API service; refreshes token automatically."""
    try:
        from google.auth.transport.requests import Request  # noqa: PLC0415
        from google.oauth2.credentials import Credentials  # noqa: PLC0415
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415
        from googleapiclient.discovery import build  # noqa: PLC0415
    except ImportError as e:
        raise ImportError(
            "Google API libraries not installed. Run: uv add google-auth-oauthlib google-auth-httplib2 google-api-python-client"
        ) from e

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), _SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _header_value(headers: list[dict], name: str) -> str | None:
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value")
    return None


# Public aliases — reused by cc_statement_fetch.py so it shares the same OAuth client and
# header-parsing logic rather than duplicating it.
get_gmail_service = _get_service
header_value = _header_value


def _decode_body(data: str) -> str:
    """Base64url-decode a Gmail message part body."""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_text(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime == "text/plain" and body_data:
        return _decode_body(body_data)

    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _extract_text(part)
            if text:
                return text

    return ""


async def sync_gmail_transactions(
    conn: aiosqlite.Connection,
    credentials_path: Path,
    token_path: Path,
    lookback_hours: int = 4,
) -> int:
    """
    Fetch recent emails from Gmail, parse for transactions, insert to staging table.
    Returns count of new staged items.
    """
    try:
        service = _get_service(credentials_path, token_path)
    except Exception:
        logger.exception("Gmail service init failed")
        return 0

    # Determine search window
    last_ts_str = await settings_repo.get_value(conn, _SETTINGS_KEY_TS)
    if last_ts_str:
        try:
            after_ts = int(last_ts_str)
        except ValueError:
            after_ts = int(time.time()) - lookback_hours * 3600
    else:
        # First run: look back 30 days
        after_ts = int(time.time()) - 30 * 24 * 3600

    query = f"after:{after_ts} ({_GMAIL_QUERY})"
    logger.debug("Gmail sync query: %s", query)

    try:
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=_MAX_MESSAGES)
            .execute()
        )
        messages = result.get("messages", [])
    except Exception:
        logger.exception("Gmail messages.list failed")
        return 0

    rules = await merchant_rules_repo.list_active_rules_for_matching(conn)

    def classify(merchant: str) -> ClassificationResult:
        return match_merchant(merchant, rules)

    new_count = 0
    for msg_ref in messages:
        msg_id = msg_ref["id"]
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
        except Exception:
            logger.warning("Failed to fetch Gmail message %s", msg_id)
            continue

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])

        subject = _header_value(headers, "Subject") or ""
        sender = _header_value(headers, "From") or ""
        date_header = _header_value(headers, "Date")
        body = _extract_text(payload) or msg.get("snippet", "")

        parsed = classify_and_parse(subject, sender, body, date_header, classify=classify)
        if parsed is None:
            continue

        # Route CC alert emails to the correct CC linked account
        suggested_account_id: int | None = None
        if parsed.cc_last_four:
            suggested_account_id = await cc_repo.find_card_account_id_by_last_four(
                conn, parsed.cc_last_four
            )

        row_id = await staging_repo.insert_staged(
            conn,
            gmail_message_id=msg_id,
            email_date=parsed.tx_date.isoformat(),
            email_subject=subject[:500] if subject else None,
            email_from=sender[:200] if sender else None,
            raw_snippet=parsed.raw_snippet[:500] if parsed.raw_snippet else None,
            parsed_date=parsed.tx_date.isoformat(),
            parsed_amount_paise=parsed.amount_paise,
            parsed_merchant=parsed.merchant,
            parsed_category=parsed.category,
            parsed_payment_mode=parsed.payment_mode,
            parsed_transaction_type=parsed.transaction_type,
            suggested_account_id=suggested_account_id,
        )
        if row_id is not None:
            new_count += 1

    # Advance checkpoint to now
    await settings_repo.set_value(conn, _SETTINGS_KEY_TS, str(int(time.time())))
    logger.info("Gmail sync complete: %s new item(s) from %s email(s)", new_count, len(messages))
    return new_count


async def historical_sync_gmail_transactions(
    conn: aiosqlite.Connection,
    credentials_path: Path,
    token_path: Path,
    from_date: date,
    to_date: date,
) -> dict[str, int]:
    """
    Fetch emails in a specific date range and stage any transaction emails found.

    Unlike the rolling sync, this does NOT update gmail_last_sync_ts so the
    normal 3-hour job is unaffected.

    Returns {"new_items": N, "total_scanned": M}.
    """
    try:
        service = _get_service(credentials_path, token_path)
    except Exception:
        logger.exception("Gmail service init failed (historical sync)")
        return {"new_items": 0, "total_scanned": 0}

    # Convert date boundaries to Unix timestamps
    after_ts = int(datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc).timestamp())
    # to_date is inclusive — shift to end of that day
    to_inclusive = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=timezone.utc)
    before_ts = int(to_inclusive.timestamp())

    query = f"after:{after_ts} before:{before_ts} ({_GMAIL_QUERY})"
    logger.info(
        "Gmail historical sync: %s → %s (query: %s)",
        from_date.isoformat(),
        to_date.isoformat(),
        query,
    )

    # Paginate through all matching messages up to _HISTORICAL_MAX_MESSAGES
    all_message_refs: list[dict] = []
    page_token: str | None = None

    while len(all_message_refs) < _HISTORICAL_MAX_MESSAGES:
        try:
            kwargs: dict = {
                "userId": "me",
                "q": query,
                "maxResults": min(500, _HISTORICAL_MAX_MESSAGES - len(all_message_refs)),
            }
            if page_token:
                kwargs["pageToken"] = page_token

            result = service.users().messages().list(**kwargs).execute()
        except Exception:
            logger.exception("Gmail messages.list failed (historical sync)")
            break

        batch = result.get("messages", [])
        all_message_refs.extend(batch)

        page_token = result.get("nextPageToken")
        if not page_token or not batch:
            break

    logger.info("Gmail historical sync: %s message(s) found to process", len(all_message_refs))

    hist_rules = await merchant_rules_repo.list_active_rules_for_matching(conn)

    def classify_hist(merchant: str) -> ClassificationResult:
        return match_merchant(merchant, hist_rules)

    new_count = 0
    total_scanned = 0
    for msg_ref in all_message_refs:
        msg_id = msg_ref["id"]
        total_scanned += 1
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
        except Exception:
            logger.warning("Failed to fetch Gmail message %s", msg_id)
            continue

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])

        subject = _header_value(headers, "Subject") or ""
        sender = _header_value(headers, "From") or ""
        date_header = _header_value(headers, "Date")
        body = _extract_text(payload) or msg.get("snippet", "")

        parsed = classify_and_parse(subject, sender, body, date_header, classify=classify_hist)
        if parsed is None:
            continue

        # Route CC alert emails to the correct CC linked account
        suggested_account_id_hist: int | None = None
        if parsed.cc_last_four:
            suggested_account_id_hist = await cc_repo.find_card_account_id_by_last_four(
                conn, parsed.cc_last_four
            )

        row_id = await staging_repo.insert_staged(
            conn,
            gmail_message_id=msg_id,
            email_date=parsed.tx_date.isoformat(),
            email_subject=subject[:500] if subject else None,
            email_from=sender[:200] if sender else None,
            raw_snippet=parsed.raw_snippet[:500] if parsed.raw_snippet else None,
            parsed_date=parsed.tx_date.isoformat(),
            parsed_amount_paise=parsed.amount_paise,
            parsed_merchant=parsed.merchant,
            parsed_category=parsed.category,
            parsed_payment_mode=parsed.payment_mode,
            parsed_transaction_type=parsed.transaction_type,
            suggested_account_id=suggested_account_id_hist,
        )
        if row_id is not None:
            new_count += 1

    logger.info(
        "Gmail historical sync complete: %s new item(s) from %s scanned (%s → %s)",
        new_count,
        total_scanned,
        from_date.isoformat(),
        to_date.isoformat(),
    )
    return {"new_items": new_count, "total_scanned": total_scanned}
