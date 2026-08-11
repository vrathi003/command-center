# Wealth Income Ledger Alignment (W3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Record income (prefilled from income streams) via `build_bank_income`, and drive savings rate from ledger income credits.

**Architecture:** Optional `default_account_id` + `category` on `income_sources`. `POST /income/{id}/record-income` posts bank income. Dashboard Income page CTA. Dashboard savings rate uses ledger income credits when double_entry.

**Tech Stack:** aiosqlite, FastAPI, pytest, `build_bank_income`.

**Spec:** `docs/superpowers/specs/2026-08-11-wealth-stack-ledger-alignment-design.md` §7

**Status:** ✅ Complete (2026-08-11). Goals linking deferred to W4.

## Global Constraints

- Streams remain planning metadata; no auto-post on payday.
- Tax 80C/regime stay settings.
- TDD; commit per task; no unrelated `uv.lock`.
- Do not implement Goals linking (W4).

## File map

| Path | Role |
|------|------|
| schema + migrations | `default_account_id`, `category` on income_sources |
| repositories/income_sources.py | fields |
| services/income_ledger.py (new) | record income helper |
| routers/income.py | record-income endpoint |
| dashboard_service.py | savings rate from ledger |
| IncomeTaxPage.tsx | Record income UI |
| tests/test_income_ledger_w3.py | coverage |

---

### Task 1: Schema + repo + API fields

- Add nullable `default_account_id`, `category` to income_sources
- Wire CRUD schemas/router
- [x] Commit `feat(income): default_account_id and category columns`

---

### Task 2: Record income API

```python
async def post_income_credit(conn, *, source, payment_date, amount_paise=None, account_id=None, category=None) -> tuple[int, IncomeSourceRow]:
```

- Require double_entry
- Bank = override or default_account_id; amount = override or source.amount_paise
- Category = override or source.category or "Salary"
- Income account = system Uncategorized Income (mirror Uncategorized Expense helper)
- `build_bank_income` + LedgerService.post; merchant=source.name
- [x] Tests; commit `feat(income): record-income ledger post`

---

### Task 3: Savings rate from ledger income

- When double_entry, dashboard summary savings rate numerator/denominator uses ledger income credits in period (query postings on income accounts or credit-normal income class)
- Else keep income_sources monthly equivalent
- [x] Test; commit `feat(dashboard): savings rate from ledger income credits`

---

### Task 4: Dashboard Record income

- API client + IncomeTaxPage modal (date, bank, amount, category prefilled)
- Optional default bank/category on create/edit
- [x] Build PASS; commit `feat(dashboard): record income from streams`

---

### Task 5: Acceptance

- Full pytest + check-ledger-writes
- Mark W3 ✅ on umbrella; note Goals W4 later; package W1–W3 done for wealth money paths
- [x] Commit `docs(wealth): mark income ledger W3 complete`

---

## Self-review vs §7

| Spec | Task |
|------|------|
| schema optional fields | 1 |
| Record income | 2 |
| Savings rate | 3 |
| UI | 4 |
| Acceptance | 5 |
