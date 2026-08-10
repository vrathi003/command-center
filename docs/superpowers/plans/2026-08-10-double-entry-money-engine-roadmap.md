# Double-Entry Money Engine — Phase Roadmap

**Spec:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md`

Implement **one phase plan at a time**. Each plan must leave the repo green and usable.

| Phase | Plan | Deliverable | Depends on |
|-------|------|-------------|------------|
| **P1** | [`2026-08-10-double-entry-money-engine-p1.md`](./2026-08-10-double-entry-money-engine-p1.md) | Ledger schema, LedgerService, builders, balances, budget/cash lenses, project_config, Discord off, ledger API | — |
| **P2** ✅ Done | [`2026-08-10-double-entry-money-engine-p2.md`](./2026-08-10-double-entry-money-engine-p2.md) · [acceptance report](../../../.superpowers/sdd/task-11-report.md) | IntakeService, candidates, quarantine, dedupe, email/file/CC→LedgerService | P1 |
| **P3** ✅ Done | [`2026-08-10-double-entry-money-engine-p3.md`](./2026-08-10-double-entry-money-engine-p3.md) · [design](../specs/2026-08-10-double-entry-money-engine-p3-design.md) · [acceptance report](../../../.superpowers/sdd/task-10-report.md) | In-place migration, full cutover, legacy archive, Settings dry-run/apply | P1+P2 |
| **P4** | [`2026-08-10-double-entry-money-engine-p4.md`](./2026-08-10-double-entry-money-engine-p4.md) · [design](../specs/2026-08-10-double-entry-money-engine-p4-design.md) | ReconciliationService, dedicated recon store, suggest+confirm, soft close, workspace UI | P3 |
| **P5** | write after P1 (can parallel P2) | Standalone AlertService + in-app channel; later Discord channel | P1 (events/outbox) |
| **P6** | write after P3 | EMI split polish, NW completeness, investment posting alignment | P3 |

**Execution rule:** Do not start P3 until P1 golden lens tests pass on real migrated samples in a dry-run.
