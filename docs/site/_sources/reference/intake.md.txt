# Intake (stub)

**Status:** stub — narrative lives in {doc}`../workflows/email-to-ledger` and
{doc}`../workflows/quarantine-approve`.

## Key modules

| Module | Role |
|--------|------|
| ``finance_common.intake.service`` | Ingest / quarantine / approve orchestration |
| ``finance_common.intake.posting_plan`` | ``plan_postings``, ``plan_transfer`` |
| ``finance_common.intake.email_bridge`` | Staging ↔ candidate bridge for Email Inbox |
| ``finance_common.intake.dedupe`` | Soft duplicate detection |

## Tables

``intake_candidates``, links from ``email_transaction_staging.intake_candidate_id``.
