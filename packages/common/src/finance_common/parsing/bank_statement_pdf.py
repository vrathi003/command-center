"""PDF bank statements: PyMuPDF + heuristic lines first; LM Studio only if no rows match."""

from __future__ import annotations

import json
import re
from typing import Any

import fitz  # type: ignore[import-untyped]
from openai import AsyncOpenAI

from finance_common.config import AppSettings
from finance_common.parsing.bank_statement_text_heuristic import (
    count_transaction_like_lines,
    heuristic_rows_from_statement_text,
)
from finance_common.parsing.transaction_import import extract_merchant_from_narration
from finance_common.parsing.llm_openai_compat import async_openai_for_lm_studio
from finance_common.types import Category, PaymentMode

MAX_PDF_PAGES = 50
MAX_PDF_BYTES = 10 * 1024 * 1024
CHUNK_MAX_CHARS = 12_000
CHUNK_OVERLAP = 500
MAX_LLM_TX_ROWS_PER_CHUNK = 500
MAX_BANK_STATEMENT_IMPORT_ROWS = 5000


class BankStatementPdfError(Exception):
    """Raised when a PDF cannot be parsed or LM Studio is unavailable."""


def _category_list_for_prompt() -> str:
    return ", ".join(f'"{m.value}"' for m in Category)


def _payment_mode_list_for_prompt() -> str:
    return ", ".join(f'"{m.value}"' for m in PaymentMode)


_SYSTEM_PROMPT = (
    "You extract posted transactions from Indian bank or credit card statement text. "
    "You MUST reply with exactly one JSON object and nothing else: no reasoning, no "
    "\"Thinking Process\", no markdown, no bullet analysis, no text before or after the JSON. "
    "The first character of your reply must be { and the last must be }. "
    "Never invent rows not present in the statement text."
)


def _user_prompt_for_chunk(chunk: str) -> str:
    return f"""Extract posted transactions and EMI line items for the **current billing cycle only**
(as stated in the statement header, e.g. statement period / billing dates). Ignore previous
cycles, opening balances, reward summaries, and marketing.

Include:
- Card/account purchases, payments, refunds, fees, interest, cash advances (real postings).
- EMI debits/credits that appear as line items in the transaction list.

Exclude:
- Terms, privacy, annexures, ads, duplicate pages, non-ledger content.
- Stand-alone EMI amortisation tables (not the same as posted txn lines).

Output exactly one JSON object with this shape (nothing else):
{{"transactions":[{{...}}, ...]}}

Each transaction must have:
- "date": string in YYYY-MM-DD (infer year from context if the fragment only shows day/month)
- "amount_inr": number — strictly positive amount in Indian Rupees (not paise)
- "is_debit": boolean — true if money left the account, false if money came in
- "narration": string — full description as shown (or best reconstruction from wrapped lines)
- "merchant": string or null — short payee/counterparty **only** (see UPI rules below), else null
- "category": one of: {_category_list_for_prompt()}
- "payment_mode": one of: {_payment_mode_list_for_prompt()}
- "notes": string or null — extra context if needed, else null

Rules:
- Debit card / ATM / POS → pick closest Debit Card or Other; category from merchant.
- UPI / HDFC-style lines: the payee is usually the segment **after** the UPI reference number, e.g.
  ``UPI/DR/102786697305/APPLE ME/HDFC/...`` → merchant ``APPLE ME``; ``UPI/DR/.../SURAJ KU`` → ``SURAJ KU``.
  Do not put the full narration into "merchant"; put the full line in "narration" only.
- Standalone merchant names (e.g. CREDITSAISON) may appear without UPI slashes — use them as merchant as-is.
- UPI → payment_mode UPI when the text mentions UPI.
- NEFT/IMPS/RTGS → NEFT/IMPS or Bank Transfer as appropriate.
- Salary, interest credit → often Income; internal transfers → Transfer; SIP/MF → Investments.
- EMI line items: use EMI Loan Repayment when clearly an EMI debit; else Other.
- Skip non-transaction noise (GST/TDS summary blocks without a clear date+amount line).

Statement fragment:
---
{chunk}
---
"""


_PAGE_HEADER = re.compile(r"(?m)^--- Page (\d+) ---\s*\n")
_BOILERPLATE_TAIL = re.compile(
    r"terms\s+and\s+conditions|privacy\s+policy|grievance\s+redressal|regulatory\s+disclosure|"
    r"important\s+information|customer\s+care|annexure|disclaimer|mandatory\s+reporting|"
    r"fatca|kyc\s+policy|reward\s+points?\s+summary",
    re.IGNORECASE,
)


def filter_trailing_boilerplate_pages(text: str) -> str:
    """Drop trailing PDF pages that look like T&C, annexures, or junk (no txn-like lines)."""
    matches = list(_PAGE_HEADER.finditer(text))
    if len(matches) < 2:
        return text

    pages: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        pages.append((int(m.group(1)), text[start:end]))

    while len(pages) > 1:
        _num, body = pages[-1]
        txn_lines = count_transaction_like_lines(body)
        boiler_hits = len(_BOILERPLATE_TAIL.findall(body))
        short = len(body.strip()) < 120
        if txn_lines == 0 and (boiler_hits >= 1 or short):
            pages.pop()
        else:
            break

    return "".join(f"--- Page {num} ---\n{body}" for num, body in pages)


def extract_text_from_pdf_bytes(pdf_bytes: bytes, password: str | None = None) -> str:
    """Extract plain text from a PDF using PyMuPDF (local).

    If the PDF is encrypted with an open password, pass ``password`` (or you get a clear error).
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise BankStatementPdfError(
            f"unreadable PDF (wrong format or invalid): {e}",
        ) from e
    try:
        if doc.needs_pass:
            if password is None:
                raise BankStatementPdfError(
                    "PDF is password-protected — provide pdf_password when uploading",
                )
            if not doc.authenticate(password):
                raise BankStatementPdfError("incorrect PDF password")

        if doc.page_count > MAX_PDF_PAGES:
            msg = f"PDF has too many pages (max {MAX_PDF_PAGES})"
            raise BankStatementPdfError(msg)
        parts: list[str] = []
        for i in range(doc.page_count):
            page = doc[i]
            parts.append(f"--- Page {i + 1} ---\n{page.get_text()}")
        return "\n".join(parts)
    finally:
        doc.close()


def chunk_statement_text(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split long text into overlapping chunks for LLM context limits."""
    t = text.strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]
    chunks: list[str] = []
    start = 0
    while start < len(t):
        end = min(start + max_chars, len(t))
        chunks.append(t[start:end])
        if end >= len(t):
            break
        start = max(0, end - overlap)
    return chunks


def _first_json_object_dict(text: str) -> dict[str, Any] | None:
    """Find the first syntactically valid JSON object in a string (handles trailing prose)."""
    decoder = json.JSONDecoder()
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            return obj
        i = end if end > i else i + 1
    return None


def _strip_to_transactions_json_start(text: str) -> str:
    """Drop reasoning text before the JSON object that contains a ``transactions`` array."""
    key = '"transactions"'
    idx = text.find(key)
    if idx == -1:
        return text
    brace = text.rfind("{", 0, idx)
    if brace == -1:
        return text
    return text[brace:]


def _first_dict_with_transactions_key(text: str) -> dict[str, Any] | None:
    """Find a JSON object that contains a ``transactions`` key."""
    decoder = json.JSONDecoder()
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict) and "transactions" in obj:
            return obj
        i = end if end > i else i + 1
    return None


def parse_json_object_from_model_text(raw: str) -> dict[str, Any]:
    """Parse JSON from model output: tolerates markdown fences, preamble text, and smart quotes."""
    if not raw or not str(raw).strip():
        msg = "empty model output"
        raise ValueError(msg)

    t = str(raw).strip()
    t = t.replace("\ufeff", "")
    # Smart quotes → ASCII (common in LLM output)
    t = t.translate(
        str.maketrans(
            {
                "\u201c": '"',
                "\u201d": '"',
                "\u2018": "'",
                "\u2019": "'",
            },
        ),
    )
    # Full ```json ... ``` blocks
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()

    t = re.sub(r"^\s*```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```\s*$", "", t).strip()

    # Qwen / chat models often prepend "Thinking Process:" — real JSON starts at {"transactions"
    t = _strip_to_transactions_json_start(t)

    try:
        data = json.loads(t)
        if isinstance(data, dict) and "transactions" in data:
            return data
    except json.JSONDecodeError:
        pass

    found = _first_dict_with_transactions_key(t)
    if found is not None:
        return found

    found = _first_json_object_dict(t)
    if found is not None and "transactions" in found:
        return found

    brace = t.find("{")
    if brace >= 0:
        tail = t[brace:]
        tail = _strip_to_transactions_json_start(tail)
        found = _first_dict_with_transactions_key(tail)
        if found is not None:
            return found
        found = _first_json_object_dict(tail)
        if found is not None and "transactions" in found:
            return found
        try:
            data = json.loads(tail)
            if isinstance(data, dict) and "transactions" in data:
                return data
        except json.JSONDecodeError:
            pass

    msg = (
        "could not parse JSON with a \"transactions\" key — model may have output reasoning only. "
        f"First 200 chars: {t[:200]!r}"
    )
    raise ValueError(msg)


def _coerce_amount_str(v: Any) -> str:
    if isinstance(v, bool) or v is None:
        raise ValueError("invalid amount")
    if isinstance(v, (int, float)):
        if v <= 0:
            raise ValueError("amount must be positive")
        return f"{float(v):.2f}"
    s = str(v).strip().replace(",", "").replace("₹", "")
    if not s:
        raise ValueError("empty amount")
    x = float(s)
    if x <= 0:
        raise ValueError("amount must be positive")
    return f"{x:.2f}"


def _coerce_date_str(v: Any) -> str:
    if v is None:
        raise ValueError("missing date")
    s = str(v).strip()[:10]
    if len(s) < 10 or s[4] != "-" or s[7] != "-":
        raise ValueError(f"date must be YYYY-MM-DD, got {v!r}")
    return s


def normalize_llm_transaction_row(obj: dict[str, Any]) -> dict[str, str]:
    """Map one LLM transaction object to CSV keys for `row_dict_to_canonical`."""
    date_s = _coerce_date_str(obj.get("date"))
    amount_s = _coerce_amount_str(obj.get("amount_inr"))
    cat_raw = obj.get("category", "Other")
    pm_raw = obj.get("payment_mode", "Other")
    cat = Category.from_string(str(cat_raw))
    pm = PaymentMode.from_string(str(pm_raw))
    narration = (obj.get("narration") or "").strip()
    merchant = obj.get("merchant")
    merchant_s = str(merchant).strip() if merchant not in (None, "") else ""
    if not merchant_s and narration:
        merchant_s = narration[:200]

    if narration and re.search(r"UPI/(?:DR|CR)/", narration, re.I):
        slim = extract_merchant_from_narration(narration)
        if slim:
            merchant_s = slim[:200]
    elif merchant_s:
        slim = extract_merchant_from_narration(merchant_s)
        if slim:
            merchant_s = slim[:200]
    notes_s = ""
    raw_notes = obj.get("notes")
    if raw_notes not in (None, ""):
        notes_s = str(raw_notes).strip()[:2000]
    elif narration and narration.strip() != merchant_s:
        notes_s = narration[:2000]

    row: dict[str, str] = {
        "date": date_s,
        "amount": amount_s,
        "category": cat.value,
        "payment_mode": pm.value,
    }
    if merchant_s:
        row["merchant"] = merchant_s
    if notes_s:
        row["notes"] = notes_s[:2000]
    return row


def dedupe_import_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove duplicates from overlapping chunks (date + amount + merchant)."""
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, str]] = []
    for r in rows:
        key = (
            r.get("date", "").strip(),
            r.get("amount", "").strip(),
            (r.get("merchant") or r.get("notes") or "")[:120].strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


async def _call_llm_for_chunk(
    client: AsyncOpenAI,
    model: str,
    chunk: str,
) -> list[dict[str, Any]]:
    user = _user_prompt_for_chunk(chunk)
    msg_kw: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }
    # LM Studio often ignores or mishandles OpenAI's response_format; plain completion + robust
    # JSON parsing is more reliable than relying on structured output.
    try:
        resp = await client.chat.completions.create(**msg_kw)
    except Exception as e:
        raise BankStatementPdfError(f"LM Studio request failed: {e}") from e
    choice = resp.choices[0].message.content
    if not choice:
        raise BankStatementPdfError("empty response from LM Studio")
    try:
        data = parse_json_object_from_model_text(choice)
    except ValueError as e:
        raise BankStatementPdfError(
            f"Model output was not valid JSON ({e}). "
            "In LM Studio, prefer a model preset without long chain-of-thought, or disable "
            "\"reasoning\" / thinking output so the reply is only `{{\"transactions\":[...]}}`.",
        ) from e
    txs = data.get("transactions")
    if txs is None:
        raise BankStatementPdfError("JSON missing 'transactions' array")
    if not isinstance(txs, list):
        raise BankStatementPdfError("'transactions' must be an array")
    out: list[dict[str, Any]] = []
    for item in txs[:MAX_LLM_TX_ROWS_PER_CHUNK]:
        if isinstance(item, dict):
            out.append(item)
    return out


async def statement_text_to_import_rows(
    text: str,
    settings: AppSettings,
    *,
    client: AsyncOpenAI | None = None,
) -> list[dict[str, str]]:
    """Plain text from a PDF (or similar) → import rows. Heuristic first; LM Studio if no rows."""
    if not text.strip():
        raise BankStatementPdfError(
            "no text extracted from PDF — image-only statements need OCR (unsupported)",
        )

    text = filter_trailing_boilerplate_pages(text)

    heuristic = heuristic_rows_from_statement_text(text)
    if heuristic:
        return dedupe_import_rows(heuristic)[:MAX_BANK_STATEMENT_IMPORT_ROWS]

    if not settings.lm_studio_url:
        raise BankStatementPdfError(
            "Could not parse transaction lines from extracted text. "
            "Set LM_STUDIO_URL for local LM Studio on this PDF, or export CSV from your bank.",
        )

    chunks = chunk_statement_text(text)
    if not chunks:
        raise BankStatementPdfError("empty statement after extraction")

    own_client = client is None
    try:
        ac = client or async_openai_for_lm_studio(settings)
    except ValueError as e:
        raise BankStatementPdfError(str(e)) from e
    try:
        raw_rows: list[dict[str, str]] = []
        for ch in chunks:
            objs = await _call_llm_for_chunk(ac, settings.lm_studio_model, ch)
            for o in objs:
                try:
                    raw_rows.append(normalize_llm_transaction_row(o))
                except (ValueError, TypeError, KeyError):
                    continue
        return dedupe_import_rows(raw_rows)[:MAX_BANK_STATEMENT_IMPORT_ROWS]
    finally:
        if own_client:
            await ac.close()


async def pdf_bytes_to_import_rows(
    pdf_bytes: bytes,
    settings: AppSettings,
    *,
    password: str | None = None,
    client: AsyncOpenAI | None = None,
) -> list[dict[str, str]]:
    """PDF bytes → import rows. Heuristic parsing first; LM Studio only if no rows match."""
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise BankStatementPdfError(f"PDF file too large (max {MAX_PDF_BYTES // (1024 * 1024)} MB)")
    text = extract_text_from_pdf_bytes(pdf_bytes, password=password)
    return await statement_text_to_import_rows(text, settings, client=client)
