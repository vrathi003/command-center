# Gmail Inbox ↔ Intake Alignment — Acceptance Report

**Branch:** `feature/gmail-intake-alignment`  
**Date:** 2026-08-11  
**Spec:** `docs/superpowers/specs/2026-08-11-gmail-intake-alignment-design.md`  
**Plan:** `docs/superpowers/plans/2026-08-11-gmail-intake-alignment.md`

## Verification

| Check | Result |
|-------|--------|
| Full suite | **370 passed**, 5 warnings (PyMuPDF SWIG deprecations) — `uv run pytest tests/ -q --tb=line` |
| Ledger write guard | **passed** — `uv run python scripts/ci_check_ledger_writes.py` |
| Gmail intake tests | **36 passed** — `test_email_staging_schema`, `test_email_staging_repo`, `test_email_bridge`, `test_email_inbox_ledger` |

## Spec §7 checklist

| # | Requirement | Status |
|---|-------------|--------|
| 1 | Schema: `quarantined` status + `intake_candidate_id` | ✅ Task 1 |
| 2 | Approve → POSTED writes candidate + staging approved | ✅ `email_bridge` + API |
| 3 | Soft-dupe without force → quarantined + `intake.quarantine_created` | ✅ 200 response, not 409 |
| 4 | Force approve posts despite soft-dupe | ✅ |
| 5 | Transfer approve; soft-dupe quarantines both legs | ✅ |
| 6 | Reject staging rejects linked pending candidate | ✅ |
| 7 | Undo clears `ledger_transaction_id`, resets pending | ✅ |
| 8 | Intake candidate approve/reject syncs staging | ✅ `intake.py` sync-back |
| 9 | `source=email`; external_key prefix `gmail:` | ✅ |

## Self-review vs spec

| Spec | Delivered |
|------|-----------|
| §4 schema | `intake_candidate_id` FK; `quarantined` status |
| §5 approve/transfer | `email_bridge` hybrid ingest + force post |
| §5.3 sync-back | Intake approve/reject updates linked staging |
| §6 UI | Quarantined badge, stats, quarantine desk link, force approve |
| §7 tests | 36 targeted + full suite green |
| Sync unchanged | Gmail sync → staging only; no auto-ingest |

## Commits (oldest → newest)

```
d67fd6a docs: add Gmail inbox Intake alignment design and plan
32a9f61 feat(email): staging quarantined status and candidate link
d4abedb feat(email): staging repo candidate link and ledger reset
da3bcc9 fix(email): set_status preserves omitted link fields
e22ed1f feat(intake): email_bridge hybrid approve and transfer
76c0129 feat(api): email inbox uses intake bridge
e625d61 feat(dashboard): email inbox quarantined status
```

## Notes

- Legacy `ledger_engine` path unchanged (`transactions` insert).
- P5 AlertService / Discord channel out of scope; quarantine events still emitted for future drain.
- `uv.lock` modified locally — excluded from docs commit.

## Acceptance

**PASS** — double_entry email approve/transfer route through the hybrid Intake bridge; quarantines visible on staging + quarantine desk; glue bugs fixed; §7 tests pass.
