"""Subscription API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubscriptionOut(BaseModel):
    id: int
    name: str
    provider: str | None
    category: str | None
    amount_paise: int
    billing_cycle: str
    monthly_equivalent_paise: int
    next_billing_date: str | None
    notes: str | None
    is_active: bool


class SubscriptionCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=80)
    amount_paise: int = Field(ge=0)
    billing_cycle: str = Field(min_length=1, max_length=20)
    next_billing_date: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class SubscriptionPutBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    provider: str | None = None
    category: str | None = Field(default=None, max_length=80)
    amount_paise: int | None = Field(default=None, ge=0)
    billing_cycle: str | None = Field(default=None, min_length=1, max_length=20)
    next_billing_date: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
