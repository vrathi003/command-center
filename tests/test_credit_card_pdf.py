"""Credit-card PDF text extraction tests."""

from __future__ import annotations

import pytest

from finance_common.parsing.bank_parsers import icici_v1
from finance_common.parsing.credit_card_pdf import extract_credit_card_pdf_text
from finance_common.parsing.bank_statement_pdf import BankStatementPdfError


def test_icici_parser_works_on_pypdf_style_text() -> None:
    """Sanity: sample ICICI layout still parses when line breaks match CardQL."""
    text = (
        "Date SerNo Amount (in`)\n"
        "15/01/2026 12702848045 REPOVIVE, INC. COLLEGE PARK US 18 940.19\n"
        "29/01/2026 12776056934 BBPS Payment received 0 1,160.54 CR\n"
    )
    rows = icici_v1.parse(text)
    assert len(rows) == 2


def test_extract_rejects_oversized_pdf() -> None:
    with pytest.raises(BankStatementPdfError, match="too large"):
        extract_credit_card_pdf_text(b"x" * (11 * 1024 * 1024))
