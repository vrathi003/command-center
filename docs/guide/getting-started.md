# Getting started

## What “the ledger” means here

Under ``ledger_engine=double_entry``, the books of record are:

| Table | Role |
|-------|------|
| ``ledger_transactions`` | Header: date, payee, source, status, optional ``external_key`` |
| ``ledger_postings`` | Signed legs (must sum to **0**). Link to ``accounts.id`` |

The older ``transactions`` table is a **legacy / façade** surface. Dashboard lists may still look like “transactions,” but after cutover they are projected from ledger postings.

## Config flags that change behaviour

| Flag / helper | Effect |
|---------------|--------|
| ``ledger_engine`` (`legacy` \| `double_entry`) | Master switch. Production should be ``double_entry``. |
| ``uses_ledger_books(conn)`` | True when engine is ``double_entry`` — read models use ledger spend/balances. |
| ``require_ledger_writes`` | FastAPI dependency: 503 if integrity failed and writes were disabled. |
| ``app.state.ledger_writes_enabled`` | Set false on startup if unbalanced posted txs are detected. |

Settings are stored via project config (SQLite settings keys), not only ``.env``.

## Mental model: adapters → plan → post

```text
UI / Email / Bot / CC Pay Bill / Record EMI
              │
              ▼
     Plan postings (builders / intake plan)
              │
              ▼
     LedgerService.post()   ← only writer into ledger_* tables
              │
              ▼
     Balances / budget lenses / net worth read posted postings
```

**Hard rule:** routers and jobs must not ``INSERT`` into ``ledger_postings`` directly. They call ``finance_common.ledger.service.post`` (or product helpers that do).

## Where to go next

- Understand signs and builders → {doc}`ledger/sign-convention`
- Trace Email Inbox approve → {doc}`workflows/email-to-ledger`
- Trace CC bill pay → {doc}`workflows/cc-bill-pay`
- Trace loan EMI → {doc}`workflows/debt-emi`
