# Money Engine — How to Use (section by section)

**For:** already-deployed Ubuntu stack (API + bot + dashboard running), ledger migration / cutover already done, `ledger_engine=double_entry`.

Pull latest `main`, restart the three services once so schema migrations apply, then use the dashboard as below.

---

## 1. Accounts (`/accounts`)

1. Keep bank / wallet / CC / loan accounts up to date — ledger balances hang off these.
2. Each **credit card** should link to a `liability_cc` account (created with the card in double-entry mode).
3. Each **loan** gets a `liability_loan` account (auto on create when double-entry).

---

## 2. Transactions (`/transactions`)

1. Add debit / credit / transfer as usual — after cutover these post through the **ledger**.
2. Use filters / search as before.
3. Prefer **void + re-post** for mistakes on ledger rows (don’t treat soft-delete as the books of record).

---

## 3. Email → books (`/email-inbox` → `/transactions/quarantine`)

1. **Email Inbox** → Sync (or wait for the job).
2. Review staged mail → **Approve** (or approve-as-transfer when it’s a transfer).
3. Ambiguous / low-confidence items land in **Quarantine** (`/transactions/quarantine`) — fix account/category → post or reject.
4. Posted items hit the ledger (source `email`); duplicates are skipped by `gmail:…` keys.

---

## 4. Alerts (`/alerts`)

1. Budget overspend, EMI due, CC due, etc. show in the **banner** and on **Alerts**.
2. Open `/alerts` → read → **Ack**.
3. Discord is optional; in-app alerts are the primary path now.

---

## 5. Credit cards (`/credit-cards`)

1. Open a card — **live outstanding** comes from the ledger (not a stale cache alone).
2. Swipes / statement apply still update the card; cache refreshes after apply.
3. **Pay bill** → pick bank + amount + date → posts `CC ↓` + `Bank ↓` (cash-flow only; not a second “spend”).
4. After pay, outstanding should drop by the paid amount.

---

## 6. Debt / EMI (`/debt`)

1. Create or open a loan — confirm it has a linked loan account.
2. Set **payment account** (bank/wallet) if you want **auto EMI** on due day.
3. **Manual:** active loan → **Record EMI** → date, bank, optional principal/interest override → save.  
   Posts principal + interest; advances next EMI date; outstanding follows ledger.
4. **Auto:** on due day, if loan account + payment account + EMI amount are set → job posts; otherwise you get a reminder / use Record EMI.
5. Loan EMIs also listed under Recurring for visibility; edit loans on Debt.

---

## 7. Subscriptions (`/recurring`)

1. Add subscription (name, amount, cycle, category, optional **payment account**).
2. When charged in real life → **Record charge** → date, pay-from account, optional amount → save.  
   Posts expense to ledger; advances `next_billing_date`.
3. There is **no silent auto-debit** — you must Record charge (or it won’t hit the books).

---

## 8. Investments + Fixed income (`/investments`)

1. After API restart, existing holdings/FI **auto-seed** ledger accounts (cost/principal vs Opening Balance Equity — not a fake bank hit).
2. **Record buy / SIP / sell** on a holding → posts transfer bank ↔ investment; updates units/avg. Does **not** count as budget spend.
3. FI: **Record deposit / maturity** → bank ↔ instrument; updates principal.
4. Price sync still updates market price only (P&L / MV on the page). Ledger stays at **cost**.

---

## 9. Net Worth (`/net-worth`)

1. Snapshots / month-end job use the **composed lens**: ledger BS − inv/FI cost + holdings MV / FI principal (+ real assets).
2. Take a snapshot from the page (compute from holdings) to refresh the chart after big buys/sells.
3. Old history rows are left as-is.

---

## 10. Income & Tax (`/income`)

1. Streams stay **planning** (expected salary etc.).
2. When money arrives → **Record income** on the stream (prefilled amount/bank/category) → ledger bank income.
3. Dashboard **savings rate** uses real ledger income credits (not the plan figure).
4. Tax regime / 80C / 80D remain settings only.

---

## 11. Goals (`/goals`)

Still manual progress trackers this package. Later: link each goal to an instrument.

---

## 12. Budget (`/budget`)

1. Caps vs actual use **ledger budget-spend** (expense categories) when `double_entry`.
2. Watch **Alerts** at ~75% / over budget instead of relying on Discord DMs.

---

## 13. Reconciliation (`/reconciliation`)

1. Upload / match statement periods against ledger postings (dual-books control).
2. Resolve unmatched items; don’t invent unpaired transfers in the old sense.

---

## 14. Settings (`/settings`)

1. Confirm FY and that **ledger engine** stays `double_entry`.
2. Leave Discord off unless you explicitly want it as a channel later.
3. Gmail paths (if used) stay as already configured on the server.

---

## Quick “when do I click what?”

| Situation | Where | Action |
|-----------|--------|--------|
| Spent on UPI / card (manual) | Transactions | Add debit/credit |
| Bank mail arrived | Email Inbox → Quarantine if needed | Approve / post |
| Paid CC bill from bank | Credit card detail | Pay bill |
| EMI left the bank | Debt | Record EMI (or let auto-post if linked) |
| Netflix / SaaS billed | Recurring | Record charge |
| Bought SIP / shares | Investments | Record buy / SIP |
| FD topped up / matured | Investments (FI) | Record deposit / maturity |
| Salary credited | Income | Record income |
| Refresh NW after trades | Net Worth | Snapshot from holdings |
| Got a warning | Alerts | Ack |
| Statement vs books | Reconciliation | Match / fix |

---

## One-liners (already done on your box — keep for later)

- Schema: restart API after pull (migrations on boot).
- Legacy history: `POST /api/migration/legacy-ledger/dry-run` then `…/apply` (you already ran this).
- Dev guard only: `make check-ledger-writes` — not needed for day-to-day use.
- After pull: restart API + dashboard so spend/budget/reports read ledger lenses.
