# Feature gates

## ``ledger_engine``

Stored in project config. Values:

- ``legacy`` — old ``transactions`` table is authoritative for writes/reads.
- ``double_entry`` — ledger is authoritative; product writes must post balanced txs.

Helper: ``uses_ledger_books(conn)`` → ``True`` iff engine is ``double_entry``.

## Write gate vs engine gate

| Check | Meaning |
|-------|---------|
| Engine is ``double_entry`` | Features that *only* make sense on the ledger (e.g. record EMI via ledger) |
| ``require_ledger_writes`` | Integrity allows posting right now |

Both can be true independently of cutover UX flags for individual read models.

## Who must pass the write gate

Typical routes (non-exhaustive):

- Manual / transfer transaction create
- Email inbox approve / transfer / undo
- Intake candidate approve
- CC bill pay
- Debt record EMI
- Investment / subscription record-charge (DE mode)

If you add a new money movement, wire **both** planning and this dependency.
