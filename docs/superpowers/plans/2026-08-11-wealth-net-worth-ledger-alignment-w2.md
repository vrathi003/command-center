# Wealth Net Worth Ledger Alignment (W2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute Net Worth with a composed lens — ledger balance sheet minus investment/FI ledger cost plus holdings market value / FI principal overlay.

**Architecture:** When `double_entry`, replace (or branch) `compute_totals_from_holdings` to use `net_worth_totals` + subtract linked inv/FI account balances + add MV/principal from side tables + assets module. Snapshots and month-end job use the same function. Legacy path keeps old holdings-only compute.

**Tech Stack:** aiosqlite, FastAPI, pytest, `finance_common.ledger.balances.net_worth_totals`.

**Spec:** `docs/superpowers/specs/2026-08-11-wealth-stack-ledger-alignment-design.md` §6

## Global Constraints

- Do not rewrite historical `net_worth_history` rows.
- Price sync remains non-posting; MV overlay from holdings tables.
- TDD; commit per task; no unrelated `uv.lock`.
- Do not implement W3 Income or Goals linking.

## File map

| Path | Role |
|------|------|
| `services/net_worth_service.py` | composed compute |
| `routers/net_worth.py` | snapshot uses composed when double_entry |
| `background_jobs.py` | month-end job |
| `dashboard_service.py` | optional live KPI if it hardcodes old path |
| `tests/test_net_worth_composed.py` | coverage |

---

### Task 1: Composed compute function

```python
async def compute_net_worth_composed(conn) -> tuple[int, int, int]:
    """assets, liabilities, net using ledger + MV overlay."""
```

Logic (double_entry):
1. `base = await net_worth_totals(conn)` → assets_paise, liabilities_paise, net
2. Sum `account_balance_paise` for all investments/FI with non-null `account_id` (= cost on books)
3. `inv_mv` from `portfolio_totals`; `fi_principal` from FI total
4. `other = await asset_repo.total_active_value` (real assets module)
5. `assets = base.assets - inv_cost - fi_cost + inv_mv + fi_principal + other`
   - If real assets are NOT on ledger, adding `other` is correct (today they aren't).
   - If `base.assets` already excludes them, fine.
6. `liabilities = base.liabilities` (CC/loans on ledger). Optionally still add unbound debt/CC caches if account_id null — prefer ledger-only when bound; for unbound keep legacy debt/cc aggregates as add-on so NW doesn't drop.

Simpler v1 accepted formula from spec:
```
assets = base.assets - inv_cost - fi_cost + inv_mv + fi_principal + other_assets
liabilities = base.liabilities
# If unbound debts/CCs exist without ledger accounts, add their outstanding to liabilities
net = assets - liabilities
```

`compute_totals_from_holdings` becomes a dispatcher: double_entry → composed; else old path.

- [x] Unit/integration tests with seeded inv + bank
- [x] Commit `feat(net-worth): composed ledger + MV lens`

---

### Task 2: Wire snapshot API + month-end job

- Ensure POST snapshot / compute-from-holdings / job call dispatcher
- [x] Test snapshot stores composed totals
- [x] Commit `feat(net-worth): snapshots use composed compute`

---

### Task 3: Acceptance

- pytest + check-ledger-writes
- Mark W2 ✅ on wealth umbrella; W3 Income next
- [x] Commit `docs(wealth): mark net worth ledger W2 complete`

---

## Self-review vs §6

| Spec | Task |
|------|------|
| Composed compute | 1 |
| Snapshots / job | 2 |
| Cash completeness note | docs only in acceptance |
| Acceptance | 3 |
