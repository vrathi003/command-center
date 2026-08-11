# Quarantine approve

When intake cannot safely auto-post, a row appears as an ``intake_candidates`` entry
(``status=pending``, with ``quarantine_reason``).

## Modal fields

| Field | Use |
|-------|-----|
| Account / Account override | Becomes ``suggested_account_id`` for planning |
| Category | Expense category on the P&L leg |
| Approve as transfer | Uses ``plan_transfer`` instead of ``plan_postings`` |
| To account | Required when transfer is checked |

## Planner outcomes (``plan_postings``)

| Account class | Direction | Result |
|---------------|-----------|--------|
| ``asset_cash`` | out | Bank expense |
| ``asset_cash`` | in | Bank income |
| ``liability_cc`` | out | CC swipe (spend) |
| ``liability_cc`` | in | **Error:** ``Credit-card payment needs a bank account`` |

That error means: “this looks like money arriving on the card.” That is either:

1. a **bill payment** → use **Approve as transfer** (bank → card), or  
2. an **EMI conversion credit** → do **not** post as payment; see {doc}`emi-conversion`.

## After approve

- Candidate → ``posted`` + ``ledger_transaction_id``
- Domain event ``intake.candidate_approved``
- Linked email staging row syncs to approved when present

## Opening balances

Special reason ``needs_opening_balance`` posts against Opening Balance Equity instead of
the normal expense/income planners.
