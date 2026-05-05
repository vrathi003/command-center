"""Journal API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class JournalEntryOut(BaseModel):
    entry_date: str
    body: str
    created_at: str
    updated_at: str


class JournalPut(BaseModel):
    body: str = Field(default="", max_length=500_000)
