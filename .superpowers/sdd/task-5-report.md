# Task 5 Report — HTTP API + poller registration + dashboard alerts

**Status:** Complete

**Commit:** `feat(api): alerts endpoints and outbox poller`

## Delivered

| Area | Change |
|------|--------|
| Schemas | `AlertNotificationResponse`; `AlertItem.id: int \| None` |
| Router | `GET /api/alerts`, `POST /api/alerts/{id}/ack` |
| Dashboard | `GET /api/dashboard/alerts` maps unread notifications |
| Lifespan | `poll_once(conn)` after DB ready in `main.py` |
| Scheduler | `job_alert_poll` every 90s via `IntervalTrigger` |
| Tests | `tests/test_alerts_api.py` — 5 TestClient cases |

## Endpoints

- **GET `/api/alerts?status=unread|acked|all&limit=100`** — list notifications (default unread).
- **POST `/api/alerts/{id}/ack`** — ack; 404 if missing or already acked; returns updated row.
- **GET `/api/dashboard/alerts`** — unread only; `kind` = `title or kind`, includes `id` for banner ack.

## Tests

```bash
uv run pytest tests/test_alerts_api.py -v
# 5 passed
```

Coverage: list default/filter, ack 404, dashboard unread→empty after ack, lifespan startup poll.

## Concerns / follow-ups

- ~~Ack response fetches via `list_notifications(status="acked")` — add `get_notification(id)` if history grows.~~ **Fixed** — see review fix below.
- ~~Re-ack returns 404 (same as missing); could use 409 later.~~ **Fixed** — idempotent 200 returns existing acked row.
- `uv.lock` not committed (per task constraint).
- Task 6: React `/alerts` page + banner ack wiring still pending.

---

## Review fix — ack via `get_notification` (idempotent)

**Status:** Complete  
**Commit:** `fix(api): ack alerts via get_notification idempotent`

### Changes

| Area | Change |
|------|--------|
| Repository | Added `get_notification(conn, notification_id) -> AlertNotification \| None` |
| Router | `POST /api/alerts/{id}/ack`: get → 404 if missing; ack+re-get if unread; return as-is if already acked |
| Tests | `test_ack_alert_returns_updated_body`, `test_ack_alert_reack_is_idempotent`; repo test covers `get_notification` |

### Tests

```bash
uv run pytest tests/test_alerts_api.py tests/test_alerts_repository.py -v
# 10 passed
```

Coverage: ack body on success, re-ack idempotent 200 with same id/acked_at, missing still 404.
