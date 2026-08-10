# Double-Entry Money Engine P5 — AlertService Design

**Date:** 2026-08-11  
**Status:** Approved for implementation planning  
**Owner:** Vaibhav  
**Parent spec:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md` §8  
**Depends on:** P1 (domain event outbox) + existing job/intake/migration emitters

---

## 1. Goal

Ship a **standalone AlertService** that drains the SQLite domain-event outbox into durable **in-app notifications**, with ack + history UI. Scheduled budget / EMI / CC-due jobs **emit events only** (no direct Discord DMs). Discord remains a future channel; digests stay untouched.

AlertService never performs budget math, ledger writes, Gmail parsing, or recon matching.

## 2. Locked decisions

| Topic | Choice |
|-------|--------|
| Scope | In-app delivery + refactor alert jobs to emit events; no Discord channel in P5 |
| Producers | Budget / EMI / CC due jobs + existing intake & migration outbox events |
| Package home | `finance_common/alerts/` (extract to `finance_alert` later if needed) |
| Delivery | Outbox poller (`processed_at`); startup + APScheduler tick |
| UI | Dashboard unread banner + dedicated `/alerts` page |
| Digests | Out of scope (weekly/monthly Discord jobs unchanged / no-op when Discord off) |
| Architecture | Dedicated `alert_notifications` table + `domain_events.processed_at` |

## 3. Architecture

```
Jobs / Intake / Migration
        │ append_event(...)
        ▼
 domain_events (+ processed_at)
        │ AlertService.poll_once()  [API startup + APScheduler ~1–2 min]
        ▼
 Route by event_type → in_app channel (if alerts.in_app.enabled)
        │ fingerprint unique + emit-side job state gates
        ▼
 alert_notifications  →  GET /alerts · POST /alerts/{id}/ack
        │
        ├── GET /dashboard/alerts → AlertsBanner (unread)
        └── /alerts page (history + ack)
```

## 4. Data model

### 4.1 `domain_events` (extend)

| Column | Notes |
|--------|--------|
| id | existing PK |
| event_type | existing |
| payload_json | existing |
| created_at | existing |
| **processed_at** | **NEW** `TEXT NULL` — set when AlertService finishes handling the row |

Index: unprocessed rows (`processed_at IS NULL`) ordered by `id`.

### 4.2 `alert_notifications`

| Column | Notes |
|--------|--------|
| id | PK |
| event_id | FK → domain_events.id (nullable if ever needed for synthetic rows; P5 always set) |
| event_type | denormalized for filters |
| fingerprint | UNIQUE — hard dedupe key |
| kind | short label for UI (e.g. `budget`, `emi`, `credit_card`, `intake`, `migration`) |
| title | short headline |
| message | body text |
| severity | `info` \| `warn` \| `error` |
| status | `unread` \| `acked` |
| created_at | |
| acked_at | nullable |

## 5. AlertService

Package: `finance_common.alerts`

| Method | Behavior |
|--------|----------|
| `poll_once(conn, *, limit=100)` | Select unprocessed events by id ASC; for each: route → insert or skip → set `processed_at`. Unknown types: mark processed, no notification. |
| (internal) `route(event)` | Map `event_type` → kind/severity/title/message/fingerprint |
| (internal) `deliver_in_app` | If `project_config.alerts.in_app.enabled`; insert notification; ignore unique fingerprint conflicts (still mark event processed) |

**Config:** Respect `alerts.in_app.enabled`. When false: mark events processed, insert nothing. Discord channel flags ignored in P5 (no Discord adapter).

**Non-responsibility:** No ledger imports/writes; no direct Discord HTTP.

**Poller scheduling:** Call `poll_once` from API lifespan startup and an APScheduler interval job (~60–120s). Structured logs for delivered / skipped / unknown.

**Failure:** Insert/route errors are logged; leave `processed_at` null so the next tick retries. Unique fingerprint conflict is not a failure.

## 6. Event catalog

### 6.1 Jobs (refactor)

Stop calling `send_discord_dm` for these jobs. Keep existing JSON state keys in `settings` so the job does not re-append the same logical alert every run. Emit **one domain event per alert line**.

| Job | `event_type` | Fingerprint |
|-----|--------------|-------------|
| Budget warn / over | `budget.threshold` | `budget\|{ym}\|{category}\|{warn\|over}` |
| EMI due within 0–3 days | `debt.emi_due` | `emi\|{debt_id}\|{due_date}` |
| CC due today / tomorrow | `credit_card.due` | `cc_due\|{card_id}\|{due_date}` |

Payload must include fields needed to render title/message (category, amounts in paise, debt/card name, dates, status).

**Out of scope:** weekly digest, monthly summary, and any other Discord-only jobs — leave as-is.

### 6.2 Existing outbox events (route only)

| `event_type` | Notes |
|--------------|--------|
| `intake.quarantine_created` | warn/error severity |
| `intake.candidate_approved` | info |
| `intake.candidate_rejected` | info |
| `migration.quarantine_created` | warn |

Fingerprint: prefer stable ids from payload (candidate id, migration item id); else `event_type|{event_id}` so each outbox row notifies at most once.

### 6.3 Unknown types

Mark `processed_at`, do not create a notification (forward-compatible with recon/other emitters).

## 7. HTTP API

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/api/alerts` | Query `status=unread\|acked\|all` (default unread); newest first; capped limit |
| POST | `/api/alerts/{id}/ack` | Set status=acked, acked_at=now |
| GET | `/api/dashboard/alerts` | Map unread notifications → existing `DashboardAlerts` / `AlertItem` shape |

Router may live under `finance_api/routers/alerts.py`; dashboard endpoint stays but is backed by AlertService/repo instead of returning `[]`.

## 8. Dashboard UI

- **AlertsBanner** (home): unread notifications; ack control per item; invalidate alert queries on ack.
- **`/alerts` page** (nav): history with unread / acked / all filter; ack actions.
- No new Discord settings UI in P5; existing `project_config` keys remain.

## 9. Testing

1. Migration creates `alert_notifications` and `domain_events.processed_at`.
2. Poller: shaped budget/EMI/CC events → unread rows; unknown type → processed, zero rows; duplicate fingerprint → single notification, both events processed.
3. Jobs: budget / EMI / CC emit via `append_event` and do not call `send_discord_dm`.
4. API: list + ack; dashboard alerts reflects unread.
5. `alerts.in_app.enabled=false` → events processed, zero notifications.
6. AlertService modules must not import ledger write APIs (mirror ledger-write CI mindset where practical).

## 10. Out of scope (later)

- Discord Alert channel adapter (`discord.alerts.enabled`)
- Digest → notification conversion
- Recon events (`recon.period_*`) delivery
- Email channel
- Extract package rename to `finance_alert`

## 11. Acceptance

P5 is done when:

1. Unprocessed domain events from §6 drain into in-app notifications under the poller.
2. Budget / EMI / CC jobs no longer DM Discord; they only append events.
3. User can see unread alerts on the dashboard, manage history on `/alerts`, and ack.
4. Tests in §9 pass; Discord remains off by project config without breaking the alert path.
