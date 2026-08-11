# Task 4 — Hybrid EMI auto-post job

- **`post_emi_and_advance`** shared by `record-emi` router and daily job: amort split → `build_emi_payment` → ledger post → sync balance → advance `next_emi_date`.
- **`auto_advance_debt` (double_entry):** when `account_id` + `payment_account_id` + `emi_paise` and due → auto-post (`source=job`); else skip (no balance scrub).
- **Legacy engine:** unchanged `compute_emi_advance` balance scrub.
- **`job_emi_auto_advance`:** docstring updated; still calls `auto_advance_active_debts`.
- Tests: 3 new in `test_debt_emi_ledger.py` — auto-post, skip without bank link, legacy scrub. 13 EMI-related tests pass.
- Commit: `feat(debt): hybrid EMI auto-post job`
