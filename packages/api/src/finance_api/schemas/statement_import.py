"""Pydantic schemas for statement import API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StatementImportRuleOut(BaseModel):
    id: int
    bank: str
    card: str
    from_emails: list[str]
    subject_contains: str | None = None
    pdf_password: str | None = None
    credit_card_id: int | None = None
    is_enabled: bool
    fetch_months: int = 6
    created_at: str | None = None
    updated_at: str | None = None


class StatementImportRuleCreate(BaseModel):
    bank: str = Field(min_length=1)
    card: str = Field(min_length=1)
    from_emails: list[str] = Field(min_length=1)
    subject_contains: str | None = None
    pdf_password: str | None = None
    credit_card_id: int | None = None
    is_enabled: bool = True
    fetch_months: int = Field(default=6, ge=0, le=60)


class StatementImportRuleUpdate(BaseModel):
    bank: str = Field(min_length=1)
    card: str = Field(min_length=1)
    from_emails: list[str] = Field(min_length=1)
    subject_contains: str | None = None
    pdf_password: str | None = None
    credit_card_id: int | None = None
    is_enabled: bool = True
    fetch_months: int = Field(default=6, ge=0, le=60)


class StatementTagRuleOut(BaseModel):
    id: int
    tag_name: str
    regex_patterns: list[str]
    is_enabled: bool


class StatementTagRuleBulkItem(BaseModel):
    tag_name: str = Field(min_length=1)
    regex_patterns: list[str] = Field(min_length=1)
    is_enabled: bool = True


class StatementTagRulesPutBody(BaseModel):
    tags: list[StatementTagRuleBulkItem]


class GmailStatusOut(BaseModel):
    configured: bool
    credentials_path: str | None = None
    llm_enabled: bool = False
    llm_model: str | None = None


class StatementImportFetchResponse(BaseModel):
    gmail_scanned: int
    statements_parsed: int
    skipped: list[dict[str, str]]
    transactions: list[dict[str, Any]]
    snapshot_id: int | None = None
    llm_model: str | None = None
    tags_source: str = "regex"
    category_source: str = "rules"


class StatementImportSnapshotOut(BaseModel):
    id: int
    fetched_at: str
    gmail_scanned: int
    statements_parsed: int
    skipped: list[dict[str, str]]
    transactions: list[dict[str, Any]]


class StatementImportTransactionBody(BaseModel):
    date: str = Field(min_length=1)
    bank: str = Field(min_length=1)
    card: str = Field(min_length=1)
    description: str = Field(min_length=1)
    amount: float
    currency: str = "INR"
    category: str | None = None
    tx_kind: str = "spend"
    tags: str = ""
    statement_period: str = ""
    gmail_message_id: str = ""


class StatementImportTransactionBulkDeleteBody(BaseModel):
    ids: list[str] = Field(min_length=1)
