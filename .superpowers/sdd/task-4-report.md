# Task 4 Report — Record buy / SIP / sell APIs

**Status:** Done  
**Tests:** `pytest tests/test_investment_ledger_w1.py` — 7 passed

## Endpoints
- `POST /investments/{id}/record-buy` — optional `kind: buy|sip` for narration
- `POST /investments/{id}/record-sell`

## Implementation
- `record_investment_buy` / `record_investment_sell` in `investment_ledger.py`
- Uses `build_investment_buy` / `build_investment_sell`; account bind only (no re-seed on trade)
- Buy: weighted-average `avg_price_paise`; sell: reduce units, avg unchanged
- Returns `{ledger_transaction_id, investment}`; 422 when not `double_entry`
