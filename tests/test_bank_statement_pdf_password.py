"""Password-protected PDF handling (PyMuPDF authenticate)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from finance_common.parsing.bank_statement_pdf import (
    BankStatementPdfError,
    extract_text_from_pdf_bytes,
)


def test_extract_requires_password_when_encrypted() -> None:
    doc = MagicMock()
    doc.needs_pass = True
    doc.page_count = 1
    with (
        patch("finance_common.parsing.bank_statement_pdf.fitz.open", return_value=doc),
        pytest.raises(BankStatementPdfError, match="password-protected"),
    ):
        extract_text_from_pdf_bytes(b"%PDF", password=None)
    doc.close.assert_called_once()


def test_extract_wrong_password() -> None:
    doc = MagicMock()
    doc.needs_pass = True
    doc.authenticate.return_value = False
    doc.page_count = 1
    with (
        patch("finance_common.parsing.bank_statement_pdf.fitz.open", return_value=doc),
        pytest.raises(BankStatementPdfError, match="incorrect PDF password"),
    ):
        extract_text_from_pdf_bytes(b"%PDF", password="wrong")
    doc.authenticate.assert_called_once_with("wrong")
    doc.close.assert_called_once()


def test_extract_success_after_authenticate() -> None:
    doc = MagicMock()
    doc.needs_pass = True
    doc.authenticate.return_value = True
    doc.page_count = 1
    page = MagicMock()
    page.get_text.return_value = "line"
    doc.__getitem__.side_effect = lambda _i: page
    with patch("finance_common.parsing.bank_statement_pdf.fitz.open", return_value=doc):
        out = extract_text_from_pdf_bytes(b"%PDF", password="ok")
    assert "Page 1" in out
    assert "line" in out
    doc.authenticate.assert_called_once_with("ok")
    doc.close.assert_called_once()
