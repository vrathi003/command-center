"""Pydantic models for merchant rule CRUD and LLM-assisted batch classification."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MerchantRuleCreate(BaseModel):
    match_type: Literal["exact", "contains"] = "contains"
    match_value: str = Field(min_length=1, max_length=200)
    canonical_merchant: str = Field(min_length=1, max_length=120)
    merchant_type: str | None = None
    category: str
    source: Literal["heuristic", "user", "llm"] = "user"
    confidence: float = 1.0
    priority: int = 0


class MerchantRuleUpdate(MerchantRuleCreate):
    pass


class MerchantRuleOut(BaseModel):
    id: int
    match_type: str
    match_value: str
    canonical_merchant: str
    merchant_type: str | None
    category: str
    source: str
    confidence: float
    priority: int
    is_active: bool
    created_at: str
    updated_at: str
    last_matched_at: str | None
    retroactively_applied: int | None = None


class UncategorizedGroupOut(BaseModel):
    merchant: str
    frequency: int
    total_paise: int


class ClassifySuggestBody(BaseModel):
    merchants: list[str] = Field(min_length=1, max_length=50)


class LlmSuggestionOut(BaseModel):
    raw_merchant: str
    canonical_merchant: str
    merchant_type: str | None
    category: str
    confidence: float


class ConfirmedSuggestionIn(BaseModel):
    raw_merchant: str
    match_type: Literal["exact", "contains"] = "exact"
    canonical_merchant: str
    merchant_type: str | None = None
    category: str


class ClassifyConfirmBody(BaseModel):
    suggestions: list[ConfirmedSuggestionIn] = Field(min_length=1, max_length=50)


class ClassifyConfirmResult(BaseModel):
    created: list[MerchantRuleOut]
    total_retroactively_applied: int
