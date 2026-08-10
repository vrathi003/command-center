# Double-Entry Money Engine P4 — Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dedicated recon store + ReconciliationService + API + account/period workspace UI so statement lines can be suggest-matched to the ledger and periods soft-closed when balances agree.

**Architecture:** `finance_common.recon` owns statements/lines/matches. Suggestions are ephemeral until confirm. Soft-close gates on all lines matched|ignored and ledger as-of closing == statement closing. Adjustments call `ledger.service.post` only. Dashboard `/reconciliation` workspace.

**Tech Stack:** aiosqlite, FastAPI, pytest, React (PageHero/Panel/TanStack Query), reuse import parsers for file → rows.

**Spec:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-p4-design.md`

## Global Constraints

- Amounts: integer paise; statement line amounts positive + direction.
- Only `finance_common/ledger/` may INSERT into `ledger_*`.
- Recon never auto-rewrites ledger; confirm/ignore/adjust are explicit.
- Suggest only — no silent persist of matches.
- Soft-close reversible via reopen; hard-lock out of scope.
- Do not implement P5 Alert delivery or P6 wealth polish.
- TDD; `uv run pytest`; commit per task; do not commit unrelated `uv.lock`.

## Product locks

1. Account + period workspace UI.
2. Dedicated `recon_*` tables (not intake dual-use).
3. Suggest + confirm matching.
4. Soft close when balanced + lines cleared.

## File map

| Path | Role |
|------|------|
| `packages/common/.../db/schema.sql` + `migrations.py` | recon tables |
| `packages/common/.../project_config.py` | `recon_match_date_window_days` |
| `packages/common/.../recon/models.py` | dataclasses |
| `packages/common/.../recon/suggest.py` | match scoring |
| `packages/common/.../recon/service.py` | import/suggest/confirm/ignore/close |
| `packages/common/.../repositories/recon.py` | persistence |
| `packages/api/.../routers/recon.py` + schemas | HTTP |
| `packages/api/.../main.py` | register |
| `dashboard/.../pages/ReconciliationPage.tsx` | UI |
| `dashboard/.../App.tsx` + `AppShell.tsx` | route/nav |
| `dashboard/.../lib/api.ts` + `types/api.ts` | client |
| `tests/test_recon_*.py` | coverage |

---

### Task 1: Schema + config

**Files:** schema.sql, migrations.py, project_config.py, app_settings schemas, tests

Create tables `recon_statements`, `recon_statement_lines`, `recon_matches` per design.  
Add `KEY_RECON_MATCH_DATE_WINDOW_DAYS` default `2` on `ProjectConfig`.

- [ ] Failing schema/config tests → implement → pytest PASS  
- [ ] Commit `feat(recon): schema and match window config`

---

### Task 2: Repository + models

**Files:** `recon/models.py`, `repositories/recon.py`, tests

CRUD: create statement + lines, list by account, get workspace rows, insert/delete match, update line status, set statement status.

- [ ] TDD  
- [ ] Commit `feat(recon): repositories for statements lines matches`

---

### Task 3: Suggest matcher

**Files:** `recon/suggest.py`, tests

```python
@dataclass(frozen=True)
class MatchProposal:
    line_id: int
    ledger_transaction_id: int
    score: float
    reasons: tuple[str, ...]
```

Rules: same account posting on ledger tx; `ABS(amount)` equal; date within window; payee prefix bonus. One proposal per line (best score); exclude already matched txs.

- [ ] Golden unit tests  
- [ ] Commit `feat(recon): suggest matches by amount date payee`

---

### Task 4: ReconciliationService

**Files:** `recon/service.py`, tests

Implement: `import_rows`, `suggest_matches`, `confirm_match`, `unmatch`, `ignore_line`, `period_status`, `soft_close`, `reopen`, `create_adjustment` (bank expense/income builders + post + confirm).

`period_status` needs ledger balance **as-of** `period_end`. Extend `ledger.balances.account_balance_paise(conn, account_id, *, as_of: date | None = None)` (same join filter as NW as-of) — additive, default `None` keeps current behavior.

Import: map parser rows → direction/amount; no ledger writes.

- [ ] Service tests covering close gates  
- [ ] Commit `feat(recon): ReconciliationService import suggest close`

---

### Task 5: HTTP API

**Files:** routers/recon.py, schemas/recon.py, main.py, tests/test_recon_api.py

Endpoints from design §5. Apply `require_ledger_writes` on adjust / (optional) soft-close if it only flips flag — soft-close is not a ledger write; adjust requires gate.

Import endpoint: multipart file + account_id + period + opening/closing (form fields).

- [ ] TestClient coverage  
- [ ] Commit `feat(api): reconciliation endpoints`

---

### Task 6: Dashboard Reconciliation page

**Files:** ReconciliationPage.tsx, api.ts, types, App.tsx, AppShell.tsx

Account picker, statement list, workspace (lines / suggestions / unmatched ledger), actions, soft-close footer.

- [ ] `npm run build` PASS  
- [ ] Commit `feat(dashboard): reconciliation workspace`

---

### Task 7: P4 acceptance

```bash
uv run pytest tests/test_recon_*.py tests/test_ledger_*.py -q
uv run python scripts/ci_check_ledger_writes.py
uv run pytest -q --tb=line
```

Update roadmap: mark P4 done + link plan.  
Write `.superpowers/sdd/task-p4-acceptance-report.md` (or task-N style).  
Commit `docs: P4 reconciliation acceptance notes`.

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Tables | 1–2 |
| Suggest + confirm | 3–4 |
| Soft close gates | 4–5 |
| Adjust via ledger | 4–5 |
| Workspace UI | 6 |
| No silent rewrite | 3–4 |

## Out of scope

P5 alerts, P6 wealth, hard close, auto-apply matches, intake-as-recon-store.
