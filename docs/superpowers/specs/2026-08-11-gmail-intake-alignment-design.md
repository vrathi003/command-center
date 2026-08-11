# Gmail Inbox ↔ Intake Alignment Design

**Date:** 2026-08-11  
**Status:** Approved for implementation  
**Owner:** Vaibhav  
**Parent:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md` §6 (Intake)  
**Depends on:** P1–P2 (LedgerService + IntakeService)

---

## 1. Goal

Align the **human Email Inbox approve path** with IntakeService so Gmail-reviewed transactions create proper `intake_candidates`, emit domain events on quarantine, and stay consistent with the money-engine boundary. **Keep Gmail sync → `email_transaction_staging` as the review desk** (no auto-ingest on sync).

## 2. Locked decisions

| Topic | Choice |
|-------|--------|
| Sync | Unchanged — staging only |
| Approve path | Hybrid: `ingest()` first; `force=true` → direct LedgerService post |
| Transfers | Same hybrid; human transfer uses `plan_transfer` + post when not quarantined |
| Quarantine UX | Staging status `quarantined` + `intake_candidate_id`; link to quarantine desk |
| Glue | `Candidate.source=email`; undo clears `ledger_transaction_id`; reject links candidates |
| Auto-ingest on sync | Out of scope |
| Discord / AlertService channel | Out of scope (P5); quarantine events still appended for future drain |

## 3. Architecture

```
Gmail sync (unchanged)
        │
        ▼
email_transaction_staging (pending)
        │ Approve / Approve-as-transfer
        ▼
email_bridge → Candidate(s)
        │
        ├─ force=false → ingest() or transfer soft-dupe gate
        │     POSTED / NOOP  → staging approved + ledger_transaction_id
        │     QUARANTINED    → staging quarantined + intake_candidate_id
        │
        └─ force=true  → plan_postings | plan_transfer + ledger_service.post
                          → staging approved; candidate row posted/updated
```

Package helper: `finance_common/intake/email_bridge.py` (map staging → Candidate; orchestrate approve/transfer outcomes). Routers stay thin.

**Non-responsibility:** AlertService delivery, Gmail parsing changes, CC statement fetch (already uses `ingest`).

## 4. Data model

### 4.1 `email_transaction_staging`

| Change | Notes |
|--------|--------|
| `status` | Allow `pending`, `approved`, `rejected`, **`quarantined`** |
| `intake_candidate_id` | NEW nullable FK → `intake_candidates(id)` |

### 4.2 Candidate / external keys

- `Candidate.source` = **`"email"`** (schema CHECK).
- `make_external_key(source=..., provider_id=gmail_message_id)` keeps prefix **`"gmail"`** for provider keys so existing posted ledger rows remain idempotent (`gmail:{message_id}`). Document this dual: intake source ≠ key prefix.

### 4.3 Repo glue

- `reset_by_transaction_ids` / undo: also clear `ledger_transaction_id` and reset status to `pending` (and clear `intake_candidate_id` when resetting).
- Reject staging: if `intake_candidate_id` points at a `pending` candidate, mark that candidate `rejected` + `intake.candidate_rejected` event.

## 5. Approve flows (`double_entry`)

### 5.1 Single-item approve

1. Load staging; allow status `pending` or (`quarantined` + `force`).
2. Build Candidate: `source=email`, `email_staging_id`, confidence `1.0` (human-reviewed), accounts/category from body/row.
3. If `force=false`: `ingest(conn, candidate)`.
   - `POSTED` → staging `approved` + `ledger_transaction_id`
   - `NOOP` → staging `approved` + existing ledger id
   - `QUARANTINED` → staging `quarantined` + `intake_candidate_id` (id returned); HTTP **200** with updated staging (not 409). UI shows badge + link.
4. If `force=true`: soft-dupe ignored; `plan_postings` + `ledger_service.post`; `save_candidate(..., status=posted)` (or update existing quarantine candidate to posted); staging `approved`.

Legacy engine path unchanged (`transactions` insert).

### 5.2 Approve-as-transfer

1. Both legs must be `pending` or both force-eligible.
2. Soft-dupe (without force) on from-account → create transfer-oriented pending candidate (quarantine reason `possible_duplicate` or `possible_transfer`), set **both** staging rows `quarantined` with same or paired `intake_candidate_id` (prefer one candidate on debit staging; credit staging stores same id or null + narration link — **prefer both rows share one `intake_candidate_id`**).
3. Otherwise / force: `plan_transfer` + `post` with `source=email` on plan metadata; external_key `gmail:{debitMsg}:{creditMsg}`; mark both staging `approved` with same `ledger_transaction_id`; save posted candidate linked to debit `email_staging_id`.

### 5.3 Quarantine desk sync-back

When intake `POST /candidates/{id}/approve` or reject runs and candidate has `email_staging_id`:

- Approve → staging `approved` + `ledger_transaction_id`
- Reject → staging `rejected`

## 6. API / UI

- `StagedEmailOut`: add `intake_candidate_id`, status may be `quarantined`.
- Email Inbox: filter/badge for quarantined; link to `/transactions/quarantine` (candidate id query if supported, else desk).
- Approve response on quarantine: 200 + body (replace soft-dupe-only 409 for the non-force ingest path). Force remains for explicit post.
- Stats counts include `quarantined`.

## 7. Testing

1. Schema migration: `quarantined` status + `intake_candidate_id`.
2. Approve → POSTED writes candidate + staging approved.
3. Approve soft-dupe without force → staging quarantined + candidate + `intake.quarantine_created`.
4. Approve force → posts despite soft-dupe.
5. Transfer approve posts both legs; soft-dupe without force quarantines.
6. Reject staging rejects linked pending candidate.
7. Undo clears `ledger_transaction_id` and resets pending.
8. Intake candidate approve/reject updates linked staging.
9. `source=email` on candidates; external_key still `gmail:…`.

## 8. Out of scope

- Auto-ingest on Gmail sync
- Parser / OAuth / historical sync changes
- Discord alert channel
- Statement-import Gmail PDF path
- Merging P5 AlertService (events still useful when P5 lands)

## 9. Acceptance

Done when double_entry email approve/transfer go through the hybrid Intake bridge, quarantines are visible on staging + quarantine desk, glue bugs are fixed, and §7 tests pass.
