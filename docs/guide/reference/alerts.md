# Alerts / Notifications (stub)

**Status:** stub.

| Piece | Role |
|-------|------|
| ``domain_events`` | Outbox of domain + ops events |
| ``finance_common.alerts.route`` | Map event → notification fingerprint |
| ``finance_common.alerts.service.poll_once`` | Drain outbox → ``alert_notifications`` |
| Dashboard ``/alerts`` | Notifications inbox + ack |

Ops types include ``ops.job_failed``, ``ops.gmail_auth_failed``, ``ops.backup_failed``.
Interactive UI errors use **toasts**, not this inbox.
