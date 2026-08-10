# Double-Entry Money Engine Redesign

**Date:** 2026-08-10  
**Status:** Draft for implementation planning  
**Owner:** Vaibhav  
**Scope:** Full redesign of money tracking and money movement for Personal Finance OS

---

## 1. Problem statement

The current ledger is a cluster of competing models:

- Positive `amount_paise` plus `transaction_type` (`debit` / `credit` / `transfer`)
- Optional `transfer_pair_id` sibling rows for transfers
- Dual account identity (`account` text vs `account_id`)
- Aggregate filters that disagree (`sum_between` includes credits; `sum_by_account` excludes them; `cc_live_balance` ignores transfer bill pays)
- Import/email paths that invent unpaired “transfers” or drop direction
- Alerts and Discord DMs mixed into domain/background jobs

Result: spend, budgets, CC outstanding, and net worth cannot be trusted. Patching individual bugs will regress again because invariants are policy, not structure.

## 2. Goals and non-goals

### Goals

1. CFO-grade books: one ledger, explicit lenses, dual-books reconciliation
2. Foolproof writes: unbalanced or orphan postings cannot land in `posted` state
3. Email-first automatic intake with quarantine for ambiguity
4. In-place migration of existing SQLite history
5. Clear service boundaries (ledger ≠ intake ≠ recon ≠ alerts)
6. Discord demoted: config-off now; later only as Alert channel and/or Intake adapter

### Non-goals (this redesign)

- Rebuilding Journal, Home Inventory, or Construction modules
- Full tax engine / XIRR / capital-gains calculator (can sit on the new ledger later)
- Shipping Discord write path or Discord alert delivery in Phase 1
- Multi-user / multi-tenant auth redesign

## 3. Product decisions (locked)

| Decision | Choice |
|----------|--------|
| Source of truth | **Dual books** — operational ledger + statement reconciliation as control |
| Capture channels | Email + file import + manual now; Discord behind dead switch |
| CC accounting | **Hybrid** — swipe = budget spend; bill pay = cash-flow only (liability ↓, cash ↓) |
| Email posting | **Auto-post with quarantine** for low confidence / transfers / duplicates |
| Product surface | **Core + wealth stack** (accounts, ledger, budget, CC, investments, debt, goals, income, reports, NW). Park Journal / Home / Construction / Discord runtime on critical path |
| Existing data | **In-place migration** with quarantine for unclean rows |
| Wealth movements (SIP, buys, EMI principal) | **Transfers into wealth/debt accounts**, not lifestyle budget spend |
| Ledger architecture | **True double-entry** (transaction header + balanced postings) |
| Alerts | **Standalone AlertService**; domains emit events only |

## 4. Architecture

### 4.1 Service topology

```
Adapters (IO)                    Domain (pure rules)              Platform
─────────────────                ───────────────────              ────────
Email sync                       LedgerService                    AlertService
File import                      IntakeService                    (standalone)
Manual UI API                    ReconciliationService
CC statement fetch               BudgetService                    Scheduler (triggers
Investment price sync            NetWorthService                    domain jobs only)
Discord bot (OFF)                BalanceService / ReportsService  project_config
Dashboard read APIs              MerchantRules / Classifier
                                 Wealth posting helpers
```

**Hard rules**

1. Domain services never import Discord, SMTP, or push SDKs.
2. Domain services emit domain events to an in-process bus / SQLite outbox.
3. AlertService is the only component that turns events into notifications.
4. Scheduler triggers domain evaluation (e.g. `BudgetService.evaluate_thresholds`); it does not send messages.
5. No adapter (router, bot, import, Gmail) inserts into ledger tables directly — only `LedgerService`.

### 4.2 Package / module intent

| Module | Responsibility |
|--------|----------------|
| `LedgerService` | Create/void/update posted transactions; enforce balance invariants |
| `IntakeService` | Candidate → auto-post / quarantine / reject; dedupe |
| `ReconciliationService` | Statement periods, matching, mismatch queue |
| `BalanceService` | Account balances from postings |
| `ReportsService` | Named lenses (budget spend, cash flow, NW inputs) |
| `BudgetService` | Caps vs budget-spend lens; emit threshold events |
| `AlertService` | Routing, dedupe/cooldown, channels, history — **no ledger math** |
| `MigrationService` | Legacy → double-entry; quarantine unclean rows |

Discord bot package: process not started when `project_config.discord.enabled=false`.

---

## 5. Core ledger model

### 5.1 Chart of accounts

Every balance lives on an **Account** with a type:

| Type | Normal balance | Examples |
|------|----------------|----------|
| `asset_cash` | Debit | Savings, current, wallet |
| `asset_investment` | Debit | Brokerage / MF / stocks buckets |
| `asset_other` | Debit | Real estate / vehicle (optional Assets link) |
| `liability_cc` | Credit | Each credit card |
| `liability_loan` | Credit | Home / personal / car loan |
| `equity` | Credit | Opening-balance equity (system) |
| `income` | Credit | Salary, interest, dividends |
| `expense` | Debit | Food, rent, fees (budget categories) |

System accounts created at migrate/boot: `Opening Balance Equity`, `Uncategorized Expense`, `Uncategorized Income`, `Suspense` (temporary only).

### 5.2 Transaction + postings

**Transaction (header)**

- `id`, `date`, `payee` / merchant, `notes`, `tags`
- `source`: `email` | `import` | `manual` | `system`
- `status`: `posted` | `void`
- `external_key` (dedupe / idempotency)
- timestamps

**Posting (leg)**

- `transaction_id`, `account_id`
- `amount_paise` **signed**: `+` = debit, `−` = credit
- optional `category` (required on expense/income P&L legs)
- optional `reconciled_statement_line_id`

One economic event = one transaction + **N ≥ 2** postings that **sum to zero**.

### 5.3 Canonical posting patterns

| Event | Postings |
|-------|----------|
| Bank UPI to merchant | Dr Expense · Cr Bank |
| Salary | Dr Bank · Cr Income |
| Bank → Bank transfer | Dr Bank B · Cr Bank A |
| CC swipe | Dr Expense · Cr CC liability |
| CC bill pay | Dr CC liability · Cr Bank |
| SIP / MF buy | Dr Investment · Cr Bank |
| EMI | Dr Loan (principal) + Dr Expense (interest) · Cr Bank |
| Opening balance | Dr/Cr Account · Cr/Dr Opening equity |

### 5.4 Ledger invariants (non-negotiable)

1. Posted transaction: ≥ 2 postings; `sum(amount_paise) = 0`
2. Every posting has a real `account_id` (FK)
3. Expense/income legs carry category; balance-sheet transfer legs do not pollute budget categories
4. Void applies to the **whole** transaction (no single-leg delete)
5. Routers/bots/import never raw-insert ledger rows
6. Boot fails closed on write routes if any posted transaction violates sum = 0

### 5.5 Removed from the old model

- `transaction_type` as primary truth
- `transfer_pair_id` sibling hacks
- Dual `account` text vs `account_id` as competing identity
- Spend SQL that forgets to exclude credits
- Unpaired import rows typed as `transfer`
- Special-case `cc_live_balance` that ignores bill-pay transfers

---

## 6. Intake, quarantine, and dedupe

### 6.1 Principle

Parsers never write the ledger. They emit a **Candidate**. `IntakeService` decides: auto-post, quarantine, or reject. Only `LedgerService` posts.

### 6.2 Candidate fields

- `date`, `amount_paise` (absolute), `direction` (in/out relative to suggested account)
- `payee`, `narration`
- `suggested_account_id`, `suggested_counter_account_id`
- `suggested_category`
- `source` (`email` | `import` | `manual`)
- `external_key`, `confidence`, `raw_payload_ref`

### 6.3 Decision rules

**Auto-post** when all are true:

1. `external_key` not already posted/void
2. Suggested account resolved to `account_id`
3. Merchant rule or high-confidence classifier picks category or counter-account type
4. Not flagged as possible transfer / duplicate / split needed
5. Confidence ≥ configured threshold

**Quarantine** when:

- Ambiguous account / merchant / category
- Looks like transfer (NEFT/IMPS/self/sweep) — needs from→to or pair match
- Soft duplicate (date±1, amount, account, similar payee) but different `external_key`
- EMI / interest split needed
- Weak amount/date parse
- Counterparty looks like another of the user’s accounts

**Reject** only for unparseable garbage (raw log only; not review UI).

### 6.4 Dedupe

1. Provider id (e.g. Gmail message-id + txn fingerprint)
2. Statement line hash (`date|amount|narration|account`)
3. Soft match → quarantine “possible duplicate”, never silent skip of a different `external_key`

Re-import / re-sync with the same `external_key` is a no-op.

### 6.5 Channels

| Channel | Phase 1 | Behavior |
|---------|---------|----------|
| Email (Gmail) | Yes | Candidate → IntakeService |
| File import | Yes | Rows → candidates; **account binding required** |
| Manual | Yes | UI builds balanced postings via LedgerService |
| Discord | Off | `project_config.discord.enabled=false`; adapters not registered |

### 6.6 Transfer pairing in intake

Opposite legs (same amount, date±1, accounts on both sides of the chart) suggest **one** transfer transaction (Dr A · Cr B). Auto-post only when both sides high-confidence and accounts known. Never create a one-legged transfer.

### 6.7 Intake must not own alerts

When Intake quarantines, it persists the row and emits a domain event (e.g. `intake.quarantine_created`). It does not notify Discord or any channel.

---

## 7. Read models (lenses)

All numbers come from **posted postings**. Each lens has a fixed definition and golden tests.

### 7.1 Budget spend (lifestyle)

**Question:** What did I consume this month by category?

- **Include:** Debits to `expense` (categorized P&L legs) in range
- **Exclude:** Income, asset↔asset transfers, investment buys, loan principal, CC bill pays, voids
- **CC:** Swipe counts; bill pay does not

Budget vs-actual uses this lens only.

### 7.2 Cash flow (bank / wallet)

**Question:** What left or entered my cash accounts?

- Postings on `asset_cash` only (signed)
- Views: money in / out / net; groupable by counter-account type
- CC bill pay appears as cash out; CC swipe does not

### 7.3 Liability / CC / loan outstanding

`balance(account)` = sum of postings with sign rules by account type.  
One formula for all accounts — no CC-only live-balance query.

Statement “closing balance” is for **reconciliation only**, not a parallel UI truth.

### 7.4 Net worth

- **Assets:** balances of `asset_*`
- **Liabilities:** balances of `liability_*`
- **Exclude:** `income`, `expense`, `equity`

Ownership percent for linked real assets must be applied consistently when bridging Assets module → `asset_other`.

### 7.5 Reconciliation (control book)

Per cash/CC account + statement period:

- Statement opening/closing + lines
- Match lines ↔ postings/transactions
- Mismatch queue when ledger ≠ statement closing or lines unmatched

Recon never auto-rewrites the ledger; adjustments go through `LedgerService` (or explicit “ignore line”).

### 7.6 KPI naming

Dashboard must expose explicitly named fields, e.g.:

- `budget_spend_month_paise`
- `cash_out_month_paise`
- `cc_outstanding_paise`
- `net_worth_paise`

No ambiguous `spent` that mixes lenses.

**Savings rate (single documented formula):**  
`(income_credits_in_period − budget_spend) / income_credits_in_period`  
(Investments are not budget spend.)

---

## 8. AlertService (standalone)

### 8.1 Responsibility

- Consume domain events (bus or outbox poll)
- Route by event type → channels (`in_app`, later `discord`, later `email`)
- Deduplicate (`event_id` / fingerprint + cooldown)
- Persist notification history + delivery status
- Respect `project_config.alerts.*` and per-channel flags

### 8.2 Non-responsibility

No budget math, no ledger writes, no Gmail parsing, no recon matching.

### 8.3 Phase 1 vs later

- **Phase 1:** `in_app` channel + structured logs; `GET /alerts`, `POST /alerts/{id}/ack`
- **Later:** Discord implements an Alert **channel** only (also reserved for quarantine / recon / budget / EMI events)

### 8.4 Decoupling from current code

Replace direct `send_discord_dm` calls inside `background_jobs.py` and domain services. Jobs call domain evaluators; evaluators emit events; AlertService delivers.

Logical home: workspace package `finance_alert` (or `packages/alert`) — extractable later; must not import ledger write APIs.

---

## 9. Migration (in-place)

### 9.1 M0 — Safety

1. File backup + checksum before rewrite
2. Schema version bump; idempotent / resumable migration
3. Feature flag `ledger.engine = legacy | double_entry`

### 9.2 M1 — Chart of accounts backfill

- Banks/wallets → `asset_cash`
- CC-linked accounts → `liability_cc` (one liability account per card)
- Loans → `liability_loan`
- Create system accounts
- Preserve `accounts.id` where possible

### 9.3 M2 — Legacy rows → transactions + postings

| Legacy shape | Action |
|--------------|--------|
| `debit` + `account_id` | Dr Expense(category) · Cr account |
| `credit` + `account_id` | Dr account · Cr Income(category) |
| Valid transfer pair (2 legs) | One tx: Dr to · Cr from |
| Orphan transfer / missing pair | Quarantine + raw snapshot (do not auto-balance) |
| Text account only | Resolve name; else quarantine |
| Debit with no account | Quarantine |
| Soft-deleted | Prefer archive/skip; or migrate as `void` |

`external_key = legacy:txn:{old_id}` for idempotency.

### 9.4 M3 — Integrity pass

1. Every posted tx sums to 0
2. No posted tx with &lt; 2 postings
3. Report migrated / quarantined / voided counts
4. Opening balance adjustments from known statement closings; gaps without statements → quarantine “needs opening balance”

### 9.5 M4 — Cutover

1. Writers → `LedgerService` only
2. Remove legacy insert paths
3. Reads → §7 lenses
4. Discord remains off
5. Keep read-only `legacy_transactions` archive until quarantine cleared (target: one FY)

### 9.6 Migration / Quarantine desk (required UX)

- Unresolved items with suggested fixes
- Preview before bulk post
- No silent force-post without balanced preview

---

## 10. Configuration

Secrets stay in env (`.env`): tokens, DB path, LLM URL.

Product behavior in `project_config` (DB or versioned config loaded at boot), including:

```text
discord.enabled = false
discord.alerts.enabled = false
alerts.in_app.enabled = true
ledger.engine = double_entry
intake.auto_post.min_confidence = <float>
intake.duplicate.date_window_days = 1
```

Toggling Discord must not require edits inside Ledger or Intake.

---

## 11. Foolproofing and tests

### 11.1 Gates

| Layer | Guard |
|-------|-------|
| LedgerService | Reject unbalanced / &lt;2 postings / missing accounts |
| DB | FK on `account_id`; CHECK amount ≠ 0; status constraints |
| Outbox | Durable domain events before notification side effects |
| CI | Golden lens tests; migrate fixture; dedupe idempotency; void atomicity |
| Boot | Posted sum≠0 → refuse write routes |
| CI lint | Ban `INSERT INTO` ledger tables outside ledger package |

### 11.2 Test pyramid

1. Unit: posting builders (swipe, bill pay, SIP, EMI split, transfer)
2. Invariant: balanced txs; void removes all legs
3. Intake: auto vs quarantine matrices; re-import idempotent
4. Lenses: one fixture → exact budget / cashflow / CC / NW
5. Migration: legacy sample → counts + invariants
6. API contract: named KPIs only
7. AlertService: event → notification; Discord skipped when disabled; alert package does not import ledger writers

---

## 12. Explicit drops and additions

### Drop / park

- Discord bot as write path (Phase 1)
- Alerts inside `background_jobs` / domain services
- Legacy `transaction_type` / `transfer_pair_id` as truth
- Text-only account on import
- Narration → silent unpaired transfer
- Parallel `cc_live_balance` special case
- Journal / Home Inventory / Construction on money integrity path
- Ambiguous dashboard `spent`

### Add

- System accounts (Opening Equity, Suspense, Uncategorized)
- Statement + recon entities
- Domain event outbox
- Standalone AlertService
- Migration / Quarantine desk UI
- EMI interest/principal split postings
- Explicit cash-flow report (hybrid CC lens)

---

## 13. Success criteria

1. Re-importing the same statement/email does not change balances
2. CC swipe raises budget spend and CC liability; bill pay lowers liability and cash only
3. SIP does not hit budget spend
4. Budget KPI ≠ cash-out KPI; both visible and tested
5. Discord off by config; enabling later cannot bypass Intake/Alert contracts
6. After migrate: zero posted unbalanced transactions; remainder quarantined

---

## 14. Delivery phases

One design; multiple implementation plans:

| Phase | Deliverable |
|-------|-------------|
| **P1** | Ledger schema + LedgerService + Balance/Reports lenses + project_config + Discord writers off |
| **P2** | IntakeService (email/import) + quarantine + dedupe |
| **P3** | Migration + quarantine desk + cutover |
| **P4** | ReconciliationService + statement matching UX |
| **P5** | AlertService (in-app) → later Discord channel |
| **P6** | Wealth polish (EMI splits, NW cash completeness, investment posting alignment) |

Recommended implementation order preserves safety: **new engine and lenses before mass migration cutover** (P1 → P2 → P3), with recon and alerts able to trail slightly (P4/P5) but not blocked from design.

---

## 15. Open implementation details (resolved at planning time, not product forks)

These do not reopen product decisions; planners must pick concrete mechanics:

1. SQLite schema naming for new tables (`transactions` reuse vs `ledger_transactions` + archive rename)
2. Outbox table vs in-process only for single-node deploy
3. Exact confidence threshold defaults
4. Whether category lives on posting vs link to `expense` sub-accounts per category (sub-accounts vs category column — prefer **category column on P&L postings** for less chart churn unless planning proves otherwise)
5. Dashboard IA for Cash Flow vs Budget (separate widgets/pages)

**Default for (4):** keep categories as a field on expense/income postings; do not explode the chart into one account per category in v1.

---

## 16. References

- Prior audit findings (spend includes credits, bulk-delete orphans pairs, import omits `account_id`, PDF/LLM drops `is_debit`, CC pay-bill/`cc_live_balance` inconsistency, over-broad transfer narration heuristics)
- Existing code hotspots: `repositories/transactions.py`, `transaction_import_service.py`, `background_jobs.py`, `discord_notify.py`, `credit_cards.py` `pay_bill`, email inbox routers
