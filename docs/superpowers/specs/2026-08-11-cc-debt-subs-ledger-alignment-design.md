# Credit Cards · Debt · Subscriptions — Ledger Alignment Design

**Date:** 2026-08-11  
**Status:** Approved for phased implementation  
**Owner:** Vaibhav  
**Parent:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md`  
**Depends on:** P1–P2 (LedgerService + IntakeService)

---

## 1. Goal

Align Credit Cards, Debt, and Subscriptions & EMI product surfaces with the double-entry money engine so **money writes go through LedgerService** (or Intake where appropriate), balances come from ledger lenses, and schedule/metadata tables stop being a parallel books of record.

## 2. Locked decisions

| Topic | Choice |
|-------|--------|
| Roadmap shape | Full package design; **implement Credit Cards first**, then Debt/EMI, then Subscriptions |
| Loan EMI posting | Hybrid: auto-post on due when bank + amount known; else remind + manual Record EMI |
| Subscription charges | Manual **Record charge** → LedgerService expense (no silent auto-charge in v1) |
| CC pay bill | `build_cc_bill_pay` + `LedgerService.post` when `double_entry` |
| CC live outstanding | `max(0, -account_balance_paise(liability_cc))` (ledger sign convention) |
| Side `credit_cards.current_balance_paise` | Keep as cache; refresh after ledger posts / statement apply; UI live bal prefers ledger |
| NW CC liability | Prefer ledger `liability_cc` balances (Debt phase may also bind loans) |
| P5 AlertService | Not a blocker for CC phase; EMI/CC due events already designed in P5 |

## 3. Phased roadmap

| Phase | Name | Deliverable |
|-------|------|-------------|
| **W1** ✅ Done | Credit cards | pay_bill → ledger; live balance from ledger; statement apply polish; optional sync cache · [acceptance report](../../../.superpowers/sdd/p-cc-w1-acceptance-report.md) |
| **W2** | Debt + EMI | Bind `liability_loan`; EMI builder; hybrid auto/manual post; replace balance-only advance as sole money path |
| **W3** | Subscriptions | `account_id` + Record charge; reminders stay event/UI only |

This document is the umbrella spec. **W1 is done; W2 is next.**

---

## 4. Phase W1 — Credit cards (implement now)

### 4.1 Architecture

```
Pay bill (dashboard)
        │ double_entry
        ▼
build_cc_bill_pay(bank, cc) → LedgerService.post
        │ external_key optional: cc_bill:{card_id}:{date}:{amount}
        ▼
return { ledger_transaction_id }  (legacy pair ids only on legacy engine)

Live balance GET
        │ double_entry + account_id
        ▼
max(0, -account_balance_paise(account_id))

Statement apply (already Intake) — keep; after apply refresh card.current_balance_paise from ledger
```

### 4.2 `POST /credit-cards/{id}/pay-bill`

When `ledger_engine == double_entry`:

1. Require linked `account_id` (`liability_cc`) and valid `from_account_id` (bank/cash).
2. `require_ledger_writes`.
3. Post via `LedgerService` with `builders.build_cc_bill_pay`, `source="dashboard"`, payee/notes from card name.
4. Optionally refresh `credit_cards.current_balance_paise` from ledger outstanding.
5. Response: `{ "ledger_transaction_id": int }` (and keep compat fields null or omit legacy debit/credit ids).

When legacy engine: keep `insert_transfer_pair` (unchanged).

### 4.3 Live balance

`GET .../live-balance` (and list enrichment): if double_entry and `account_id` set, use ledger formula above; else legacy `cc_live_balance`.

### 4.4 Statement apply polish

After successful apply in double_entry, set `current_balance_paise` from ledger outstanding (not only statement summary) so cache matches books.

### 4.5 Out of W1

- Debt EMI builders / loan accounts  
- Subscription charge posting  
- Merging P5  
- Changing CC EMI plan CRUD (metadata OK)  
- `convert-to-debt` loan account binding (W2)

### 4.6 Testing (W1)

1. pay_bill double_entry posts balanced tx; bank↓ CC liability↓ (outstanding↓).  
2. pay_bill does not call `insert_transfer_pair` when double_entry.  
3. live-balance matches ledger after swipe + pay.  
4. legacy engine still uses transfer pair.  
5. Ledger-write CI clean.

---

## 5. Phase W2 — Debt + EMI (design lock; later plan)

- On debt create (or first EMI): ensure linked `accounts` row `type=loan` / `liability_loan`; store `account_id` on `debts`.
- New builder `build_emi_payment(bank, loan, principal, interest)` → Dr loan principal + Dr interest expense · Cr bank.
- Hybrid job: if `payment_account_id` + EMI amount + due today → post; else emit `debt.emi_due` (P5) / leave for manual Record EMI.
- Auto-advance updates schedule **after** successful post (or date-only when no money path).
- Convert-from-CC-EMI creates loan account + opening balance adjustment if needed.

## 6. Phase W3 — Subscriptions (design lock; later plan)

- Add optional `account_id` + `category` on subscriptions.
- `POST /subscriptions/{id}/record-charge` → expense posting via LedgerService.
- No auto-debit in v1; Recurring page shows Record charge CTA.
- Optional later: billing-day reminder event only.

## 7. Acceptance (umbrella)

- W1 merged and green before W2 plan execution.  
- W2/W3 each get their own implementation plan when started.  
- No module writes money to legacy `transactions` when `ledger_engine=double_entry` after its phase lands.
