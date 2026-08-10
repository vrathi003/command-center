# P5 AlertService Acceptance Report

**Branch:** `feature/double-entry-ledger-p5` · **Date:** 2026-08-11

## Verification

- P5 alert suite: **30 passed**
  `uv run pytest tests/test_alerts_*.py tests/test_alert_jobs_emit.py -q`
- Ledger write guard: **passed**
  `uv run python scripts/ci_check_ledger_writes.py`
- Full suite: **368 passed**
  `uv run pytest tests/ -q --tb=line`

All pytest runs emitted five PyMuPDF SWIG deprecation warnings; no test failures or P5 regressions occurred.

## Scope

P5 delivers the standalone AlertService: `alert_notifications` schema + outbox `processed_at`, event routing and `poll_once` drain, budget/EMI/CC job emitters (Discord removed from those three jobs), HTTP list/ack endpoints + 90s poller, and dashboard banner ack + `/alerts` page. Digests unchanged; Discord channel adapter deferred.

## Commits (Tasks 1–6)

| Task | Commit | Summary |
|------|--------|---------|
| 1 | `6eecbb0` | Schema: `processed_at`, `alert_notifications` |
| 2 | `0a24c27` | Repositories + models |
| 3 | `9e9ca3f` | `route_event` + `poll_once` |
| 4 | `8313cda` | Budget / EMI / CC jobs emit events |
| 5 | `306381e` | HTTP API + poller registration |
| 5 fix | `f12ab16` | Idempotent ack via `get_notification` |
| 6 | `2e09b38` | Dashboard banner ack + Alerts page |

## Known Issues / Out of Scope

- Discord channel adapter not implemented (in-app only).
- Digest jobs still Discord-only; not routed through AlertService.
- `recon.period_*` events not emitted.
- No unread badge on Alerts nav item.
- CC due payload omits outstanding balance (was Discord-only decoration).
