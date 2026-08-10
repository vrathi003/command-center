# Double-Entry Money Engine P3 — Migration & Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate legacy `transactions` into the double-entry ledger (idempotent, quarantine unclean), archive history, and fully cut over Transactions reads/writes to the ledger.

**Architecture:** `MigrationService` plans each active legacy row → `ledger.service.post` (or intake quarantine). Soft-deleted rows stay in `legacy_transactions` only. Apply takes a file backup first. After apply, set cutover flags; `GET /api/transactions` becomes a ledger facade; legacy inserts return 410. Settings UI runs dry-run/apply; quarantine desk filters migration reasons.

**Tech Stack:** aiosqlite, FastAPI, pytest, React Settings + existing IntakeQuarantinePage.

**Spec:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-p3-design.md`

## Global Constraints

- Amounts: integer paise; postings signed via builders.
- Only `finance_common/ledger/` may INSERT into `ledger_*`.
- Soft-deleted legacy rows: never post (archive only).
- Do not invent opening-balance amounts — quarantine `needs_opening_balance`.
- Do not implement P4 recon, P5 Alert delivery, or P6 wealth polish.
- TDD; `uv run pytest`; commit per task; do not commit unrelated `uv.lock` noise.

## Product locks for P3

1. Full cutover after successful apply.
2. Dry-run / apply via shared service + HTTP + CLI.
3. Quarantine reuse `intake_candidates`.
4. Transactions page keeps response shape (`TransactionRow`); backend facade maps ledger → that shape.
5. Rollback = restore backup file only.

## File map

| Path | Role |
|------|------|
| `packages/common/.../project_config.py` | cutover keys |
| `packages/common/.../migration/__init__.py` | package export |
| `packages/common/.../migration/models.py` | `MigrationReport` |
| `packages/common/.../migration/resolve.py` | account resolve |
| `packages/common/.../migration/plan_row.py` | legacy row → post plan or quarantine reason |
| `packages/common/.../migration/service.py` | dry_run / apply / backup / OB pass / archive |
| `packages/common/.../migration/facade.py` | ledger → TransactionRow-shaped dicts |
| `scripts/migrate_legacy_to_ledger.py` | CLI |
| `packages/api/.../routers/migration.py` | dry-run / apply |
| `packages/api/.../routers/transactions.py` | facade + 410 + ledger writes |
| `packages/api/.../main.py` | register migration router |
| `dashboard/.../pages/SettingsPage.tsx` | migration panel |
| `dashboard/.../pages/IntakeQuarantinePage.tsx` | reason filter |
| `dashboard/.../pages/TransactionsPage.tsx` | quarantine banner |
| `dashboard/.../lib/api.ts` + `types/api.ts` | migration client types |
| `tests/test_migration_*.py` | coverage |

---

### Task 1: Migration config keys + report model

**Files:**
- Modify: `packages/common/src/finance_common/project_config.py`
- Create: `packages/common/src/finance_common/migration/__init__.py`
- Create: `packages/common/src/finance_common/migration/models.py`
- Modify: `packages/api/src/finance_api/schemas/app_settings.py` (expose cutover fields read-only if settings already expose project_config)
- Test: `tests/test_project_config.py`, `tests/test_migration_models.py`

**Interfaces:**
- Produces: `MigrationReport(migrated: int, quarantined: int, skipped_deleted: int, noop: int, backup_path: str | None, cutover_at: str | None)`
- Settings keys: `project_config.migration.legacy_cutover_at`, `project_config.migration.legacy_archive` (`"true"`/`"false"`)
- Helpers: `async def is_legacy_cutover(conn) -> bool`, `async def mark_legacy_cutover(conn, at_iso: str) -> None`

- [ ] **Step 1:** Failing tests for default cutover false + report dataclass fields
- [ ] **Step 2:** Implement keys + load/save + `MigrationReport`
- [ ] **Step 3:** `uv run pytest tests/test_project_config.py tests/test_migration_models.py -q` PASS
- [ ] **Step 4:** Commit `feat(migration): cutover config keys and MigrationReport`

---

### Task 2: Account resolve + row planner

**Files:**
- Create: `packages/common/src/finance_common/migration/resolve.py`
- Create: `packages/common/src/finance_common/migration/plan_row.py`
- Test: `tests/test_migration_plan_row.py`

**Interfaces:**
- Produces:
  ```python
  async def resolve_account_id(conn, *, account_id: int | None, account_name: str | None) -> int | None
  ```
  Exact name match on `accounts.name` (case-sensitive first; if none, casefold unique match).
- Produces:
  ```python
  @dataclass(frozen=True)
  class PlannedMigrate:
      kind: Literal["post", "quarantine", "skip_deleted", "noop"]
      external_key: str | None
      post_input: PostTransactionInput | None
      quarantine_reason: str | None
      raw_payload: dict[str, object] | None
      legacy_ids: tuple[int, ...]
  ```
- `async def plan_legacy_row(conn, row, *, paired_sibling=None, already_posted: set[str]) -> PlannedMigrate`
- Mapping:
  - deleted → `skip_deleted`
  - external_key already posted → `noop`
  - transfer with valid sibling → `plan_transfer`, key `legacy:pair:{pair_id}`
  - debit/credit → Candidate-equivalent via `plan_postings` (direction out/in), key `legacy:txn:{id}`
  - missing account → quarantine `legacy_migration:missing_account`
  - orphan transfer → `legacy_migration:orphan_transfer`

- [ ] **Step 1:** Tests for SBI Personal name resolve, debit/credit/transfer/missing/deleted
- [ ] **Step 2:** Implement resolve + plan_row (reuse `intake.posting_plan.plan_postings` / `plan_transfer`)
- [ ] **Step 3:** pytest PASS
- [ ] **Step 4:** Commit `feat(migration): plan legacy rows into ledger posts or quarantine`

---

### Task 3: MigrationService dry_run + apply (+ backup)

**Files:**
- Create: `packages/common/src/finance_common/migration/service.py`
- Test: `tests/test_migration_service.py`

**Interfaces:**
```python
async def dry_run(conn) -> MigrationReport
async def apply(conn, *, db_path: Path) -> MigrationReport
```

Apply steps:
1. Copy `db_path` → `{stem}.pre-ledger-migrate-{utc}.db` beside it; sha256 into report notes (store path on report).
2. Iterate active + deleted rows (deleted only count skip).
3. Group transfer pairs: process pair once; skip second leg as part of pair.
4. On `post`: `ledger.service.post`; on quarantine: `save_candidate` pending + `append_event` `migration.quarantine_created`.
5. After history: `_opening_balance_pass(conn)` → pending candidates `needs_opening_balance` for each `asset_cash`/`liability_cc` with postings and no equity OB posting yet.
6. Archive: `CREATE TABLE IF NOT EXISTS legacy_transactions AS SELECT * FROM transactions` only if table empty/missing — if exists with rows, skip recreate; else copy. Prefer: if not exists, `CREATE TABLE legacy_transactions AS SELECT * FROM transactions`.
7. `mark_legacy_cutover(conn, now_iso)`.
8. Return report.

Dry-run: same planning, no writes, no backup required.

- [ ] **Step 1:** Fixture tests — 1 debit, 1 credit, 1 soft-delete, 1 missing account, 1 transfer pair → counts; second apply all noop; backup file created on apply
- [ ] **Step 2:** Implement service
- [ ] **Step 3:** pytest PASS
- [ ] **Step 4:** Commit `feat(migration): dry-run and apply legacy→ledger with backup`

---

### Task 4: CLI

**Files:**
- Create: `scripts/migrate_legacy_to_ledger.py`
- Test: optional smoke via subprocess or skip if covered by service tests — prefer thin CLI calling service

```python
# argparse --dry-run | --apply; load DB_PATH from env; print MigrationReport JSON
```

- [ ] **Step 1:** Implement CLI
- [ ] **Step 2:** `uv run python scripts/migrate_legacy_to_ledger.py --help` works
- [ ] **Step 3:** Commit `feat(migration): CLI dry-run/apply entrypoint`

---

### Task 5: Migration HTTP API

**Files:**
- Create: `packages/api/src/finance_api/routers/migration.py`
- Create: `packages/api/src/finance_api/schemas/migration.py`
- Modify: `packages/api/src/finance_api/main.py`
- Test: `tests/test_migration_api.py`

Endpoints:
- `POST /api/migration/legacy-ledger/dry-run` → MigrationReport
- `POST /api/migration/legacy-ledger/apply` → Depends `require_ledger_writes`; uses settings `DB_PATH` for backup source

- [ ] **Step 1:** API tests with TestClient + seeded legacy rows
- [ ] **Step 2:** Implement + register router
- [ ] **Step 3:** pytest PASS
- [ ] **Step 4:** Commit `feat(api): legacy ledger migration dry-run/apply`

---

### Task 6: Ledger → transactions facade

**Files:**
- Create: `packages/common/src/finance_common/migration/facade.py`
- Modify: `packages/api/src/finance_api/routers/transactions.py` (GET list/get)
- Test: `tests/test_transactions_facade.py`

**Mapping rules** (posted ledger tx → dict matching `_tx_row_dict`):
- `id` = ledger transaction id
- `date`, `merchant`=`payee`, `notes`, `source`, `tags`
- `amount_paise` = `sum(abs(p.amount_paise))//2`
- Pick cash/CC leg: posting whose account_class in `asset_cash`,`liability_cc` (if two, prefer asset_cash for transfers’ “from” as transfer type)
- If both legs are asset/liability (transfer): `transaction_type="transfer"`, `transfer_pair_id=external_key or f"ledger:{id}"`, `account_id`=from (negative cash leg)
- Else if cash/CC leg amount &lt; 0: `debit` (money out / CC swipe liability more negative)
- Else: `credit`
- `category` from P&L posting category or `"Other"`
- `payment_mode` = `"Other"` (legacy field unused on ledger)
- `account` = account name for `account_id`

When `is_legacy_cutover(conn)` **or** `ledger_engine==double_entry` **and** `legacy_transactions` exists / cutover flag set — use facade. Spec: after apply cutover is set; until then GET may still read legacy. **Rule:** if `is_legacy_cutover` → facade; else → legacy `tx_repo.list_recent`.

- [ ] **Step 1:** Unit tests for mapping debit/credit/transfer
- [ ] **Step 2:** Wire GET `/` and `/{id}`
- [ ] **Step 3:** pytest PASS
- [ ] **Step 4:** Commit `feat(api): transactions list facade over ledger after cutover`

---

### Task 7: Cutover writers — 410 + ledger create/void

**Files:**
- Modify: `packages/api/src/finance_api/routers/transactions.py` (POST/, PUT, transfer, bulk-delete)
- Test: `tests/test_transactions_cutover.py`

When `is_legacy_cutover(conn)`:
- `POST /` debit/credit → `plan_postings`-equivalent + `ledger.post` (require account_id); return `{id: ledger_id}`
- `POST /transfer` → `plan_transfer` + post; return `transfer_pair_id=f"ledger:{id}"`, both ids = ledger id
- `PUT /{id}` → void old + post new (or reject 501 with message — prefer void+repost for simplicity)
- `POST /bulk-delete` → `ledger.void` each id
- If somehow code still calls `insert_transaction` under cutover in this router — must not; gate at start of each write handler

Also: if cutover and client hits a forgotten legacy path → HTTP 410 `legacy transactions are archived; use ledger`.

- [ ] **Step 1:** Tests create/list/void after apply
- [ ] **Step 2:** Implement
- [ ] **Step 3:** pytest PASS
- [ ] **Step 4:** Commit `feat(api): cutover manual tx writes to ledger`

---

### Task 8: Settings migration panel + API client

**Files:**
- Modify: `dashboard/src/pages/SettingsPage.tsx`
- Modify: `dashboard/src/lib/api.ts`, `dashboard/src/types/api.ts`
- Optional: expose cutover_at on GET settings

UI:
- Section “Ledger migration”
- Buttons Dry-run / Apply (Apply confirm dialog)
- Show last report counts + cutover timestamp if set

- [ ] **Step 1:** Types + api helpers
- [ ] **Step 2:** Settings panel wired to endpoints
- [ ] **Step 3:** `npm run build` (or tsc) PASS
- [ ] **Step 4:** Commit `feat(dashboard): settings panel for legacy→ledger migration`

---

### Task 9: Quarantine desk + Transactions banner

**Files:**
- Modify: `dashboard/src/pages/IntakeQuarantinePage.tsx` — filter chips: All / legacy_migration / needs_opening_balance / other
- Modify: `dashboard/src/pages/TransactionsPage.tsx` — if pending intake count &gt; 0 after cutover, show link banner to quarantine
- Approve OB: ensure approve API already supports amount override — if not, extend ApproveBody with `amount_paise` for OB posts using Opening Balance Equity builder

OB approve path (if missing):
- When reason is `needs_opening_balance` and body has `amount_paise` + `account_id`: post Dr/Cr between account and Opening Balance Equity (sign: positive amount = increase asset via Dr cash Cr equity).

- [ ] **Step 1:** Backend OB approve support + test if needed
- [ ] **Step 2:** UI filter + banner
- [ ] **Step 3:** build PASS
- [ ] **Step 4:** Commit `feat(dashboard): migration quarantine filters and OB approve`

---

### Task 10: P3 acceptance

Run:
```bash
uv run pytest tests/test_migration_*.py tests/test_transactions_facade.py tests/test_transactions_cutover.py tests/test_intake_*.py tests/test_ledger_*.py -q
uv run python scripts/ci_check_ledger_writes.py
uv run pytest -q --tb=line
```

Operator smoke (document in report; do **not** auto-apply to live DB without user confirm in acceptance notes):
1. Dry-run against `~/finance/finance.db` — record counts
2. User confirms → Apply
3. Transactions page shows history; re-apply noop
4. Quarantine shows `needs_opening_balance` for SBI Personal (and any other cash/CC)

Update `docs/superpowers/plans/2026-08-10-double-entry-money-engine-roadmap.md` — mark P3 done + link plan.

- [ ] **Step 1:** Fix failures
- [ ] **Step 2:** Write `.superpowers/sdd/task-p3-acceptance-report.md` (or `task-11` style under sdd)
- [ ] **Step 3:** Commit `docs: P3 migration acceptance notes`

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| M0 backup + idempotent keys | 3 |
| M1 account resolve | 2 |
| M2 row mapping + quarantine | 2–3 |
| M3 OB quarantine | 3, 9 |
| M4 archive + cutover flags | 3, 7 |
| Dry-run/apply API+CLI | 4–5 |
| Transactions facade | 6 |
| Settings + quarantine UX | 8–9 |
| Soft-delete skip | 2–3 |

## Out of scope

P4 recon, P5 alerts, P6 wealth polish, dropping `legacy_transactions`.
