"""Gmail attachment auto-fetch service tests."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from finance_api.services.cc_statement_fetch import (
    _decode_attachment,
    _find_pdf_attachment,
    fetch_cc_statements,
)
from finance_common.config import AppSettings
from finance_common.db import ensure_database, open_db
from finance_common.repositories import credit_cards as cc_repo


def test_decode_attachment_roundtrips() -> None:
    raw = b"hello pdf bytes"
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    assert _decode_attachment(encoded) == raw


def test_find_pdf_attachment_locates_nested_part() -> None:
    payload = {
        "parts": [
            {"mimeType": "text/plain", "body": {"data": "aGk="}},
            {
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "application/pdf",
                        "filename": "stmt.pdf",
                        "body": {"attachmentId": "ATT1"},
                    },
                ],
            },
        ]
    }
    att_id, filename = _find_pdf_attachment(payload)
    assert att_id == "ATT1"
    assert filename == "stmt.pdf"


def test_find_pdf_attachment_none_when_no_pdf() -> None:
    payload = {"parts": [{"mimeType": "text/plain", "body": {"data": "aGk="}}]}
    assert _find_pdf_attachment(payload) == (None, None)


@pytest.mark.asyncio
async def test_fetch_cc_statements_short_circuits_when_no_cards_enabled() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        counts = await fetch_cc_statements(conn, settings.db_path, settings.db_path)
    assert counts == {"fetched": 0, "staged": 0, "skipped_unmatched": 0, "skipped_duplicate": 0}


@pytest.mark.asyncio
async def test_fetch_cc_statements_skips_duplicate_and_unmatched() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        card_id = await cc_repo.insert_credit_card(
            conn,
            name="Test HDFC",
            issuer="HDFC Bank",
            last_four="1234",
            credit_limit_paise=100_000,
            current_balance_paise=0,
            notes=None,
            auto_fetch_enabled=True,
        )
        # Pre-stage a statement so "dup-msg" is treated as already fetched.
        await cc_repo.insert_statement(
            conn,
            credit_card_id=card_id,
            filename="x.pdf",
            period_start=None,
            period_end=None,
            extraction_preview=None,
            summary_json="{}",
            line_items_json="[]",
            source="auto_fetch",
            gmail_message_id="dup-msg",
        )

        def _messages() -> SimpleNamespace:
            return SimpleNamespace(
                list=lambda **_kw: SimpleNamespace(
                    execute=lambda: {"messages": [{"id": "dup-msg"}, {"id": "unmatched-msg"}]}
                ),
                get=lambda **_kw: SimpleNamespace(
                    execute=lambda: {
                        "payload": {"headers": [{"name": "Subject", "value": "Your Statement"}]},
                        "snippet": "no card digits here",
                    }
                ),
            )

        fake_service = SimpleNamespace(users=lambda: SimpleNamespace(messages=_messages))

        with patch(
            "finance_api.services.cc_statement_fetch.get_gmail_service",
            return_value=fake_service,
        ):
            counts = await fetch_cc_statements(conn, settings.db_path, settings.db_path)

    assert counts["fetched"] == 2
    assert counts["skipped_duplicate"] == 1
    assert counts["skipped_unmatched"] == 1
    assert counts["staged"] == 0


@pytest.mark.asyncio
async def test_fetch_cc_statements_matches_by_last_four_and_stages() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        card_id = await cc_repo.insert_credit_card(
            conn,
            name="Test HDFC",
            issuer="HDFC Bank",
            last_four="1234",
            credit_limit_paise=100_000,
            current_balance_paise=0,
            notes=None,
            auto_fetch_enabled=True,
        )

        pdf_text = (
            "Domestic Transactions\n"
            "15/02/2025 12:02:24 PAYTM UTILITY NOIDA 20.00\n"
            "Reward Points Summary\n"
        )

        def _messages() -> SimpleNamespace:
            return SimpleNamespace(
                list=lambda **_kw: SimpleNamespace(
                    execute=lambda: {"messages": [{"id": "msg-1"}]}
                ),
                get=lambda **_kw: SimpleNamespace(
                    execute=lambda: {
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "Statement for card ending 1234"}
                            ],
                            "parts": [
                                {
                                    "mimeType": "application/pdf",
                                    "filename": "stmt.pdf",
                                    "body": {"attachmentId": "ATT1"},
                                },
                            ],
                        },
                        "snippet": "",
                    }
                ),
                attachments=lambda: SimpleNamespace(
                    get=lambda **_kw: SimpleNamespace(
                        execute=lambda: {
                            "data": base64.urlsafe_b64encode(b"%PDF-fake").decode().rstrip("=")
                        }
                    )
                ),
            )

        fake_service = SimpleNamespace(users=lambda: SimpleNamespace(messages=_messages))

        with (
            patch(
                "finance_api.services.cc_statement_fetch.get_gmail_service",
                return_value=fake_service,
            ),
            patch(
                "finance_api.services.credit_card_statement_service.extract_text_from_pdf_bytes",
                return_value=pdf_text,
            ),
        ):
            counts = await fetch_cc_statements(conn, settings.db_path, settings.db_path)

        assert counts["staged"] == 1
        stmt = await cc_repo.get_statement_by_gmail_message_id(conn, "msg-1")
        assert stmt is not None
        assert stmt.credit_card_id == card_id
        assert stmt.status == "pending_review"
        assert stmt.source == "auto_fetch"
