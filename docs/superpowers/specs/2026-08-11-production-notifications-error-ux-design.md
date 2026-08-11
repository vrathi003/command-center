# Production Notifications & Error UX Design

**Date:** 2026-08-11  
**Status:** Approved for planning  
**Owner:** Vaibhav  

---

## 1. Goal

Make every interactive API failure and important success **visible in the UI**, and surface **background/system failures** in a persistent Notifications inbox so the user learns about breakage without re-trying the feature. Target FAANG-grade clarity: clear message, actionable when possible, no silent mutations.

## 2. Locked decisions

| Topic | Choice |
|-------|--------|
| Split | **C** — Ephemeral toasts for interactive actions; persistent inbox for background/system only |
| Success toasts | **B** — Important actions only (approve, import, sync, delete, transfer, bulk); routine form saves quiet unless they fail |
| Inbox content | **B** — Existing domain alerts + operational/job failures (not a copy of every interactive API error) |
| Architecture | Harden existing AlertService + `/alerts`; add toast layer on the dashboard (do not invent a second notifications stack) |
| Immediate bug | Email Inbox approve 422 must surface; DE approve must require/select `account_id` when missing |

## 3. Problem diagnosis (current)

- No toast library; React Query has no global mutation error handler.
- `parseJson` throws raw response text (`{"detail":"..."}`), often unreadable.
- Email Inbox approve/reject/bulk/transfer: often **no `onError` UI** → silent failure (user’s Network 422 on `approve`).
- `/alerts` covers domain events (budget/EMI/CC/intake/digest) but **not** job crashes / Gmail auth / backup failures.
- Background jobs: many `logger.exception` only.

Likely approve 422 under `double_entry`: missing `account_id` / `suggested_account_id` → `"account_id is required to approve"` (UI never sends account).

## 4. Architecture

```
Interactive mutation (dashboard)
        │
        ▼
apiFetch → parseApiError (normalized)
        │
        ▼
React Query MutationCache
  onError  → error toast (always)
  onSuccess → success toast if allowlisted
        │
        ▼
Page-specific UI may still show inline detail (optional)

Background / ops failure
        │
        ▼
domain_events.append_event(ops.* | existing kinds)
        │
        ▼
AlertService.poll_once → alert_notifications
        │
        ▼
/alerts (Notifications) + nav unread badge + dashboard banner
```

### 4.1 Error contract (API → UI)

Normalize in the dashboard client (and prefer structured `detail` from FastAPI):

```ts
type ApiError = {
  status: number
  message: string       // human-readable
  detail?: unknown      // raw FastAPI detail for debugging
  code?: string         // optional machine code when we add it
}
```

Rules:
- Prefer `detail` string, or first validation message from `detail[]`, else `HTTP {status}`.
- Never show a raw JSON blob as the only message.
- 401 continues to trigger logout via existing `finance:unauthorized`.

Optional later (not v1): `X-Request-Id` on API responses echoed in toast “Copy details”.

### 4.2 Toast layer (ephemeral)

- Library: **sonner** (stable, lightweight, fits React 19) or equivalent already in ecosystem — one global `<Toaster />` in app shell.
- **Errors:** always toast for failed mutations; duration longer / dismissible; include short title (“Approve failed”) + message.
- **Success allowlist** (v1): approve / reject, import, Gmail/statement sync, delete / bulk-delete, transfer create, bulk approve. CRUD create/update on settings-like forms: success quiet; errors still toast.
- Queries (`useQuery`): keep `PageError` for full-page loads; optional toast only if a background refetch fails after prior success (v1 optional — default off to reduce noise).

Global wiring: `QueryClient` `MutationCache` default `onError` / `onSuccess` so pages cannot silently forget. Pages may override with richer copy but must not swallow without UI.

### 4.3 Notifications inbox (persistent)

Extend existing `/alerts` (nav label → **Notifications** if copy change is cheap; route can stay `/alerts`).

| Kind | Source | Examples |
|------|--------|----------|
| Existing | Already routed | budget, emi, credit_card, intake, migration, digest |
| **ops** (new) | Jobs / sync / integrity | `ops.job_failed`, `ops.gmail_auth_failed`, `ops.backup_failed`, `ops.ledger_integrity` |

Routing: add handlers in `finance_common.alerts.route` for `ops.*` → `kind="ops"`, severity `error` (or `warn` when recoverable).

Job wrapper pattern (conceptual):

```python
async def run_job(name: str, fn, conn, ...):
    try:
        await fn(...)
    except Exception as exc:
        await append_event(conn, "ops.job_failed", {"job": name, "error": str(exc)[:500]})
        raise  # keep logs
```

Gmail `invalid_grant`: emit `ops.gmail_auth_failed` with re-auth hint (link to docs / setup script message).

Unread badge on nav; dashboard banner keeps showing recent high-severity items.

### 4.4 Email Inbox approve fix (same initiative)

1. Parse and toast 422 `detail` (via global handler + local if needed).
2. When `ledger_engine=double_entry` and row has no `suggested_account_id`, **block approve** until user picks an account; send `account_id` in approve body.
3. Bulk approve: skip/flag rows missing account; report count in toast (“3 approved, 2 need account”).

## 5. Phasing

| Phase | Deliverable |
|-------|-------------|
| **P1** | Error normalization + global toasts + Email Inbox approve UX (account + visible errors) |
| **P2** | Ops event types + job failure emission + Notifications copy/badge polish |
| **P3** | Sweep remaining pages: remove `window.alert`, rely on toast policy; success allowlist coverage |

P1 alone stops silent approve failures. P2 meets “know without waiting to use the feature.”

## 6. Testing

- Unit: `parseApiError` for string detail, validation array, empty body.
- Component/integration: mutation failure shows toast (Testing Library + QueryClient).
- API: approve without account under DE → 422 with stable message; with account → 201.
- Alert route: `ops.job_failed` → notification row; `poll_once` inserts once (fingerprint dedupe).

## 7. Out of scope (v1)

- External APM (Sentry/Datadog)
- Discord DM for every ops event (optional later; digests already Discord)
- Request-id tracing end-to-end
- Persisting interactive API errors into the inbox (rejected as C)

## 8. Success criteria

1. Approving a staged email without an account shows a clear error toast (and account picker when DE).
2. Any allowlisted mutation failure shows a toast with human-readable reason.
3. A forced job failure (test) appears under Notifications without opening that feature.
4. Gmail `invalid_grant` produces an ops notification with re-auth guidance after next sync attempt.
