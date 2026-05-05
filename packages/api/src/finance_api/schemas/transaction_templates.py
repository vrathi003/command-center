"""Pydantic models for transaction template CRUD."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TransactionTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    amount: int | None = Field(default=None, description="Amount in paise; null = fill at use time")
    merchant: str | None = None
    category: str | None = None
    account_id: int | None = None
    payment_mode: str | None = None
    transaction_type: Literal["debit", "credit", "transfer"] = "debit"
    notes: str | None = None
    tags: str | None = None


class TransactionTemplateUpdate(TransactionTemplateCreate):
    pass


class TransactionTemplateOut(BaseModel):
    id: int
    name: str
    amount: int | None
    merchant: str | None
    category: str | None
    account_id: int | None
    payment_mode: str | None
    transaction_type: str
    notes: str | None
    tags: str | None
    created_at: str
