"""Domain value types and enumerations for the Finance OS.

All monetary amounts are represented as Paise (integer) throughout the system.
1 rupee = 100 paise. The display layer converts paise → ₹ strings.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NewType

# ── Scalar newtypes ────────────────────────────────────────────────────────────

Paise = NewType("Paise", int)
"""Integer rupee amount × 100. Never use float for money."""

FYYear = NewType("FYYear", str)
"""Financial year string in "YYYY-YY" format, e.g. "2025-26"."""


def rupees_to_paise(rupees: float) -> Paise:
    """Convert a rupee amount (float) to paise (int), rounding half-up."""
    return Paise(round(rupees * 100))


def paise_to_rupees(paise: Paise) -> float:
    """Convert paise to rupees for display."""
    return paise / 100


# ── Expense categories ─────────────────────────────────────────────────────────


class Category(StrEnum):
    FOOD_DELIVERY = "Food Delivery"
    GROCERIES = "Groceries"
    DINING_OUT = "Dining Out"
    OUTSIDE_FOOD_SNACKS = "Outside Food & Snacks"
    TRANSPORT_FUEL = "Transport & Fuel"
    CAR_EXPENSES = "Car Expenses"
    HOUSING_RENT = "Housing & Rent"
    UTILITIES = "Utilities"
    HEALTH_MEDICAL = "Health & Medical"
    CLOTHING = "Clothing"
    ONLINE_SHOPPING = "Online Shopping"
    ENTERTAINMENT = "Entertainment"
    SUBSCRIPTIONS = "Subscriptions"
    EDUCATION = "Education"
    PERSONAL_CARE = "Personal Care"
    PERSONAL_GROOMING = "Personal Grooming"
    TRAVEL = "Travel"
    RELATIVES_VISIT = "Relatives Visit"
    GIFTS_DONATIONS = "Gifts & Donations"
    GIFTS_ADDITIONALS = "Gifts & Additionals"
    EMI_LOAN = "EMI Loan Repayment"
    CC_BILL = "CC Bill"
    INVESTMENTS = "Investments"
    INSURANCE = "Insurance"
    TAXES = "Taxes"
    INCOME = "Income"
    TRANSFER = "Transfer"
    OTHER = "Other"

    @classmethod
    def from_string(cls, value: str) -> Category:
        """Case-insensitive lookup; falls back to OTHER."""
        normalised = value.strip().lower()
        for member in cls:
            if member.value.lower() == normalised or member.name.lower() == normalised:
                return member
        return cls.OTHER


# ── Payment modes ──────────────────────────────────────────────────────────────


# Transaction ledger type on `transactions.transaction_type`: debit | credit | transfer
# ("transfer" rows are paired via transfer_pair_id; excluded from spend aggregates.)


class PaymentMode(StrEnum):
    UPI = "UPI"
    CASH = "Cash"
    HDFC_CC = "HDFC Credit Card"
    SBI_CC = "SBI Credit Card"
    ICICI_CC = "ICICI Credit Card"
    AXIS_CC = "Axis Credit Card"
    OTHER_CC = "Other Credit Card"
    HDFC_DC = "HDFC Debit Card"
    SBI_DC = "SBI Debit Card"
    BANK_TRANSFER = "Bank Transfer"
    NEFT_IMPS = "NEFT/IMPS"
    EMI = "EMI"
    OTHER = "Other"

    @classmethod
    def from_string(cls, value: str) -> PaymentMode:
        normalised = value.strip().lower()
        # Common abbreviation shorthands
        shortcuts: dict[str, PaymentMode] = {
            "upi": cls.UPI,
            "gpay": cls.UPI,
            "phonepe": cls.UPI,
            "paytm": cls.UPI,
            "cash": cls.CASH,
            "hdfc": cls.HDFC_CC,
            "hdfc cc": cls.HDFC_CC,
            "hdfc credit": cls.HDFC_CC,
            "sbi": cls.SBI_CC,
            "icici": cls.ICICI_CC,
            "axis": cls.AXIS_CC,
            "neft": cls.NEFT_IMPS,
            "imps": cls.NEFT_IMPS,
            "bank transfer": cls.BANK_TRANSFER,
            "transfer": cls.BANK_TRANSFER,
            "emi": cls.EMI,
        }
        if normalised in shortcuts:
            return shortcuts[normalised]
        for member in cls:
            if member.value.lower() == normalised:
                return member
        return cls.OTHER


# ── Debt types ─────────────────────────────────────────────────────────────────


class DebtType(StrEnum):
    HOME_LOAN = "Home Loan"
    CAR_LOAN = "Car Loan"
    PERSONAL_LOAN = "Personal Loan"
    EDUCATION_LOAN = "Education Loan"
    CC_REVOLVING = "Credit Card Revolving"
    OTHER = "Other"


class DebtStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    PAUSED = "paused"


# ── Investment types ───────────────────────────────────────────────────────────


class InvestmentType(StrEnum):
    MUTUAL_FUND = "Mutual Fund"
    STOCK = "Stock"
    ETF = "ETF"
    SGB = "Sovereign Gold Bond"
    REIT = "REIT"
    OTHER = "Other"


class FixedIncomeType(StrEnum):
    FD = "Fixed Deposit"
    RD = "Recurring Deposit"
    PPF = "PPF"
    NPS = "NPS"
    EPF = "EPF"
    NSC = "NSC"
    SSY = "Sukanya Samriddhi"
    OTHER = "Other"


# ── Income types ───────────────────────────────────────────────────────────────


class IncomeType(StrEnum):
    SALARY = "Salary"
    FREELANCE = "Freelance"
    RENTAL = "Rental"
    DIVIDEND = "Dividend"
    INTEREST = "Interest"
    CAPITAL_GAINS = "Capital Gains"
    BONUS = "Bonus"
    OTHER = "Other"


class IncomeFrequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    ONE_TIME = "one_time"


class Taxability(StrEnum):
    FULLY_TAXABLE = "fully_taxable"
    PARTIALLY_EXEMPT = "partially_exempt"
    FULLY_EXEMPT = "fully_exempt"


# ── Asset types ────────────────────────────────────────────────────────────────


class AssetType(StrEnum):
    APARTMENT = "apartment"
    PLOT = "plot"
    COMMERCIAL = "commercial"
    VEHICLE = "vehicle"
    GOLD = "gold"
    OTHER = "other"


class AssetStatus(StrEnum):
    ACTIVE = "active"
    SOLD = "sold"


class PossessionStatus(StrEnum):
    UNDER_CONSTRUCTION = "under_construction"
    POSSESSED = "possessed"
    NA = "na"


class PSFAreaType(StrEnum):
    CARPET = "carpet"
    BUILTIN = "builtin"
    SUPER_BUILTIN = "super_builtin"


class AssetCostType(StrEnum):
    BASE_PRICE = "base_price"
    STAMP_DUTY = "stamp_duty"
    REGISTRATION = "registration"
    GST = "gst"
    LEGAL_FEES = "legal_fees"
    BROKERAGE = "brokerage"
    PARKING = "parking"
    PLC = "plc"
    IFMS = "ifms"
    CLUB_MEMBERSHIP = "club_membership"
    MAINTENANCE_DEPOSIT = "maintenance_deposit"
    IMPROVEMENT = "improvement"
    OTHER = "other"


class AssetMilestone(StrEnum):
    BOOKING = "booking"
    AGREEMENT = "agreement"
    FOUNDATION = "foundation"
    SLAB_1 = "slab_1"
    SLAB_2 = "slab_2"
    SLAB_3 = "slab_3"
    SLAB_4 = "slab_4"
    POSSESSION = "possession"
    REGISTRATION = "registration"
    OTHER = "other"


# ── Insurance types ────────────────────────────────────────────────────────────


class InsuranceType(StrEnum):
    HEALTH = "health"
    LIFE = "life"
    TERM = "term"
    VEHICLE = "vehicle"
    HOME = "home"
    TRAVEL = "travel"
    OTHER = "other"


class InsurancePremiumFrequency(StrEnum):
    ANNUAL = "annual"
    SEMI_ANNUAL = "semi_annual"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"


class InsuranceStatus(StrEnum):
    ACTIVE = "active"
    LAPSED = "lapsed"
    SURRENDERED = "surrendered"
    MATURED = "matured"
