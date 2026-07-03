"""CC statement service: bank-specific parser is required, no heuristic/LLM fallback."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from finance_api.services.credit_card_statement_service import build_credit_card_statement_payload
from finance_common.config import AppSettings
from finance_common.db import ensure_database, open_db

_HDFC_TEXT = (
    "Domestic Transactions\n"
    "15/02/2025 12:02:24 PAYTM UTILITY NOIDA 20.00\n"
    "Reward Points Summary\n"
)


@pytest.mark.asyncio
async def test_build_payload_uses_bank_specific_parser_for_known_issuer() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        with patch(
            "finance_api.services.credit_card_statement_service.extract_text_from_pdf_bytes",
            return_value=_HDFC_TEXT,
        ):
            summary, lines, preview = await build_credit_card_statement_payload(
                "statement.pdf",
                b"%PDF-fake",
                pdf_password=None,
                issuer="HDFC Bank",
                conn=conn,
            )
    assert isinstance(summary, dict)
    assert preview is not None
    assert len(lines) == 1
    assert lines[0]["amount_paise"] == 2000
    assert "PAYTM" in lines[0]["description"]


@pytest.mark.asyncio
async def test_build_payload_raises_for_unsupported_issuer() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        with patch(
            "finance_api.services.credit_card_statement_service.extract_text_from_pdf_bytes",
            return_value="totally unrecognized statement text",
        ):
            with pytest.raises(ValueError, match="Supported banks"):
                await build_credit_card_statement_payload(
                    "statement.pdf",
                    b"%PDF-fake",
                    pdf_password=None,
                    issuer="Some Random Co-op Bank",
                    conn=conn,
                )


@pytest.mark.asyncio
async def test_build_payload_raises_when_known_bank_finds_no_rows() -> None:
    """A known bank with unrecognizable/empty statement text is a clear error, not a
    silent fallback to the (removed) generic heuristic/LLM path."""
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        with patch(
            "finance_api.services.credit_card_statement_service.extract_text_from_pdf_bytes",
            return_value="no transaction-shaped lines here at all",
        ):
            with pytest.raises(ValueError, match="Supported banks"):
                await build_credit_card_statement_payload(
                    "statement.pdf",
                    b"%PDF-fake",
                    pdf_password=None,
                    issuer="HDFC Bank",
                    conn=conn,
                )
