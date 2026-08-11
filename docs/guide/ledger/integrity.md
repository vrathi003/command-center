# Integrity and write gates

## Checks

``find_unbalanced_posted_transaction_ids(conn)`` finds posted headers where:

- fewer than two postings, or
- sum of posting amounts ≠ 0

``assert_ledger_healthy(conn)`` raises ``LedgerIntegrityError`` if any such ids exist.

## Startup behaviour

When the API starts with ``ledger_engine=double_entry``, it can run integrity and set
``app.state.ledger_writes_enabled = False`` if the books are unhealthy.

## ``require_ledger_writes``

FastAPI dependency (``finance_api.deps_ledger``):

- If writes disabled → **HTTP 503** ``Ledger writes disabled due to integrity failure``
- Used on mutating routes that post to the ledger (transactions, email approve, CC pay, EMI, …)

## What to do if writes are blocked

1. Inspect unbalanced ids (script / SQL using the integrity helper).
2. Fix data (usually void + re-post, or repair a bad migration row).
3. Restart API so integrity re-runs and re-enables writes.

## CI guard

``make check-ledger-writes`` / ``scripts/ci_check_ledger_writes.py`` fails the build if
product code inserts into ledger tables without going through the service.
