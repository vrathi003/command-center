# Double-Entry Money Engine P3 — Migration & Cutover Design

**Date:** 2026-08-10  
**Status:** Approved for implementation planning  
**Owner:** Vaibhav  
**Parent spec:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md` §9  
**Depends on:** P1 (ledger) + P2 (intake) — both shipped

---

## 1. Goal

Convert existing SQLite history into the double-entry ledger, quarantine unclean rows, then **fully cut over** product reads/writes so the legacy `transactions` table is archive-only.

## 2. Locked decisions

| Topic | Choice |
|-------|--------|
| Cutover | **Full** — Transactions UI + writers use ledger; legacy archived read-only |
| Soft-deleted rows | **Skip / archive only** — no ledger posts |
| Opening balances | **Quarantine `needs_opening_balance`** per cash/CC account; do not invent amounts |
| Run path | **Explicit dry-run → apply** via API and CLI (shared service) |
| Posting path | **`ledger.service.post` only** (no bulk SQL into `ledger_*`) |
| Quarantine store | Reuse `intake_candidates` with migration reasons |
| Rollback | Restore pre-apply DB backup file; no in-place un-migrate |

## 3. Live DB snapshot (pre-migrate, 2026-08-10)

| Metric | Count |
|--------|------:|
| Active legacy rows | 1,847 |
| Soft-deleted | 4,700 |
| Active with `account_id` | 42 |
| Active missing `account_id` but text `SBI Personal` | 1,805 |
| Transfer pairs (distinct) | 3 |
| Orphan transfer legs | 0 |
| Posted ledger txs | 0 |

Name resolution for `SBI Personal` → account id `1` (`asset_cash`) is expected to cover nearly all active rows.

## 4. Migration engine

### 4.1 Safety (M0)

1. Before **apply**: copy DB file next to original (timestamped) and record SHA-256 in the run report / `settings`.
2. Refuse apply if backup or checksum fails.
3. Idempotent / resumable via `external_key`:
   - Single debit/credit: `legacy:txn:{old_id}`
   - Transfer pair: `legacy:pair:{transfer_pair_id}` (one ledger tx for both legs)
4. Dry-run shares the same planner as apply but writes nothing (except optional report-only settings if needed — prefer return JSON only).

### 4.2 Chart of accounts (M1)

- Rely on P1 `account_class` backfill + system accounts (`Opening Balance Equity`, `Uncategorized Expense`, `Uncategorized Income`, `Suspense`).
- Resolve account: prefer `account_id`; else exact match on `accounts.name` = legacy `account` text; else quarantine `legacy_migration:missing_account`.

### 4.3 Row mapping (M2)

| Legacy shape | Action |
|--------------|--------|
| Soft-deleted | Skip (remain in archive) |
| `debit` + resolved account | Dr Uncategorized Expense (category on posting) · Cr account |
| `credit` + resolved account | Dr account · Cr Uncategorized Income (category on posting) |
| Valid transfer pair (exactly 2 active legs, distinct accounts) | One transfer: Dr to · Cr from |
| Orphan / incomplete transfer | Quarantine `legacy_migration:orphan_transfer` + raw snapshot |
| Unresolvable account | Quarantine `legacy_migration:missing_account` |
| Already posted external_key | Noop |

Use existing builders / `plan_postings` / `plan_transfer` patterns. Category from legacy `category` (default Other). Source on ledger header: `legacy_migration`. Payee from `merchant`. Notes from `notes`.

### 4.4 Integrity + opening balance (M3)

After apply history pass:

1. Assert all newly posted txs balance (LedgerService already enforces; boot integrity remains).
2. Report counts: `migrated`, `quarantined`, `skipped_deleted`, `noop`.
3. For each `asset_cash` / `liability_cc` account that has at least one migrated posting: if no prior opening-balance posting exists against `Opening Balance Equity`, create a **pending** intake candidate with reason `needs_opening_balance` (amount null / user-supplied on approve). Do **not** auto-post invented OB.

### 4.5 API / CLI

Shared: `finance_common.migration.legacy_to_ledger`

- `dry_run(conn) -> MigrationReport`
- `apply(conn, *, backup_path: Path) -> MigrationReport`

HTTP (under `/api/migration/`):

- `POST /api/migration/legacy-ledger/dry-run`
- `POST /api/migration/legacy-ledger/apply` (requires `require_ledger_writes`; runs backup then apply)

CLI:

```bash
uv run python scripts/migrate_legacy_to_ledger.py --dry-run
uv run python scripts/migrate_legacy_to_ledger.py --apply
```

## 5. Archive + cutover (M4)

After successful apply:

1. **Archive table:** ensure `legacy_transactions` holds a full copy of pre-cutover `transactions` (including soft-deleted). Preferred sequence:
   - If `legacy_transactions` missing: `CREATE TABLE legacy_transactions AS SELECT * FROM transactions` (or rename + recreate empty stub only if no code path still inserts — prefer **copy** then stop writers).
   - Keep original `transactions` empty or replace writers so new money never lands there; simplest foolproof approach: after copy, leave `transactions` in place but **gate all insert/update/soft-delete paths** when cutover flag is set, and point reads at ledger facade.
2. **Flags** in `project_config` / settings:
   - `project_config.migration.legacy_cutover_at` = ISO timestamp
   - `project_config.migration.legacy_archive` = true
3. **Legacy writers** (`insert_transaction`, transfer pair insert, bulk-delete soft-delete on legacy): return **410** with message to use ledger/intake when cutover is set (also when `ledger_engine=double_entry` post-cutover).
4. **Manual create/edit/delete** on Transactions UI → ledger post / void (compat shapes).
5. **`GET /api/transactions/`** becomes a facade over ledger list, mapping postings → familiar fields (`transaction_type` inferred from cash/CC leg sign, amount positive paise, merchant=payee, category from P&L posting, `account_id` from cash/CC leg).
6. Discord remains off.
7. **Rollback:** restore the backup file taken at apply; do not implement reverse posting migration in P3.

## 6. UI / ops

1. **Settings → Migration panel:** dry-run counts, Apply (confirm), last report, cutover timestamp.
2. **Intake quarantine desk:** filter/badge for `legacy_migration:*` and `needs_opening_balance`; approve OB with amount → post equity ↔ account; reject leaves archive only.
3. **Transactions page:** keep layout; data from facade; banner if quarantine pending after migrate.
4. **Out of scope:** P4 statement recon matching UX; P5 AlertService delivery; auto-invented opening balances.

## 7. Testing

1. Fixture DB with debit/credit/transfer/soft-delete/missing-account → expected migrated/quarantined/skipped counts.
2. Idempotent second apply → all noop; balances unchanged.
3. Golden: after migrate sample, budget lens ≠ cash-flow lens still holds.
4. Cutover: legacy insert → 410; GET transactions returns ledger rows; void removes from facade.
5. Backup file exists after apply (tmp path in tests).

## 8. Acceptance

- Dry-run on live DB shows sensible counts (~1.8k migrate candidates, 0 orphan pairs expected).
- Apply on live (operator-run): backup present; ledger posted ≈ migratable rows; quarantine for OB (+ any unclean).
- Transactions page lists migrated history.
- Re-apply is noop.
- CI: migration tests + `ci_check_ledger_writes.py` green.

## 9. Explicit non-goals (P3)

- P4 ReconciliationService / statement match UI
- P5 AlertService Discord/in-app delivery beyond existing outbox inserts
- P6 EMI split / NW polish
- Dropping `legacy_transactions` in this phase
- Dual-write to legacy + ledger

---

## Spec self-review

- Placeholders: none.
- Consistent with parent §9 and P2 intake quarantine reuse.
- Scope is one phase (migrate + cutover + settings/quarantine UX).
- Ambiguity resolved: soft-delete skip; OB quarantine; dry-run/apply; full cutover via facade + writer gate.
