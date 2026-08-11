# Package map

| Package | Path | Role |
|---------|------|------|
| ``finance-common`` | ``packages/common`` | DB, ledger, intake, recon, alerts, parsing, repos |
| ``finance-api`` | ``packages/api`` | FastAPI routers + background jobs |
| ``finance-bot`` | ``packages/bot`` | Discord client; DE writes via ``product_writes`` |
| Dashboard | ``dashboard`` | React UI |

## Ledger package API surface

```{eval-rst}
.. automodule:: finance_common.ledger
   :members:
   :imported-members:
   :undoc-members:
```
