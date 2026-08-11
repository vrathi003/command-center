# Email → ledger

## Happy path

```text
Gmail sync (job or POST /email-inbox/sync)
        │
        ▼
email_transaction_staging  (status pending)
        │
        ▼
Dashboard Email Inbox — review / edit
        │
        ▼
Approve  ──►  Intake bridge (hybrid)
        │
        ├─► quarantine (duplicate / transfer ambiguity / low confidence)
        │
        └─► plan_postings / plan_transfer → ledger.service.post
                 staging status = approved + ledger_transaction_id
```

## Double-entry requirements

- Approve must send a real **``account_id``** (bank or CC matching the swipe/expense).
- Under DE, missing account → **422** ``account_id is required to approve``.
- Interactive failures surface as **toasts**; Gmail auth / job crashes land in **Notifications** as ``ops.*``.

## Sources and keys

- Staging / candidates use ``external_key`` like ``gmail:…`` so re-sync does not double-post.
- ``source`` on the ledger header is typically ``email``.

## Related UI

| Page | Route |
|------|-------|
| Email Inbox | ``/email-inbox`` |
| Quarantine desk | ``/transactions/quarantine`` |

Next: {doc}`quarantine-approve`.
