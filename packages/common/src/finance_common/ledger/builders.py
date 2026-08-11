"""Posting builders for common double-entry transaction patterns.

Sign convention (signed ``amount_paise`` on each posting):

- Asset increase = debit = ``+amount``
- Asset decrease = credit = ``-amount``
- Liability increase = credit = ``-amount``
- Liability decrease = debit = ``+amount``
- Expense increase = debit = ``+amount``
- Income increase = credit = ``-amount``

All builder ``amount_paise`` arguments are positive magnitudes; signs are
applied here.  Examples:

- CC swipe ₹100: Expense ``+10000``, CC ``-10000``
- Bill pay ₹100: CC ``+10000``, Bank ``-10000``
- Bank expense: Expense ``+X``, Bank ``-X``
- Bank income: Bank ``+X``, Income ``-X``
- Transfer A→B: B ``+X``, A ``-X``
- Investment buy: Investment ``+X``, Bank ``-X``
"""

from __future__ import annotations

from finance_common.ledger.models import NewPosting


def build_bank_expense(
    *,
    bank_id: int,
    expense_account_id: int,
    amount_paise: int,
    category: str,
) -> tuple[NewPosting, ...]:
    """Debit expense, credit bank (asset decrease)."""
    return (
        NewPosting(expense_account_id, amount_paise, category),
        NewPosting(bank_id, -amount_paise),
    )


def build_bank_income(
    *,
    bank_id: int,
    income_account_id: int,
    amount_paise: int,
    category: str,
) -> tuple[NewPosting, ...]:
    """Debit bank (asset increase), credit income."""
    return (
        NewPosting(bank_id, amount_paise),
        NewPosting(income_account_id, -amount_paise, category),
    )


def build_transfer(
    *,
    from_account_id: int,
    to_account_id: int,
    amount_paise: int,
) -> tuple[NewPosting, ...]:
    """Debit destination, credit source."""
    return (
        NewPosting(to_account_id, amount_paise),
        NewPosting(from_account_id, -amount_paise),
    )


def build_cc_swipe(
    *,
    cc_id: int,
    expense_account_id: int,
    amount_paise: int,
    category: str,
) -> tuple[NewPosting, ...]:
    """Debit expense, credit credit-card liability."""
    return (
        NewPosting(expense_account_id, amount_paise, category),
        NewPosting(cc_id, -amount_paise),
    )


def build_cc_bill_pay(
    *,
    bank_id: int,
    cc_id: int,
    amount_paise: int,
) -> tuple[NewPosting, ...]:
    """Debit credit-card liability, credit bank."""
    return (
        NewPosting(cc_id, amount_paise),
        NewPosting(bank_id, -amount_paise),
    )


def build_investment_buy(
    *,
    bank_id: int,
    investment_account_id: int,
    amount_paise: int,
) -> tuple[NewPosting, ...]:
    """Debit investment asset, credit bank."""
    return (
        NewPosting(investment_account_id, amount_paise),
        NewPosting(bank_id, -amount_paise),
    )


def build_emi_payment(
    *,
    bank_id: int,
    loan_id: int,
    expense_account_id: int,
    principal_paise: int,
    interest_paise: int,
    interest_category: str = "Debt Interest",
) -> tuple[NewPosting, ...]:
    """Dr loan principal + Dr interest expense · Cr bank."""
    total = principal_paise + interest_paise
    postings: list[NewPosting] = [NewPosting(loan_id, principal_paise)]
    if interest_paise != 0:
        postings.append(
            NewPosting(expense_account_id, interest_paise, interest_category)
        )
    postings.append(NewPosting(bank_id, -total))
    return tuple(postings)
