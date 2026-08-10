# Double-Entry Money Engine P4 — Reconciliation Design

**Date:** 2026-08-10  
**Status:** Approved for implementation planning  
**Owner:** Vaibhav  
**Parent spec:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md` §7.5  
**Depends on:** P1–P3 (ledger + intake + cutover)

---

## 1. Goal

Ship a **control book**: per cash/CC account and statement period, import statement lines into a dedicated recon store, suggest matches to ledger transactions, let the user confirm/ignore/adjust, and **soft-close** the period when the books agree.

Recon never silently rewrites the ledger.

## 2. Locked decisions

| Topic | Choice |
|-------|--------|
| Primary UX | Account + period workspace |
| Statement storage | Dedicated `recon_statements` / `recon_statement_lines` (not intake dual-use) |
| Matching | Suggest + user confirm (no silent auto-apply) |
| Period close | Soft close (reversible); blocked unless balanced + all lines matched\|ignored |
| Architecture | `finance_common.recon` + API + dashboard page |
| Adjustments | Explicit → `ledger.service.post`, then match |

## 3. Data model

### 3.1 `recon_statements`

| Column | Notes |
|--------|--------|
| id | PK |
| account_id | FK → accounts (asset_cash or liability_cc) |
| period_start / period_end | ISO dates inclusive |
| opening_balance_paise | Statement opening |
| closing_balance_paise | Statement closing |
| status | `open` \| `reconciled` |
| source | e.g. `upload`, `manual` |
| filename | optional |
| created_at / updated_at | |

Unique-ish: one open statement per (account_id, period_start, period_end) preferred; allow reopen after soft-close.

### 3.2 `recon_statement_lines`

| Column | Notes |
|--------|--------|
| id | PK |
| statement_id | FK |
| tx_date | |
| amount_paise | positive |
| direction | `in` \| `out` |
| payee / narration | |
| external_key | optional fingerprint for idempotent re-import |
| status | `unmatched` \| `matched` \| `ignored` |
| ignore_reason | optional |

### 3.3 `recon_matches`

| Column | Notes |
|--------|--------|
| id | PK |
| line_id | FK unique (one match per line) |
| ledger_transaction_id | FK → ledger_transactions |
| method | `suggested` \| `manual` |
| confirmed_at | |

Matching targets a **ledger transaction** that has a posting on the statement’s account (not an arbitrary posting orphan).

Optional later: `reconciled_statement_line_id` on ledger header — **out of P4** unless needed for queries; prefer join via `recon_matches`.

## 4. ReconciliationService

Package: `finance_common.recon`

| Method | Behavior |
|--------|----------|
| `import_statement` | Parse CSV/XLSX/PDF via existing parsers → insert statement + lines. No ledger writes. Idempotent on line `external_key` within statement. |
| `suggest_matches` | For unmatched lines, propose ledger txs on same account: amount equal, date ± `project_config` window (default 1–2 days), payee prefix match. Return ranked proposals; do not persist until confirm. |
| `confirm_match` | Persist `recon_matches`; set line status `matched`. Reject if statement reconciled or line already matched. |
| `unmatch` | Remove match; line → `unmatched`. Blocked if statement reconciled (must reopen). |
| `ignore_line` | Line → `ignored` + reason. |
| `period_status` | Ledger balance of account as-of `period_end` vs `closing_balance_paise`; counts unmatched lines / unmatched ledger activity in period. |
| `soft_close` | Require: all lines matched\|ignored AND ledger as-of closing equals statement closing. Set status `reconciled`. |
| `reopen` | Status → `open`. |
| `create_adjustment` | Build + `ledger.service.post` (e.g. bank charge / interest) for the account, then confirm_match to the line. |

Domain event (outbox only, no AlertService delivery): `recon.period_mismatched` / `recon.period_reconciled` optional for P5.

## 5. API

Prefix `/api/recon`

- `GET /statements?account_id=`
- `POST /statements` metadata or multipart import
- `GET /statements/{id}` workspace DTO
- `POST /statements/{id}/suggest`
- `POST /statements/{id}/lines/{line_id}/confirm` `{ ledger_transaction_id }`
- `POST /statements/{id}/lines/{line_id}/unmatch`
- `POST /statements/{id}/lines/{line_id}/ignore` `{ reason? }`
- `POST /statements/{id}/adjust` → ledger post + match
- `POST /statements/{id}/soft-close`
- `POST /statements/{id}/reopen`

Ledger write routes use `require_ledger_writes`. Import does not.

## 6. Dashboard UX

Route e.g. `/reconciliation` (nav near Accounts / Transactions).

1. Account picker → statement list (period, status, closing vs ledger delta)
2. Workspace:
   - Left: statement lines (status badges)
   - Center/right: suggestions + unmatched ledger txs in period
   - Actions: Confirm, Manual match, Ignore, Adjust
3. Footer: statement closing, ledger as-of, unmatched counts; Soft close enabled only when green
4. Empty states for no statements / all matched

Keep visual language consistent with existing pages (PageHero, Panel, TanStack Query).

## 7. Config

Reuse or add:

- `project_config.recon.match.date_window_days` (default `2`)
- Optional min payee prefix length (code constant ok)

## 8. Testing

1. Import statement → N lines, zero ledger side effects  
2. Suggest finds unique amount/date match; confirm persists  
3. Soft-close blocked when unmatched line or balance mismatch  
4. Soft-close succeeds when matched + balances equal; reopen allows unmatch  
5. Adjust posts via LedgerService and matches line  
6. CI: still ban INSERT into `ledger_*` outside ledger package  

## 9. Acceptance

- Import a bank CSV for SBI Personal for a known month  
- Suggest/confirm most lines  
- Soft-close when closing matches  
- Reopen works  

## 10. Non-goals (P4)

- P5 AlertService delivery of recon events  
- P6 wealth/EMI polish  
- Hard-locked periods  
- Auto-apply matches without confirm  
- Using intake_candidates as the recon store  
- Statement closing as a parallel balance UI on Accounts page  

---

## Spec self-review

- No TBD placeholders.  
- Aligns with parent §7.5 (control book; no silent rewrite).  
- Scope is one phase.  
- Soft-close gates and suggest-only matching made explicit.
