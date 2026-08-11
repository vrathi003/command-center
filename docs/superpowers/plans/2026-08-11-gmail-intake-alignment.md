# Gmail Inbox ↔ Intake Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route Email Inbox approve/transfer through a hybrid Intake bridge while keeping Gmail sync → staging review desk.

**Architecture:** `finance_common.intake.email_bridge` maps staging → Candidate (`source=email`, external_key prefix `gmail:`). Non-force approve calls `ingest()`; force posts via LedgerService. Staging gains `quarantined` + `intake_candidate_id`. Quarantine desk syncs staging on candidate approve/reject.

**Tech Stack:** aiosqlite, FastAPI, pytest, React EmailInboxPage.

**Spec:** `docs/superpowers/specs/2026-08-11-gmail-intake-alignment-design.md`

## Global Constraints

- Sync never calls Intake — staging only.
- Candidate.source = `email`; external_key prefix remains `gmail:` for provider ids.
- Only `finance_common/ledger/` inserts ledger rows (via LedgerService / ingest).
- Legacy `ledger_engine` path stays on `transactions` inserts.
- TDD; `uv run pytest`; commit per task; do not commit unrelated `uv.lock`.
- Do not implement auto-ingest on sync, Discord channel, or P5 merge.

## File map

| Path | Role |
|------|------|
| `db/schema.sql` + `migrations.py` | staging status + `intake_candidate_id` |
| `repositories/email_staging.py` | set_status fields, reset ledger id, get by candidate |
| `intake/email_bridge.py` | approve / transfer orchestration |
| `routers/email_inbox.py` | call bridge; schemas |
| `routers/intake.py` | sync-back staging |
| `dashboard/.../EmailInboxPage.tsx` + api/types | quarantined UX |
| `tests/test_email_inbox_*.py` | coverage |

---

### Task 1: Staging schema — `quarantined` + `intake_candidate_id`

**Files:** `schema.sql`, `migrations.py`, `tests/test_email_staging_schema.py` (new)

- Add nullable `intake_candidate_id INTEGER REFERENCES intake_candidates(id)`.
- Document statuses: `pending|approved|rejected|quarantined` (add CHECK if rebuilding; else app-enforced + migration note). Prefer ALTER ADD COLUMN; if CHECK needed and table has none today, skip CHECK and validate in repo.

- [ ] Failing schema test → migrate → PASS  
- [ ] Commit `feat(email): staging quarantined status and candidate link`

---

### Task 2: email_staging repository glue

**Files:** `repositories/email_staging.py`, tests

- `set_status(..., intake_candidate_id=...)`  
- `reset_by_transaction_ids` also clears `ledger_transaction_id` and `intake_candidate_id`, status `pending`  
- `reset_by_ledger_transaction_ids(conn, ids)` for undo path  
- `get_by_intake_candidate_id` / list helpers as needed  
- Row dataclass includes new fields

- [ ] TDD → commit `feat(email): staging repo candidate link and ledger reset`

---

### Task 3: `email_bridge` approve + transfer

**Files:** Create `packages/common/src/finance_common/intake/email_bridge.py`, `tests/test_email_bridge.py`

**Interfaces:**

```python
async def approve_staged_item(
    conn, *, staging_id: int, overrides: ApproveOverrides, force: bool
) -> StagedEmailRow: ...

async def approve_as_transfer(
    conn, *, debit_id: int, credit_id: int, ..., force: bool
) -> tuple[StagedEmailRow, StagedEmailRow, int]: ...
```

Behaviors per design §5. Use `ingest` for single-item non-force; force → `plan_postings`/`plan_transfer` + `ledger_service.post` + `save_candidate`/`update_candidate_status`.

- [ ] TDD covering POSTED / QUARANTINED / force / transfer  
- [ ] Commit `feat(intake): email_bridge hybrid approve and transfer`

---

### Task 4: Wire email_inbox + intake sync-back API

**Files:** `routers/email_inbox.py`, schemas, `routers/intake.py`, `tests/test_email_inbox_ledger.py` (extend)

- Replace inline double_entry approve/transfer with bridge calls.
- Allow approve from `quarantined` when `force=true`.
- On quarantine: return 200 with status `quarantined` (remove non-force soft-dupe 409 for double_entry).
- Intake candidate approve/reject: if `email_staging_id`, update staging.

- [ ] API tests PASS → commit `feat(api): email inbox uses intake bridge`

---

### Task 5: Dashboard Email Inbox UX

**Files:** `EmailInboxPage.tsx`, `api.ts`, `types/api.ts`

- Surface `quarantined` status badge; link to quarantine desk.
- Show Force approve when quarantined / soft-dupe messaging updated for 200 quarantined response.
- Stats include quarantined count if shown.

- [ ] `npm run build --prefix dashboard` PASS  
- [ ] Commit `feat(dashboard): email inbox quarantined status`

---

### Task 6: Acceptance

- Full `uv run pytest` + ledger write CI  
- Optional short note in roadmap or leave as standalone spec  
- Commit `docs: gmail intake alignment acceptance` if adding report under `.superpowers/sdd/`

---

## Self-review vs spec

| Spec | Task |
|------|------|
| §4 schema | 1–2 |
| §5 approve/transfer | 3–4 |
| §5.3 sync-back | 4 |
| §6 UI | 5 |
| §7 tests | 1–6 |
| Sync unchanged | enforced in tasks |
