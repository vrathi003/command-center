# Schema

Defined in ``packages/common/src/finance_common/db/schema.sql``.

## ``ledger_transactions``

| Column | Notes |
|--------|-------|
| ``id`` | PK |
| ``date`` | ISO ``YYYY-MM-DD`` |
| ``payee`` / ``notes`` / ``tags`` | Optional text |
| ``source`` | e.g. ``manual``, ``discord``, ``email``, ``import``, product-specific |
| ``status`` | ``posted`` \| ``void`` |
| ``external_key`` | Optional unique key for idempotency (partial unique index) |
| ``created_at`` / ``updated_at`` | UTC datetime strings |

## ``ledger_postings``

| Column | Notes |
|--------|-------|
| ``id`` | PK |
| ``transaction_id`` | FK → ``ledger_transactions`` |
| ``account_id`` | FK → ``accounts`` |
| ``amount_paise`` | Signed, ``CHECK != 0`` |
| ``category`` | Required for expense/income classes at post time |
| ``reconciled_statement_line_id`` | Optional recon link |

## Account classes that matter

Accounts carry ``account_class`` (not only UI ``type``). Planner and balance logic key off class:

| Class pattern | Examples |
|---------------|----------|
| ``asset_cash`` | Bank, wallet |
| ``asset_investment`` | Brokerage / MF cost accounts |
| ``liability_cc`` | Credit cards |
| ``liability_loan`` | Loans |
| ``expense`` / ``income`` | P&L (system + category accounts) |
| ``equity_*`` | Opening balance equity, etc. |

## Related tables (not the books, but attached)

| Table | Role |
|-------|------|
| ``intake_candidates`` | Quarantine / review before post |
| ``email_transaction_staging`` | Gmail review desk |
| ``recon_*`` | Statement control book |
| ``alert_notifications`` / ``domain_events`` | Ops + domain alerts |

## Amounts and dates

- Store money as **paise** (int). Display ÷ 100.
- Dates are calendar ISO strings (no timezone math in the ledger layer).
