# Credit cards

Route: ``/credit-cards`` (list) and ``/credit-cards/:id`` (detail).

Standalone deep-dive: ``docs/CREDIT_CARDS.md`` (statement import, Pay Bill, EMIs).

## Portfolio KPI strip (list page)

Under the page hero, **active cards only** roll up into six KPIs (same pattern as
Debt / Goals):

| KPI | Meaning |
|-----|---------|
| **Total outstanding** | Sum of each card’s statement/current balance |
| **Limit available** | Sum of ``max(0, limit − utilised)`` per card |
| **Total limit** | Sum of credit limits |
| **Limit utilised** | Sum of balance **+** EMI principal blocked against the limit |
| **Active EMIs** | Count of active EMI plans across cards |
| **EMI / month** | Sum of monthly EMI dues |

Outstanding and utilised are **not** the same number: utilised includes EMI-blocked
principal so available limit stays conservative.

Inactive cards are excluded from the strip.

## Card tiles

Each tile still shows per-card limit, balance, utilization %, and EMI / month when
plans exist. Open a tile for live ledger outstanding, Pay Bill, statements, and EMI CRUD.

## Ledger behaviour (double-entry)

- Card create links / creates a ``liability_cc`` account.
- Live outstanding prefers ledger postings on that account.
- **Pay Bill** posts bank ↓ + CC liability ↓ (cash-flow only — not budget spend).
- Statement apply refreshes the card’s cached balance after import.
