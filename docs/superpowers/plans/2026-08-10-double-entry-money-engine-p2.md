# Double-Entry Money Engine P2 — Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route email and file-import money into the double-entry ledger through `IntakeService` (auto-post when confident, otherwise quarantine), with idempotent dedupe and required account binding — without Discord writers or AlertService delivery.

**Architecture:** Parsers emit `Candidate` dicts. `IntakeService.ingest` decides auto-post / quarantine / reject using `project_config` thresholds. Auto-post calls `finance_common.ledger.service.post` + builders only (CI insert ban). Quarantine rows live in `intake_candidates`. Domain events for quarantine are written to a minimal `domain_events` outbox table (P5 AlertService will consume later; P2 only persists + logs).

**Tech Stack:** Same as P1 — aiosqlite, FastAPI, pytest, React dashboard for quarantine desk.

**Spec:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md` §6, §14 P2.

## Global Constraints

- Amounts: integer paise; ledger postings signed (+debit / −credit).
- Only `finance_common/ledger/` may INSERT into `ledger_*` tables.
- Intake must not import Discord / `discord_notify`.
- Do not implement P3 migration cutover, P4 recon, or P5 Alert delivery.
- When `ledger.engine=legacy`, keep existing approve/import paths writing legacy `transactions` (compat). When `double_entry` (default), Intake → ledger only.
- File import **requires** `account_id` (not name-only) under double_entry.
- TDD; `uv run pytest`; commit per task.

## Product locks for P2

1. **Unified `intake_candidates` table** — not a rewrite of `email_transaction_staging`. Gmail sync still fills email staging for the existing inbox UI; **approve** (and optional auto-path) converts staging → Candidate → Intake. File import creates candidates directly.
2. **Expense/income P&L account** — use system accounts `Uncategorized Expense` / `Uncategorized Income` for the counter-account; put merchant category on the posting `category` field (already required by LedgerService for P&L).
3. **Legacy Transactions page** — unchanged in P2 (still reads `transactions`). New money is visible via ledger summary + quarantine desk + new ledger list API. P3 cutover unifies UI.
4. **CC statement apply** — included: apply path uses Intake with `build_cc_swipe` when engine=double_entry.
5. **Events** — insert into `domain_events` (`event_type`, `payload_json`, `created_at`); no notifier.

## File map

| Path | Role |
|------|------|
| `packages/common/.../db/schema.sql` + `migrations.py` | `intake_candidates`, `domain_events` |
| `packages/common/.../intake/models.py` | Candidate dataclass, Decision enum |
| `packages/common/.../intake/dedupe.py` | external_key + soft-match |
| `packages/common/.../intake/service.py` | `IntakeService.ingest` / `approve_quarantined` / `reject` |
| `packages/common/.../intake/posting_plan.py` | Candidate → PostTransactionInput (builders) |
| `packages/common/.../repositories/intake_candidates.py` | CRUD |
| `packages/common/.../repositories/domain_events.py` | append-only outbox |
| `packages/api/.../routers/intake.py` | quarantine list/approve/reject |
| `packages/api/.../routers/email_inbox.py` | approve → Intake when double_entry |
| `packages/api/.../services/transaction_import_service.py` | rows → Intake |
| `packages/api/.../routers/transactions.py` | import form requires `account_id` when double_entry |
| `packages/api/.../routers/credit_cards.py` | apply_statement → Intake |
| `packages/api/.../routers/ledger.py` | `GET /ledger/transactions` list |
| `dashboard/.../pages/IntakeQuarantinePage.tsx` | quarantine desk |
| `dashboard/.../App.tsx` + `AppShell.tsx` | nav route |
| `tests/test_intake_*.py` | matrices |

---

### Task 1: Schema — `intake_candidates` + `domain_events`

**Files:** schema.sql, migrations.py, `tests/test_intake_schema.py`

**DDL `intake_candidates`:**
- `id INTEGER PK`
- `status TEXT` CHECK IN (`pending`,`posted`,`rejected`) DEFAULT `pending`
- `source TEXT NOT NULL` (`email`|`import`|`cc_statement`|`manual`)
- `external_key TEXT` UNIQUE WHERE NOT NULL
- `tx_date TEXT NOT NULL`
- `amount_paise INTEGER NOT NULL CHECK (amount_paise > 0)`
- `direction TEXT NOT NULL` CHECK IN (`out`,`in`) — relative to `suggested_account_id`
- `payee TEXT`, `narration TEXT`
- `suggested_account_id INTEGER REFERENCES accounts(id)`
- `suggested_counter_account_id INTEGER REFERENCES accounts(id)` — optional; else system P&L
- `suggested_category TEXT`
- `confidence REAL NOT NULL DEFAULT 0`
- `quarantine_reason TEXT`
- `ledger_transaction_id INTEGER REFERENCES ledger_transactions(id)`
- `raw_payload_json TEXT`
- `email_staging_id INTEGER` — optional link
- `created_at` / `updated_at`

**DDL `domain_events`:**
- `id INTEGER PK`, `event_type TEXT NOT NULL`, `payload_json TEXT NOT NULL`, `created_at TEXT`

- [ ] **Step 1:** Failing test that `ensure_database` creates both tables  
- [ ] **Step 2:** Implement DDL + migration  
- [ ] **Step 3:** Pass + commit `feat(intake): schema for candidates and domain events`

---

### Task 2: Candidate model + posting planner

**Files:** `intake/models.py`, `intake/posting_plan.py`, `tests/test_intake_posting_plan.py`

```python
@dataclass(frozen=True, slots=True)
class Candidate:
    source: str
    tx_date: date
    amount_paise: int  # positive magnitude
    direction: Literal["out", "in"]
    suggested_account_id: int | None
    payee: str | None = None
    narration: str | None = None
    suggested_category: str | None = None
    suggested_counter_account_id: int | None = None
    external_key: str | None = None
    confidence: float = 0.0
    raw_payload: dict | None = None
    email_staging_id: int | None = None

async def plan_postings(conn, candidate: Candidate) -> PostTransactionInput:
    """Resolve P&L accounts + builders; raise IntakePlanError if account missing."""
```

Rules:
- `direction=out` + cash/wallet account → `build_bank_expense` (expense acct = counter or Uncategorized Expense)
- `direction=in` + cash → `build_bank_income`
- `direction=out` + `liability_cc` → `build_cc_swipe`
- `direction=in` + `liability_cc` → treat as payment toward card → needs bank account; if missing, quarantine (planner returns error → caller quarantines)
- Transfer: only when caller passes both accounts via a dedicated `plan_transfer(from_id, to_id, ...)`

- [ ] **Step 1:** Unit tests for expense/income/cc_swipe plans  
- [ ] **Step 2:** Implement + resolve system accounts by name  
- [ ] **Step 3:** Commit `feat(intake): candidate model and posting planner`

---

### Task 3: Dedupe helpers

**Files:** `intake/dedupe.py`, `tests/test_intake_dedupe.py`

```python
def make_external_key(*, source: str, provider_id: str | None, date: str, amount_paise: int, narration: str, account_id: int | None) -> str:
    """Prefer provider_id; else sha256 of statement-line fingerprint."""

async def find_soft_duplicate(conn, *, account_id, amount_paise, tx_date, payee, window_days: int) -> int | None:
    """Return intake_candidates.id or ledger tx id of soft match; None if none.
    Soft match: same account_id, amount, date±window, normalized payee prefix."""
```

Also check existing `ledger_transactions.external_key` via ledger service idempotency.

- [ ] Tests for key stability + soft window  
- [ ] Commit `feat(intake): external_key and soft-duplicate helpers`

---

### Task 4: IntakeService.ingest

**Files:** `intake/service.py`, `repositories/intake_candidates.py`, `repositories/domain_events.py`, `tests/test_intake_service.py`

```python
class Decision(StrEnum):
    POSTED = "posted"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"
    NOOP = "noop"  # duplicate external_key already posted

async def ingest(conn, candidate: Candidate) -> tuple[Decision, int | None]:
    """Returns (decision, candidate_id or ledger_tx_id)."""
```

Decision matrix (use `load_project_config`):
1. If `external_key` already on posted ledger tx → `NOOP`
2. If `suggested_account_id` is None → quarantine `missing_account`
3. If soft duplicate found → quarantine `possible_duplicate`
4. If narration suggests bank transfer (`narration_suggests_bank_transfer`) and not an explicit transfer plan → quarantine `possible_transfer`
5. If `confidence < min_confidence` → quarantine `low_confidence`
6. Else `plan_postings` → `ledger_service.post` → mark candidate `posted` (insert row for audit) → return POSTED  
7. On `IntakePlanError` → quarantine with reason

On quarantine: insert candidate `pending`, append `domain_events` `intake.quarantine_created`, `logger.info`.

- [ ] Golden tests covering each branch  
- [ ] Commit `feat(intake): IntakeService ingest auto-post and quarantine`

---

### Task 5: Quarantine approve / reject API

**Files:** `routers/intake.py`, schemas, `main.py` register, `tests/test_intake_api.py`

Endpoints:
- `GET /api/intake/candidates?status=pending`
- `POST /api/intake/candidates/{id}/approve` body: optional overrides (account_id, category, counter_account_id, as_transfer to_account_id)
- `POST /api/intake/candidates/{id}/reject`

Approve rebuilds Candidate from row + overrides → `plan_postings` / `plan_transfer` → `ledger.post` → status posted.  
Depends on `require_ledger_writes` for approve.

- [ ] API tests with TestClient  
- [ ] Commit `feat(api): intake quarantine list/approve/reject`

---

### Task 6: Wire file import → Intake

**Files:** `transaction_import_service.py`, `routers/transactions.py`, dashboard import UI if present

When `ledger_engine == double_entry`:
- Require form field `account_id` (int); 422 if missing
- For each parsed row: build Candidate (`source=import`, direction from transaction_type debit→out credit→in, confidence from merchant rule or 0.5 default, external_key from fingerprint)
- Call `ingest`; collect counts `{posted, quarantined, rejected, noop, failed}`
- Do **not** call `insert_transaction`

When `legacy`: keep old path.

- [ ] Tests: import with account_id posts; without → 422; duplicate external_key → noop  
- [ ] Commit `feat(import): route bank file import through IntakeService`

---

### Task 7: Wire email approve → Intake

**Files:** `email_inbox.py`

When `double_entry`:
- `approve_staged` → Candidate from staging row (account from `suggested_account_id` or body) → `ingest` (force confidence=1.0 on explicit approve) OR direct `plan`+`post` bypassing confidence gate (explicit human approve should post even if low confidence, still run soft-dupe warn: if soft dupe, 409 unless `force=true`)
- `approve_as_transfer` → `plan_transfer` + `ledger.post` (not unpaired)
- Store `ledger_transaction_id` on staging if column exists — add `ledger_transaction_id` to `email_transaction_staging` via migration
- `undo_approved` → `ledger.void` when ledger id set

When `legacy`: unchanged.

- [ ] Tests for approve → ledger post + void  
- [ ] Commit `feat(email): approve staged mail into double-entry ledger`

---

### Task 8: Wire CC statement apply → Intake

**Files:** `credit_cards.py` apply_statement

When `double_entry` and card has `account_id`:
- Each non-skip line → Candidate direction out/in from type, `suggested_account_id=card.account_id`, external_key `cc_stmt:{statement_id}:{line_idx}` or hash, confidence 0.9 if classified else 0.6
- `ingest` each line; payments that look like bill pay → quarantine `cc_payment` for user to confirm bank account (or skip as today)

When `legacy`: unchanged `insert_transaction` loop.

- [ ] Test apply posts cc_swipe to ledger  
- [ ] Commit `feat(cc): apply statements through Intake when double_entry`

---

### Task 9: Ledger list API

**Files:** `ledger/service.py` or `repositories`, `routers/ledger.py`

`GET /api/ledger/transactions?from=&to=&limit=` → list posted headers with postings summary (date, payee, amount abs, accounts).

- [ ] Test list returns ingested rows  
- [ ] Commit `feat(api): list ledger transactions`

---

### Task 10: Quarantine desk UI

**Files:** `IntakeQuarantinePage.tsx`, `api.ts`, `types/api.ts`, App route + AppShell nav (e.g. under Transactions)

- List pending candidates (date, amount, payee, reason, confidence)
- Actions: Approve (account picker if missing), Reject
- Link from Email Inbox banner: “Ledger quarantine”

Keep EmailInboxPage working; do not remove it.

- [ ] Manual smoke OK; basic render test optional  
- [ ] Commit `feat(dashboard): intake quarantine desk`

---

### Task 11: P2 acceptance

Run:
```bash
uv run pytest tests/test_intake_*.py tests/test_ledger_*.py tests/test_transactions_import.py -v
uv run python scripts/ci_check_ledger_writes.py
```

Smoke:
1. Import CSV with `account_id` → some posted / quarantined  
2. Re-import same file → noop / no balance change  
3. Email approve → ledger tx  
4. Quarantine UI approve transfer-looking row  

- [ ] Document results in report; fix failures  
- [ ] Update roadmap: mark P2 plan path ready / done  
- [ ] Commit if docs only: `docs: P2 intake acceptance notes`

---

## Spec coverage

| Spec §6 item | Task |
|--------------|------|
| Candidate fields | 2 |
| Auto-post / quarantine rules | 4 |
| Dedupe external_key + soft | 3–4 |
| File import account binding | 6 |
| Email channel | 7 |
| Transfer pairing (approve-as-transfer + quarantine possible_transfer) | 4,5,7 |
| No alerts in intake | 4 (outbox only) |
| LedgerService only writer | all |

## Out of scope

- P3 legacy migration / Transactions page cutover  
- P4 statement reconciliation  
- P5 AlertService Discord/in-app delivery  
- Discord bot intake adapter  
- Auto-post on Gmail sync without human approve (optional follow-up: can call ingest from sync with confidence; default P2 keeps sync → staging → approve)

---

## Self-review

- No dual-write to legacy (avoids double books); visibility via ledger list + quarantine  
- Explicit human approve bypasses confidence but not soft-dupe without force  
- CC bill-pay lines quarantine rather than inventing bank account  
