# Goals

Route: ``/goals``.

Savings targets with portfolio KPIs, time-to-goal, on-track status, an emergency-fund
helper, and an illustrative retirement corpus projector. Progress amounts are
**manual** this package (Goals ↔ holding link is later).

## Portfolio KPI strip

| KPI | Meaning |
|-----|---------|
| **Goals** | Number of goals |
| **Total target** | Sum of target amounts |
| **Total saved** | Sum of current amounts |
| **Overall progress** | ``saved ÷ target`` (capped at 100%) |
| **Monthly save** | Sum of planned monthly contributions |
| **On track** | ``on_track_or_done / trackable`` — needs both a target date and monthly save |

## Emergency fund

1. Enter **Monthly expenses (₹)** (stored in browser ``localStorage`` — not derived from ledger spend).
2. Target = **6 ×** that amount.
3. **Create emergency goal** / **Update emergency goal target** finds a goal whose name or category contains ``emergency`` (case-insensitive), or creates ``Emergency fund`` / category ``Emergency``.

Gap = target − that goal’s current saved amount.

## Retirement corpus (illustrative)

Local-only calculator (also ``localStorage``): grow current corpus annually and add a flat monthly SIP until retirement age. Not advice; ignores tax and inflation.

## Goal cards

Replaces the old inline edit table. Each card shows:

- Progress bar and %
- Saved / target / monthly save
- **Time to goal** — ``ceil(remaining ÷ monthly)`` months when monthly > 0
- **On track / Behind / Complete / No pace yet**
  - On track when planned monthly ≥ remaining ÷ months until target date
- Edit / Delete

## Out of scope (for now)

- Linking a goal to an investment / account for automatic progress
- Auto monthly expenses from ledger spend
- Server ``/goals/summary`` endpoint (rollups are client-side)
