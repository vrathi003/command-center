"""Map domain event types to in-app alert notifications."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from finance_common.alerts.models import AlertSeverity
from finance_common.types import Paise, paise_to_rupees


@dataclass(frozen=True, slots=True)
class RoutedAlert:
    fingerprint: str
    kind: str
    title: str
    message: str
    severity: AlertSeverity


def route_event(
    event_type: str,
    payload: Mapping[str, object],
    *,
    event_id: int,
) -> RoutedAlert | None:
    """Return a routed alert for a known event type, or None when unknown."""
    if event_type == "budget.threshold":
        return _route_budget(payload, event_id=event_id)
    if event_type == "debt.emi_due":
        return _route_emi(payload, event_id=event_id)
    if event_type == "credit_card.due":
        return _route_credit_card(payload, event_id=event_id)
    if event_type == "intake.quarantine_created":
        return _route_intake_quarantine(payload, event_id=event_id)
    if event_type == "intake.candidate_approved":
        return _route_intake_approved(payload, event_id=event_id)
    if event_type == "intake.candidate_rejected":
        return _route_intake_rejected(payload, event_id=event_id)
    if event_type == "migration.quarantine_created":
        return _route_migration_quarantine(payload, event_id=event_id)
    return None


def _fallback_fingerprint(event_type: str, event_id: int) -> str:
    return f"{event_type}|{event_id}"


def _payload_str(payload: Mapping[str, object], key: str, default: str = "") -> str:
    value = payload.get(key)
    if value is None:
        return default
    return str(value)


def _payload_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _format_rupees(paise: Paise) -> str:
    return f"₹{paise_to_rupees(paise):,.2f}"


def _route_budget(payload: Mapping[str, object], *, event_id: int) -> RoutedAlert:
    ym = _payload_str(payload, "ym")
    category = _payload_str(payload, "category", "Unknown")
    status = _payload_str(payload, "status")

    if ym and category and status:
        fingerprint = f"budget|{ym}|{category}|{status}"
    else:
        fingerprint = _fallback_fingerprint("budget.threshold", event_id)

    severity: AlertSeverity = "warn" if status == "warn" else "error"
    if status == "warn":
        title = f"Budget warning: {category}"
    elif status == "over":
        title = f"Budget over: {category}"
    else:
        title = f"Budget alert: {category}"

    parts: list[str] = []
    spent_paise = _payload_int(payload, "spent_paise")
    budget_paise = _payload_int(payload, "budget_paise")
    if spent_paise is not None and budget_paise is not None:
        parts.append(
            f"Spent {_format_rupees(Paise(spent_paise))} of {_format_rupees(Paise(budget_paise))}"
        )
    pct = payload.get("pct")
    if pct is not None:
        parts.append(f"{pct}% utilized")
    if ym:
        parts.append(f"for {ym}")
    message = ". ".join(parts) if parts else f"Budget threshold reached for {category}."

    return RoutedAlert(
        fingerprint=fingerprint,
        kind="budget",
        title=title,
        message=message,
        severity=severity,
    )


def _route_emi(payload: Mapping[str, object], *, event_id: int) -> RoutedAlert:
    debt_id = _payload_int(payload, "debt_id")
    due_date = _payload_str(payload, "due_date")
    name = _payload_str(payload, "name", "Loan")

    if debt_id is not None and due_date:
        fingerprint = f"emi|{debt_id}|{due_date}"
    else:
        fingerprint = _fallback_fingerprint("debt.emi_due", event_id)

    days_until = _payload_int(payload, "days_until")
    if days_until is not None and due_date:
        message = f"{name} EMI due in {days_until} day(s) on {due_date}."
    elif due_date:
        message = f"{name} EMI due on {due_date}."
    else:
        message = f"{name} EMI payment is due soon."

    return RoutedAlert(
        fingerprint=fingerprint,
        kind="emi",
        title=f"EMI due: {name}",
        message=message,
        severity="warn",
    )


def _route_credit_card(payload: Mapping[str, object], *, event_id: int) -> RoutedAlert:
    card_id = _payload_int(payload, "card_id")
    due_date = _payload_str(payload, "due_date")
    name = _payload_str(payload, "name", "Credit card")
    when = _payload_str(payload, "when")

    if card_id is not None and due_date:
        fingerprint = f"cc_due|{card_id}|{due_date}"
    else:
        fingerprint = _fallback_fingerprint("credit_card.due", event_id)

    if when and due_date:
        message = f"{name} payment due {when} ({due_date})."
    elif due_date:
        message = f"{name} payment due on {due_date}."
    else:
        message = f"{name} payment is due soon."

    return RoutedAlert(
        fingerprint=fingerprint,
        kind="credit_card",
        title=f"Credit card due: {name}",
        message=message,
        severity="warn",
    )


def _route_intake_quarantine(payload: Mapping[str, object], *, event_id: int) -> RoutedAlert:
    candidate_id = _payload_int(payload, "candidate_id")
    reason = _payload_str(payload, "reason", "Review required")

    if candidate_id is not None:
        fingerprint = f"intake.quarantine|{candidate_id}"
    else:
        fingerprint = _fallback_fingerprint("intake.quarantine_created", event_id)

    label = str(candidate_id) if candidate_id is not None else "unknown"
    return RoutedAlert(
        fingerprint=fingerprint,
        kind="intake",
        title="Intake quarantined",
        message=f"Candidate {label} quarantined: {reason}.",
        severity="warn",
    )


def _route_intake_approved(payload: Mapping[str, object], *, event_id: int) -> RoutedAlert:
    candidate_id = _payload_int(payload, "candidate_id")

    if candidate_id is not None:
        fingerprint = f"intake.approved|{candidate_id}"
    else:
        fingerprint = _fallback_fingerprint("intake.candidate_approved", event_id)

    label = str(candidate_id) if candidate_id is not None else "unknown"
    return RoutedAlert(
        fingerprint=fingerprint,
        kind="intake",
        title="Intake approved",
        message=f"Candidate {label} was approved and posted.",
        severity="info",
    )


def _route_intake_rejected(payload: Mapping[str, object], *, event_id: int) -> RoutedAlert:
    candidate_id = _payload_int(payload, "candidate_id")
    reason = _payload_str(payload, "reason", "Rejected")

    if candidate_id is not None:
        fingerprint = f"intake.rejected|{candidate_id}"
    else:
        fingerprint = _fallback_fingerprint("intake.candidate_rejected", event_id)

    label = str(candidate_id) if candidate_id is not None else "unknown"
    return RoutedAlert(
        fingerprint=fingerprint,
        kind="intake",
        title="Intake rejected",
        message=f"Candidate {label} rejected: {reason}.",
        severity="info",
    )


def _route_migration_quarantine(payload: Mapping[str, object], *, event_id: int) -> RoutedAlert:
    stable_id = (
        payload.get("fingerprint") or payload.get("id") or payload.get("candidate_id") or event_id
    )
    reason = _payload_str(payload, "reason", "Migration review required")
    fingerprint = f"migration.quarantine|{stable_id}"

    return RoutedAlert(
        fingerprint=fingerprint,
        kind="migration",
        title="Migration quarantined",
        message=f"Migration item quarantined: {reason}.",
        severity="warn",
    )
