"""Credit-card statement PDF unlock + text extraction (CardQL-compatible).

CardQL uses pikepdf to decrypt and pypdf to extract text. PyMuPDF produces
different line breaks on many Indian bank CC statements, which breaks the
regex-based bank parsers (especially ICICI serial-number lines).
"""

from __future__ import annotations

import io

import pikepdf
from pypdf import PdfReader

from finance_common.parsing.bank_statement_pdf import BankStatementPdfError, MAX_PDF_BYTES, MAX_PDF_PAGES


def unlock_pdf_bytes(data: bytes, password: str | None) -> tuple[bytes, bool]:
    """Decrypt PDF if needed; return bytes suitable for pypdf text extraction."""

    def _try(pwd: str | None) -> bytes | None:
        try:
            pdf = pikepdf.open(io.BytesIO(data), password=pwd or "")
            buf = io.BytesIO()
            pdf.save(buf)
            pdf.close()
            return buf.getvalue()
        except Exception:
            return None

    if password:
        result = _try(password)
        if result is not None:
            return result, True
        raise BankStatementPdfError("incorrect PDF password")

    result = _try(None)
    if result is not None:
        return result, True

    # Encrypted but no password supplied — pypdf cannot read the raw bytes.
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise BankStatementPdfError(
                "PDF is password-protected — provide pdf_password when uploading",
            )
    except BankStatementPdfError:
        raise
    except Exception:
        pass

    return data, False


def extract_credit_card_pdf_text(pdf_bytes: bytes, password: str | None = None) -> str:
    """Unlock (if needed) and extract plain text using pypdf (matches CardQL)."""
    if len(pdf_bytes) > MAX_PDF_BYTES:
        msg = f"PDF too large (max {MAX_PDF_BYTES // (1024 * 1024)} MB)"
        raise BankStatementPdfError(msg)

    unlocked, _was_unlocked = unlock_pdf_bytes(pdf_bytes, password)

    try:
        reader = PdfReader(io.BytesIO(unlocked))
    except Exception as e:
        raise BankStatementPdfError(f"unreadable PDF: {e}") from e

    if len(reader.pages) > MAX_PDF_PAGES:
        msg = f"PDF has too many pages (max {MAX_PDF_PAGES})"
        raise BankStatementPdfError(msg)

    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts)
