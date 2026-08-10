from __future__ import annotations

from datetime import date

from finance_common.recon.models import ReconStatementLine
from finance_common.recon.suggest import LedgerMatchCandidate, suggest_matches


def _line(
    *,
    line_id: int = 1,
    tx_date: date = date(2026, 8, 10),
    amount_paise: int = 25_000,
    payee: str | None = "Swiggy",
) -> ReconStatementLine:
    return ReconStatementLine(
        id=line_id,
        statement_id=1,
        tx_date=tx_date,
        amount_paise=amount_paise,
        direction="out",
        payee=payee,
        narration=None,
        external_key=None,
        status="unmatched",
        ignore_reason=None,
        created_at="2026-08-10T00:00:00",
        updated_at="2026-08-10T00:00:00",
    )


def test_suggest_matches_selects_best_same_account_candidate() -> None:
    proposals = suggest_matches(
        lines=(_line(),),
        candidates=(
            LedgerMatchCandidate(
                transaction_id=11,
                account_id=7,
                tx_date=date(2026, 8, 9),
                amount_paise=-25_000,
                payee="Swiggy Instamart",
            ),
            LedgerMatchCandidate(
                transaction_id=12,
                account_id=7,
                tx_date=date(2026, 8, 10),
                amount_paise=-25_000,
                payee="Swiggy",
            ),
        ),
        account_id=7,
    )

    assert len(proposals) == 1
    assert proposals[0].line_id == 1
    assert proposals[0].ledger_transaction_id == 12
    assert proposals[0].score == 1.0
    assert proposals[0].reasons == ("amount", "date", "payee_prefix")


def test_suggest_matches_excludes_matched_and_ineligible_candidates() -> None:
    proposals = suggest_matches(
        lines=(_line(),),
        candidates=(
            LedgerMatchCandidate(11, 7, date(2026, 8, 10), -25_000, "Swiggy"),
            LedgerMatchCandidate(12, 8, date(2026, 8, 10), -25_000, "Swiggy"),
            LedgerMatchCandidate(13, 7, date(2026, 8, 10), -20_000, "Swiggy"),
            LedgerMatchCandidate(14, 7, date(2026, 8, 13), -25_000, "Swiggy"),
        ),
        account_id=7,
        matched_ledger_transaction_ids=frozenset({11}),
    )

    assert proposals == ()


def test_suggest_matches_scores_date_distance_and_missing_payee() -> None:
    proposals = suggest_matches(
        lines=(_line(payee=None),),
        candidates=(
            LedgerMatchCandidate(11, 7, date(2026, 8, 12), 25_000, None),
        ),
        account_id=7,
        date_window_days=2,
    )

    assert len(proposals) == 1
    assert proposals[0].score == 0.7
    assert proposals[0].reasons == ("amount", "date")
