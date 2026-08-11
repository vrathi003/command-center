# Production Notifications & Error UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Visible toasts for interactive API errors/important successes; persistent Notifications for domain + ops failures; Email Inbox approve no longer silent under DE.

**Architecture:** Normalize API errors in `dashboard/src/lib/apiError.ts`; mount Sonner + React Query `MutationCache` defaults; extend AlertService with `ops.*` events from jobs; fix Email Inbox account + approve feedback.

**Tech Stack:** React 19, TanStack Query 5, Sonner, FastAPI, existing `finance_common.alerts` / `domain_events`

**Spec:** `docs/superpowers/specs/2026-08-11-production-notifications-error-ux-design.md`

## Global Constraints

- Toasts = interactive only; inbox = background/system + existing domain alerts (not every UI error)
- Success toasts only for allowlisted important actions
- Never show raw JSON `{"detail":...}` as the only user message
- Prefer extending `/alerts` over a second notifications stack

---

### Task 1: API error normalization (dashboard)

**Files:**
- Create: `dashboard/src/lib/apiError.ts`
- Modify: `dashboard/src/lib/api.ts` (`parseJson`)
- Test: `dashboard` unit via vitest if present, else `tests` not required — add `dashboard/src/lib/apiError.test.ts` only if vitest exists; otherwise pytest-free pure TS tested by build

**Interfaces:**
- Produces: `class ApiClientError extends Error { status, message, detail }`, `parseApiError(res, text): ApiClientError`, `formatErrorMessage(err: unknown): string`

- [ ] **Step 1:** Implement parsers for string `detail`, `{detail: string}`, `{detail: [{msg}]}`, fallback `HTTP {status}`
- [ ] **Step 2:** `parseJson` throws `ApiClientError`
- [ ] **Step 3:** `npm run build` in dashboard passes

---

### Task 2: Sonner + global mutation toasts

**Files:**
- Modify: `dashboard/package.json` (add `sonner`)
- Create: `dashboard/src/lib/toastPolicy.ts` (success allowlist by mutation meta)
- Modify: `dashboard/src/providers/QueryProvider.tsx`
- Modify: `dashboard/src/App.tsx` or shell — mount `<Toaster />`

**Interfaces:**
- Mutation meta: `{ successMessage?: string, silent?: boolean }`
- Default `onError`: toast.error(formatErrorMessage(err))
- Default `onSuccess`: toast.success if `meta.successMessage` set

- [ ] **Step 1:** `npm install sonner` in `dashboard/`
- [ ] **Step 2:** Wire QueryClient MutationCache + Toaster
- [ ] **Step 3:** Smoke: trigger a failing mutation → toast appears

---

### Task 3: Email Inbox approve UX (DE account + feedback)

**Files:**
- Modify: `dashboard/src/pages/EmailInboxPage.tsx`
- Modify: `dashboard/src/lib/api.ts` `approveEmailTransaction` if needed
- Test: manual / existing API tests; add pytest if approve body account covered

- [ ] **Step 1:** EditState + form include `accountId`; send `account_id` on approve
- [ ] **Step 2:** Block approve when DE and no account; clear toast/error copy
- [ ] **Step 3:** `approveMut` / bulk / transfer set `meta.successMessage`; rely on global onError
- [ ] **Step 4:** Verify 422 without account shows human message

---

### Task 4: Ops alert routing + job failures (P2)

**Files:**
- Modify: `packages/common/src/finance_common/alerts/route.py`
- Modify: `packages/api/src/finance_api/services/background_jobs.py` (wrapper / key jobs)
- Modify: `packages/api/src/finance_api/services/gmail_sync.py` or statement fetch catch `invalid_grant`
- Modify: `dashboard/src/pages/AlertsPage.tsx` / nav label → Notifications (copy)
- Test: `tests/test_alerts_service.py` for `ops.job_failed`, `ops.gmail_auth_failed`

- [ ] **Step 1:** Route `ops.job_failed`, `ops.gmail_auth_failed`, `ops.backup_failed`
- [ ] **Step 2:** Emit from job exceptions + Gmail auth failure path
- [ ] **Step 3:** Tests green; unread badge still works

---

### Task 5: Allowlist sweep + remove window.alert (P3)

**Files:** high-traffic mutation pages (Transactions, Import, Email sync, Debt delete, etc.)

- [ ] **Step 1:** Add `meta.successMessage` on allowlisted mutations
- [ ] **Step 2:** Replace `window.alert` with toasts where trivial
- [ ] **Step 3:** Full pytest + dashboard build; push `main`

---

## Commit strategy

- After Task 1–2: `feat(dashboard): add ApiClientError and global mutation toasts`
- After Task 3: `fix(email-inbox): require account on DE approve and surface errors`
- After Task 4: `feat(alerts): emit ops failures into Notifications inbox`
- After Task 5: `chore(dashboard): success toast allowlist and drop window.alert`
