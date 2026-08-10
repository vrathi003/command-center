"""Pure reconciliation match suggestion scoring."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date

from finance_common.recon.models import ReconStatementLine

_AMOUNT_WEIGHT = 0.6
_DATE_WEIGHT = 0.3
_PAYEE_PREFIX_WEIGHT = 0.1


@dataclass(frozen=True, slots=True)
class MatchProposal:
    """The highest-scoring ledger transaction proposed for a statement line."""

    line_id: int
    ledger_transaction_id: int
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LedgerMatchCandidate:
    """A single account posting and its ledger transaction details."""

    transaction_id: int
    account_id: int
    tx_date: date
    amount_paise: int
    payee: str | None


def _has_payee_prefix(line_payee: str | None, candidate_payee: str | None) -> bool:
    if line_payee is None or candidate_payee is None:
        return False

    normalized_line = " ".join(line_payee.casefold().split())
    normalized_candidate = " ".join(candidate_payee.casefold().split())
    return bool(normalized_line) and (
        normalized_line.startswith(normalized_candidate)
        or normalized_candidate.startswith(normalized_line)
    )


def _score_candidate(
    line: ReconStatementLine, candidate: LedgerMatchCandidate, date_window_days: int
) -> tuple[float, tuple[str, ...]] | None:
    expected_amount = line.amount_paise if line.direction == "in" else -line.amount_paise
    if candidate.amount_paise != expected_amount:
        return None

    days_apart = abs((candidate.tx_date - line.tx_date).days)
    if days_apart > date_window_days:
        return None

    date_score = _DATE_WEIGHT * (date_window_days + 1 - days_apart) / (
        date_window_days + 1
    )
    reasons = ["amount", "date"]
    score = _AMOUNT_WEIGHT + date_score
    if _has_payee_prefix(line.payee, candidate.payee):
        score += _PAYEE_PREFIX_WEIGHT
        reasons.append("payee_prefix")
    return round(score, 6), tuple(reasons)


def suggest_matches(
    *,
    lines: Iterable[ReconStatementLine],
    candidates: Iterable[LedgerMatchCandidate],
    account_id: int,
    matched_ledger_transaction_ids: Collection[int] = (),
    date_window_days: int = 2,
) -> tuple[MatchProposal, ...]:
    """Return one best, unconfirmed ledger-match proposal for each unmatched line."""
    if date_window_days < 0:
        raise ValueError("date_window_days must be non-negative")

    matched_ids = frozenset(matched_ledger_transaction_ids)
    eligible_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.account_id == account_id and candidate.transaction_id not in matched_ids
    )
    proposals: list[MatchProposal] = []
    for line in lines:
        if line.status != "unmatched":
            continue

        scored_candidates = [
            (candidate, candidate_score)
            for candidate in eligible_candidates
            if (
                candidate_score := _score_candidate(line, candidate, date_window_days)
            ) is not None
        ]
        if not scored_candidates:
            continue

        candidate, (proposal_score, reasons) = max(
            scored_candidates, key=lambda item: (item[1][0], -item[0].transaction_id)
        )
        proposals.append(
            MatchProposal(
                line_id=line.id,
                ledger_transaction_id=candidate.transaction_id,
                score=proposal_score,
                reasons=reasons,
            )
        )
    return tuple(proposals)
