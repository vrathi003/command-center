# Double-Entry Money Engine P5 — AlertService Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drain `domain_events` into durable in-app notifications via a standalone AlertService, refactor budget/EMI/CC jobs to emit events only, and ship Dashboard banner + `/alerts` ack UI.

**Architecture:** `finance_common.alerts` owns routing + `poll_once`. Outbox rows gain `processed_at`. Notifications live in `alert_notifications` (unique `fingerprint`). APScheduler interval + API startup drain the outbox. Discord channel and digests are out of scope.

**Tech Stack:** aiosqlite, FastAPI, APScheduler, pytest, React (PageHero/Panel/TanStack Query).

**Spec:** `docs/superpowers/specs/2026-08-11-double-entry-money-engine-p5-design.md`

## Global Constraints

- Amounts in payloads stay integer paise; display formatting only at message render time.
- AlertService must not import ledger write APIs (`finance_common.ledger.service` / builders that post).
- No Discord Alert channel in P5; do not re-enable Discord for digests.
- Digests (`job_weekly_discord`, `job_monthly_discord`) stay unchanged.
- Respect `project_config.alerts.in_app.enabled`.
- Unknown `event_type` → mark processed, no notification.
- TDD; `uv run pytest`; commit per task; do not commit unrelated `uv.lock`.
- Do not implement P6 wealth polish or recon event delivery.

## Product locks

1. In-app only + job emit refactor (no Discord channel).
2. Producers: budget / EMI / CC due + existing intake/migration events.
3. Package: `finance_common/alerts/`.
4. Outbox poller (`processed_at`).
5. Banner + `/alerts` page.
6. Digests out of scope.

## File map

| Path | Role |
|------|------|
| `packages/common/.../db/schema.sql` + `migrations.py` | `processed_at`, `alert_notifications` |
| `packages/common/.../repositories/domain_events.py` | list unprocessed + mark processed |
| `packages/common/.../repositories/alerts.py` | notification CRUD |
| `packages/common/.../alerts/__init__.py` | package export |
| `packages/common/.../alerts/models.py` | dataclasses |
| `packages/common/.../alerts/route.py` | event → notification fields |
| `packages/common/.../alerts/service.py` | `poll_once` |
| `packages/api/.../routers/alerts.py` + `schemas/alerts.py` | HTTP |
| `packages/api/.../routers/dashboard.py` | unread peek |
| `packages/api/.../schemas/dashboard.py` | optional `id` on `AlertItem` |
| `packages/api/.../main.py` | register router; startup poll |
| `packages/api/.../services/background_jobs.py` | emit events; alert poller job; CC job without Discord gate |
| `dashboard/.../pages/AlertsPage.tsx` | history UI |
| `dashboard/.../components/dashboard/AlertsBanner.tsx` | ack |
| `dashboard/.../App.tsx` + `AppShell.tsx` | route/nav |
| `dashboard/.../lib/api.ts` + `types/api.ts` | client |
| `tests/test_alerts_*.py` | coverage |
| `docs/superpowers/plans/...-roadmap.md` | mark P5 done after acceptance |

---

### Task 1: Schema — `processed_at` + `alert_notifications`

**Files:**
- Modify: `packages/common/src/finance_common/db/schema.sql`
- Modify: `packages/common/src/finance_common/db/migrations.py`
- Test: `tests/test_alerts_schema.py`

**Interfaces:**
- Produces: tables/columns matching design §4

- [ ] **Step 1: Write failing schema test**

```python
# tests/test_alerts_schema.py
@pytest.mark.asyncio
async def test_alert_notifications_and_processed_at_exist(tmp_path: Path) -> None:
    db = tmp_path / "alerts.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cols = {
            r[1]
            for r in await (
                await conn.execute("PRAGMA table_info(domain_events)")
            ).fetchall()
        }
        assert "processed_at" in cols
        names = {
            r[0]
            for r in await (
                await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='alert_notifications'"
                )
            ).fetchall()
        }
        assert "alert_notifications" in names
        acol = {
            r[1]
            for r in await (
                await conn.execute("PRAGMA table_info(alert_notifications)")
            ).fetchall()
        }
        assert {
            "id", "event_id", "event_type", "fingerprint", "kind",
            "title", "message", "severity", "status", "created_at", "acked_at",
        } <= acol
```

Also assert migration upgrades an old DB that already has `domain_events` without `processed_at` (create bare table then `apply_migrations`).

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest tests/test_alerts_schema.py -v
```

- [ ] **Step 3: Implement schema + migration**

In `schema.sql`, extend `domain_events`:

```sql
CREATE TABLE IF NOT EXISTS domain_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_domain_events_unprocessed
    ON domain_events(id) WHERE processed_at IS NULL;

CREATE TABLE IF NOT EXISTS alert_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER REFERENCES domain_events(id),
    event_type TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info'
        CHECK (severity IN ('info', 'warn', 'error')),
    status TEXT NOT NULL DEFAULT 'unread'
        CHECK (status IN ('unread', 'acked')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    acked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_status_created
    ON alert_notifications(status, created_at DESC);
```

In `migrations.py`, after intake/domain_events block: if `domain_events` exists and lacks `processed_at`, `ALTER TABLE ... ADD COLUMN processed_at TEXT` + create unprocessed index; create `alert_notifications` if missing (same DDL as schema).

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit**

```bash
git add packages/common/src/finance_common/db/schema.sql \
  packages/common/src/finance_common/db/migrations.py \
  tests/test_alerts_schema.py
git commit -m "feat(alerts): schema for notifications and outbox processed_at"
```

---

### Task 2: Domain events + alert repositories and models

**Files:**
- Create: `packages/common/src/finance_common/alerts/models.py`
- Create: `packages/common/src/finance_common/repositories/alerts.py`
- Modify: `packages/common/src/finance_common/repositories/domain_events.py`
- Create: `packages/common/src/finance_common/alerts/__init__.py`
- Test: `tests/test_alerts_repository.py`

**Interfaces:**
- Produces:
  - `async def list_unprocessed(conn, *, limit: int = 100) -> list[DomainEventRow]`
  - `async def mark_processed(conn, event_id: int, *, when: str | None = None) -> None`
  - `async def insert_notification(conn, *, event_id: int | None, event_type: str, fingerprint: str, kind: str, title: str, message: str, severity: str) -> int | None` — returns `None` on unique fingerprint conflict
  - `async def list_notifications(conn, *, status: str | None, limit: int = 100) -> list[AlertNotification]`
  - `async def ack_notification(conn, notification_id: int) -> bool`
  - dataclass `AlertNotification` / `DomainEventRow` in `alerts/models.py` (or domain_events module for event row)

- [ ] **Step 1: Failing repo tests** — insert event via `append_event`, list unprocessed, mark processed, insert notification, duplicate fingerprint → `None`, ack flips status

- [ ] **Step 2: Implement repos** — `INSERT OR IGNORE` / catch integrity for fingerprint unique; `mark_processed` sets `processed_at = datetime('now')`

- [ ] **Step 3: pytest PASS** → commit `feat(alerts): repositories for outbox drain and notifications`

---

### Task 3: AlertService route + poll_once

**Files:**
- Create: `packages/common/src/finance_common/alerts/route.py`
- Create: `packages/common/src/finance_common/alerts/service.py`
- Modify: `packages/common/src/finance_common/alerts/__init__.py`
- Test: `tests/test_alerts_service.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class RoutedAlert: fingerprint, kind, title, message, severity`
  - `def route_event(event_type: str, payload: Mapping[str, object], *, event_id: int) -> RoutedAlert | None`
  - `async def poll_once(conn: aiosqlite.Connection, *, limit: int = 100) -> int` — returns count of events processed (marked)

**Routing table (exact):**

| event_type | kind | severity | fingerprint |
|------------|------|----------|-------------|
| `budget.threshold` | `budget` | `warn` if status warn else `error` | `budget\|{ym}\|{category}\|{status}` |
| `debt.emi_due` | `emi` | `warn` | `emi\|{debt_id}\|{due_date}` |
| `credit_card.due` | `credit_card` | `warn` | `cc_due\|{card_id}\|{due_date}` |
| `intake.quarantine_created` | `intake` | `warn` | `intake.quarantine\|{candidate_id}` |
| `intake.candidate_approved` | `intake` | `info` | `intake.approved\|{candidate_id}` |
| `intake.candidate_rejected` | `intake` | `info` | `intake.rejected\|{candidate_id}` |
| `migration.quarantine_created` | `migration` | `warn` | `migration.quarantine\|{fingerprint or id from payload or event_id}` |
| other | — | — | return `None` (unknown) |

Title/message: human-readable strings from payload fields (category, rupee amounts via `/100`, debt/card name, reason). If required payload keys missing, still notify with best-effort text and fingerprint fallback `f"{event_type}|{event_id}"`.

`poll_once`:
1. `cfg = await load_project_config(conn)`
2. For each unprocessed event: parse JSON payload; `routed = route_event(...)`; if `routed is None`: mark processed; continue
3. If not `cfg.alerts_in_app_enabled`: mark processed; continue
4. `insert_notification(...)`; ignore `None` (dup fingerprint); always mark processed after successful route decision
5. On unexpected exception: log, leave unprocessed, continue to next (or break — prefer continue)

- [ ] **Step 1: Unit tests** — known types → notification; unknown → processed no row; duplicate fingerprint → one row two processed; `alerts_in_app_enabled=false` → zero rows all processed

- [ ] **Step 2: Implement** → pytest PASS → commit `feat(alerts): AlertService poll_once and routing`

---

### Task 4: Refactor budget / EMI / CC jobs to emit events

**Files:**
- Modify: `packages/api/src/finance_api/services/background_jobs.py`
- Test: `tests/test_alert_jobs_emit.py`

**Interfaces:**
- Consumes: `append_event` from `finance_common.repositories.domain_events`
- Produces: jobs no longer call `send_discord_dm` for budget/EMI/CC

**Behavior changes:**

1. `job_budget_and_alerts`: keep state gates; for each new warn/over line, `append_event(event_type="budget.threshold", payload={ym, category, status, spent_paise, budget_paise, pct})`. Remove Discord send block entirely for this job.

2. `job_emi_reminders`: same pattern → `debt.emi_due` with `{debt_id, name, due_date, days_until}`. No Discord.

3. `job_cc_due_date_alerts`: **remove early return when Discord token/uid missing** (that currently skips all work). Keep state gates; emit `credit_card.due` per card/date with `{card_id, name, due_date, when}`. No Discord.

4. Leave `job_weekly_discord` / `job_monthly_discord` as-is.

- [ ] **Step 1: Failing tests** — seed minimal budget/debt/cc fixtures (reuse patterns from other API tests); run job functions against temp DB; assert `domain_events` rows exist with expected types; monkeypatch/assert `send_discord_dm` not called (patch `finance_api.services.background_jobs.send_discord_dm`)

- [ ] **Step 2: Implement job changes** → pytest PASS → commit `feat(alerts): budget EMI CC jobs emit domain events`

---

### Task 5: HTTP API + poller registration + dashboard alerts

**Files:**
- Create: `packages/api/src/finance_api/schemas/alerts.py`
- Create: `packages/api/src/finance_api/routers/alerts.py`
- Modify: `packages/api/src/finance_api/main.py` (include router; call `poll_once` once during lifespan after ensure_database)
- Modify: `packages/api/src/finance_api/routers/dashboard.py`
- Modify: `packages/api/src/finance_api/schemas/dashboard.py` — add optional `id: int | None = None` on `AlertItem`
- Modify: `packages/api/src/finance_api/services/background_jobs.py` — `job_alert_poll` + `IntervalTrigger(seconds=90)` (or 60–120)
- Test: `tests/test_alerts_api.py`

**Endpoints:**

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/api/alerts?status=unread\|acked\|all` | default `unread`; limit default 100 |
| POST | `/api/alerts/{id}/ack` | 404 if missing; return updated row |
| GET | `/api/dashboard/alerts` | unread → `AlertItem(id, kind=title or kind, message, severity)` |

`job_alert_poll(db_path)`: open_db → `poll_once(conn)`.

Lifespan: after DB ready, `async with open_db(...) as conn: await poll_once(conn)` before/after scheduler start (either order OK; prefer before yield).

- [ ] **Step 1: API tests with TestClient** — append_event + poll_once (or hit endpoint after manual insert notification); list/ack/dashboard

- [ ] **Step 2: Implement** → pytest PASS → commit `feat(api): alerts endpoints and outbox poller`

---

### Task 6: Dashboard banner ack + Alerts page

**Files:**
- Create: `dashboard/src/pages/AlertsPage.tsx`
- Modify: `dashboard/src/components/dashboard/AlertsBanner.tsx`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/src/components/layout/AppShell.tsx` — nav item under Operations (near quarantine), label `Alerts`, icon `Bell`
- Modify: `dashboard/src/lib/api.ts` — `fetchAlerts`, `ackAlert`
- Modify: `dashboard/src/types/api.ts` — `AlertNotification`, extend dashboard alert with `id?`
- Modify: `dashboard/src/pages/DashboardPage.tsx` — pass ack handler if banner needs mutation

**UI behavior:**
- Banner: show unread; each row has Ack button calling `POST /api/alerts/{id}/ack`; invalidate `['dashboard-alerts']` and `['alerts']`
- `/alerts`: PageHero + filter pills (Unread / Acked / All) + list with Ack for unread
- Match existing Panel / button styles (same as quarantine/recon pages — no new design system)

- [ ] **Step 1: Wire types + api helpers**
- [ ] **Step 2: AlertsPage + nav + route**
- [ ] **Step 3: Banner ack**
- [ ] **Step 4: Manual smoke** — `npm run build --prefix dashboard` (or tsc) must succeed
- [ ] **Step 5: Commit** `feat(dashboard): alerts page and banner ack`

---

### Task 7: Acceptance + roadmap

**Files:**
- Modify: `docs/superpowers/plans/2026-08-10-double-entry-money-engine-roadmap.md` — mark P5 done with plan/design links
- Test: ensure full suite green; optional `tests/test_alerts_acceptance.py` smoke: emit budget event → poll → unread → ack

- [ ] **Step 1: Run**

```bash
uv run pytest tests/ -q --tb=line
uv run python scripts/ci_check_ledger_writes.py
```

Expected: all pass; CI script clean.

- [ ] **Step 2: Update roadmap P5 row** to ✅ Done with links to this plan + design + note acceptance.

- [ ] **Step 3: Commit** `docs: P5 AlertService acceptance notes`

---

## Out of scope reminders

- Discord channel adapter
- Digest → notifications
- `recon.period_*` events
- Extracting `packages/alert`

## Self-review (plan vs spec)

| Spec section | Task |
|--------------|------|
| §4 data model | Task 1 |
| §5 AlertService | Tasks 2–3 |
| §6.1 job emitters | Task 4 |
| §6.2 existing events | Task 3 routing |
| §6.3 unknown | Task 3 |
| §7 HTTP | Task 5 |
| §8 UI | Task 6 |
| §9 tests | Tasks 1–7 |
| §11 acceptance | Task 7 |
| Digests unchanged | Task 4 explicit leave-as-is |
| CC job without Discord gate | Task 4 |
