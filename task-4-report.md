# Task 4 Email Inbox Uses Intake Bridge

- `email_inbox.py` double_entry approve/transfer now delegate to `email_bridge`; errors mapped 404/409/422.
- Soft-dupe without force returns **200** + `status=quarantined` + `intake_candidate_id` (no 409).
- `StagedEmailOut` + stats include `intake_candidate_id` / `quarantined` count.
- Reject staging rejects linked pending candidate + event; undo uses `reset_by_ledger_transaction_ids`.
- `intake.py` approve/reject syncs linked staging rows via `email_staging_id` + `get_by_intake_candidate_id`.
- Force approve updates existing quarantine candidate via `update_candidate_status(..., posted)`.
- 9 new/updated API tests + 1 bridge test — 27 related tests pass.
- Commit: `feat(api): email inbox uses intake bridge`
