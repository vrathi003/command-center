"""Domain errors for double-entry ledger operations."""


class LedgerError(Exception):
    """Raised when a ledger operation violates an invariant."""


class UnbalancedTransactionError(LedgerError):
    """Raised when signed postings do not sum to zero."""


class DuplicateExternalKeyError(LedgerError):
    """Raised when an external key cannot be reused."""
