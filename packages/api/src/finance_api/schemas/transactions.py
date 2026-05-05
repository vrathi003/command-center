"""Transaction import API schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TransactionImportRowError(BaseModel):
    row: int = Field(ge=1, description="1-based data row in the file")
    message: str


class TransactionImportResponse(BaseModel):
    imported: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: list[TransactionImportRowError] = Field(default_factory=list)


class TransactionBulkDeleteBody(BaseModel):
    ids: list[int] = Field(
        min_length=1,
        max_length=200,
        description=(
            "Transaction ids to soft-delete (max 200 per request — bounded JSON body and "
            "single SQL batch; clients should chunk larger deletes)."
        ),
    )


class TransactionBulkDeleteResponse(BaseModel):
    deleted: int = Field(ge=0, description="Rows marked deleted")


class TransactionCreate(BaseModel):
    """Manual single transaction (debit/credit)."""

    date: str = Field(min_length=10, max_length=10, description="YYYY-MM-DD")
    amount_paise: int = Field(
        gt=0,
        description="Always positive; use transaction_type for direction",
    )
    category: str
    merchant: str | None = None
    payment_mode: str
    transaction_type: Literal["debit", "credit"] = "debit"
    account: str | None = None
    account_id: int | None = None
    notes: str | None = None
    tags: str | None = None
    source: str = "dashboard"


class TransferCreate(BaseModel):
    amount_paise: int = Field(gt=0)
    from_account_id: int = Field(gt=0)
    to_account_id: int = Field(gt=0)
    date: str = Field(min_length=10, max_length=10)
    notes: str | None = None
    tags: str | None = None


class TransferResponse(BaseModel):
    transfer_pair_id: str
    debit_transaction_id: int
    credit_transaction_id: int


class TransactionCreated(BaseModel):
    id: int


class TransactionDashboardUpdate(BaseModel):
    """Dashboard edit payload: debit/credit fields and optional transfer accounts."""

    date: str = Field(min_length=10, max_length=10, description="YYYY-MM-DD")
    amount_paise: int = Field(gt=0)
    category: str | None = None
    merchant: str | None = None
    payment_mode: str | None = None
    transaction_type: Literal["debit", "credit"] | None = None
    account_id: int | None = None
    notes: str | None = None
    tags: str | None = None
    from_account_id: int | None = None
    to_account_id: int | None = None


class TransactionUpdated(BaseModel):
    id: int
