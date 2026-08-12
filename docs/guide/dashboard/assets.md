# Assets

Route: ``/assets`` (list) and ``/assets/:id`` (detail).

Physical wealth: real estate, vehicles, gold, and other holdings. Values are
manual / module-side today (not full ``asset_other`` ledger posts for every asset).

## Portfolio KPIs

| KPI | Meaning |
|-----|---------|
| **Total assets** | Count of assets |
| **Current value** | Sum of ``current_value_paise`` |
| **Purchase price** | Sum of purchase prices |
| **Overall appreciation** | Portfolio % change vs purchase |

## Appreciation vs depreciation sections

The list is split by **asset type** (not by whether the latest % is positive):

| Section | Types |
|---------|--------|
| **Appreciation assets** | ``apartment``, ``plot``, ``commercial``, ``gold``, ``other`` |
| **Depreciation assets** | ``vehicle`` |

Each section shows a **count** and **current-value subtotal**. Cards show
“Appreciation” or “Depreciation” for the purchase→current % label accordingly.

Sold assets stay in their type section (status badge still shows ``sold``).

## Detail page

Per-asset edit, real-estate / vehicle extras, costs, linked loans, and payment
milestones live on ``/assets/:id``.

## Out of scope (for now)

- Auto-classifying by actual gain/loss instead of type
- Posting every physical asset as ``asset_other`` on the ledger
