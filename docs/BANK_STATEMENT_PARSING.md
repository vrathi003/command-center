# Bank statement PDF parsing

This project can turn **PDF bank statements** into rows compatible with transaction import (same shape as CSV/Excel import). Everything runs **locally** on your machine: text extraction uses **PyMuPDF**; optional structuring uses **LM Studio** (OpenAI-compatible local server) only when simpler parsing does not produce rows.

## What was implemented

| Area | What it does |
|------|----------------|
| **PDF text extraction** | [PyMuPDF](https://pymupdf.readthedocs.io/) (`fitz`) reads text from each page (max 50 pages, max 10 MB). |
| **Heuristic line parsing** | If extracted text contains lines that look like `YYYY-MM-DD … amount …` or `DD/MM/YYYY … amount …` (optional `Dr`/`Cr`), rows are built **without any LLM**. Category and payment mode are inferred from keywords (UPI, NEFT, salary, etc.). |
| **LM Studio fallback** | If heuristics find **no** rows, the pipeline calls your local **LM Studio** server (`LM_STUDIO_URL`) to return JSON with a `transactions` array. Prompts ask for **current billing cycle** postings only (plus EMI line items in the ledger), and to ignore T&C, annexures, and non-ledger pages. **Temperature 0** for stability. |
| **JSON parsing** | Some chat models prepend “Thinking Process” or reasoning before JSON. The app finds the JSON object that contains `"transactions"` (skips prose) and parses it with `json.JSONDecoder.raw_decode`. If you still see parse errors, use an LM Studio preset **without** long chain-of-thought, or disable reasoning output so the reply is only `{"transactions":[...]}`. |
| **Trailing pages** | After extraction, **trailing** pages are dropped when they have **no** transaction-like lines and match boilerplate (e.g. terms and conditions, privacy, annexure) or are very short — so junk pages at the end are not sent to the model. |
| **Cloud blocking** | The OpenAI-compatible HTTP client **refuses** `api.openai.com`, `api.anthropic.com`, and Azure OpenAI hosts — only your configured local base URL is used for the LLM step. |
| **Password-protected PDFs** | After opening the PDF, PyMuPDF’s `authenticate()` is used when `needs_pass` is true. You must supply a password via the dashboard, API form field, or CLI flag. |
| **API** | `POST /api/transactions/import` accepts `.pdf` like CSV/XLSX; optional form field `pdf_password` for encrypted files. |
| **Dashboard** | Transactions page: optional **PDF password** field (enter before choosing the file if the PDF is encrypted), file input accepts PDF. |
| **CLI** | `scripts/bank_statement_pdf_to_csv.py` writes a CSV you can inspect or re-import. |
| **Makefile** | `make pdf-to-csv` wraps the CLI; optional `PASS=…` forwards `-p` for encrypted PDFs. |

### Code locations

| Piece | Path |
|-------|------|
| Extraction, heuristic vs LLM orchestration | `packages/common/src/finance_common/parsing/bank_statement_pdf.py` |
| Heuristic line parser (no network) | `packages/common/src/finance_common/parsing/bank_statement_text_heuristic.py` |
| LM Studio client (host allowlist / blocking) | `packages/common/src/finance_common/parsing/llm_openai_compat.py` |
| Shared import column mapping | `packages/common/src/finance_common/parsing/transaction_import.py` |
| API route | `packages/api/src/finance_api/routers/transactions.py` |
| CLI | `scripts/bank_statement_pdf_to_csv.py` |
| Tests | `tests/test_bank_statement_pdf.py`, `tests/test_bank_statement_text_heuristic.py`, `tests/test_bank_statement_pdf_password.py`, `tests/test_llm_openai_compat.py` |

### Environment variables

| Variable | Role |
|----------|------|
| `LM_STUDIO_URL` | Base URL for the local server (e.g. `http://127.0.0.1:1234/v1`). **Only needed** when heuristic parsing finds zero rows. |
| `LM_STUDIO_MODEL` | Model id as exposed by LM Studio (e.g. `qwen/qwen3.5-9b`). |

See root `.env.example` for placeholders. Copy to `.env` and start LM Studio with the model loaded before relying on the LLM fallback.

## How to run

### 1. Dashboard (recommended for import into the app)

1. Start the API (`uv run python start.py` or `make dev`) and the dashboard (`make dev-dashboard` or `npm run dev` in `dashboard/`).
2. Open **Transactions**.
3. If the PDF is **encrypted**, type the password in **PDF password (if encrypted)** first, then choose the file (the password is sent only to your API with the upload).
4. For **unencrypted** PDFs, leave the password blank and choose the file.

Imports use the same pipeline as CSV: rows must still satisfy `parse_import_row` (date, amount, category, etc.) after normalization.

### 2. CLI (standalone CSV; no API required)

From the repo root (with `uv sync` already run):

```bash
uv run python scripts/bank_statement_pdf_to_csv.py /path/to/statement.pdf -o /path/to/out.csv
```

Encrypted PDF:

```bash
uv run python scripts/bank_statement_pdf_to_csv.py /path/to/statement.pdf -o /path/to/out.csv -p 'your-pdf-password'
```

If heuristics fail and you need LM Studio, ensure `.env` has `LM_STUDIO_URL` and `LM_STUDIO_MODEL`, and LM Studio is running.

### 3. Makefile

```bash
make pdf-to-csv PDF=~/Downloads/statement.pdf OUT=~/Downloads/out.csv
```

Encrypted PDF:

```bash
make pdf-to-csv PDF=~/Downloads/statement.pdf OUT=~/Downloads/out.csv PASS=your-password
```

### 4. HTTP API (curl / scripts)

```bash
curl -s -X POST "http://127.0.0.1:8000/api/transactions/import" \
  -F "file=@/path/to/statement.pdf" \
  -F "pdf_password=optional-if-encrypted"
```

Non-PDF imports work as before: only `file` is required.

## Behaviour summary

1. **Size / pages** — Rejects files over 10 MB or more than 50 pages (configurable in code).
2. **Text** — If PyMuPDF extracts no text (e.g. scanned image-only PDF), you get a clear error; **OCR is not implemented**.
3. **Heuristics first** — If at least one line matches the heuristic patterns, **no** request is made to LM Studio.
4. **LM fallback** — If heuristics return zero rows and `LM_STUDIO_URL` is unset, the error explains that you must set LM Studio or export CSV from the bank.
5. **Password** — Wrong password → `incorrect PDF password`; missing password on an encrypted file → message to provide `pdf_password` / `-p`.
6. **Trailing pages** — Non-transaction tail pages (T&C, etc.) are removed before heuristics/LLM when page markers (`--- Page N ---`) are present.
7. **LLM content** — The model is instructed to output **only** JSON (no thinking text) and to restrict to the **current billing period** and real ledger lines (including EMI postings in the list), excluding amortisation tables that are not posted transactions.

## Related docs

- Root [README](../README.md) — Transactions import (CSV/Excel/PDF).
- [SETUP_AND_OPERATIONS.md](SETUP_AND_OPERATIONS.md) — Scheduler, backups, other API operations.
