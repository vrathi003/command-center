"""Merchant rules CRUD + LLM-assisted batch classification (suggest → confirm)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn, get_settings
from finance_api.schemas.merchant_rules import (
    ClassifyConfirmBody,
    ClassifyConfirmResult,
    ClassifySuggestBody,
    LlmSuggestionOut,
    MerchantRuleCreate,
    MerchantRuleOut,
    MerchantRuleUpdate,
    UncategorizedGroupOut,
)
from finance_api.settings import ApiSettings
from finance_common.classification.llm_classifier import suggest_classifications
from finance_common.parsing.llm_openai_compat import async_openai_for_local_llm
from finance_common.repositories import merchant_rules as merchant_rules_repo

router = APIRouter(prefix="/merchant-rules", tags=["merchant-rules"])


def _out(
    r: merchant_rules_repo.MerchantRuleRow,
    *,
    retroactively_applied: int | None = None,
    statement_import_applied: int | None = None,
) -> dict[str, object]:
    return {
        "id": r.id,
        "match_type": r.match_type,
        "match_value": r.match_value,
        "canonical_merchant": r.canonical_merchant,
        "merchant_type": r.merchant_type,
        "category": r.category,
        "source": r.source,
        "confidence": r.confidence,
        "priority": r.priority,
        "is_active": r.is_active,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "last_matched_at": r.last_matched_at,
        "retroactively_applied": retroactively_applied,
        "statement_import_applied": statement_import_applied,
    }


@router.get("/")
async def list_rules(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    source: str | None = None,
) -> list[dict[str, object]]:
    rows = await merchant_rules_repo.list_rules(conn, source=source)
    return [_out(r) for r in rows]


@router.get("/uncategorized", response_model=list[UncategorizedGroupOut])
async def list_uncategorized(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    limit: int = 100,
) -> list[UncategorizedGroupOut]:
    groups = await merchant_rules_repo.list_uncategorized_grouped(conn, limit=limit)
    return [
        UncategorizedGroupOut(
            merchant=g.merchant,
            frequency=g.frequency,
            total_paise=g.total_paise,
            sources=list(g.sources),
        )
        for g in groups
    ]


@router.post("/", response_model=MerchantRuleOut, status_code=201)
async def create_rule(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: MerchantRuleCreate,
) -> dict[str, object]:
    try:
        rid = await merchant_rules_repo.create_rule(
            conn,
            match_type=body.match_type,
            match_value=body.match_value,
            canonical_merchant=body.canonical_merchant,
            merchant_type=body.merchant_type,
            category=body.category,
            source=body.source,
            confidence=body.confidence,
            priority=body.priority,
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=409, detail="an active rule already exists for this match value"
        ) from e
    ledger_applied, statement_applied = await merchant_rules_repo.bulk_apply_rule(conn, rid)
    row = await merchant_rules_repo.get_rule(conn, rid)
    if row is None:
        raise HTTPException(status_code=500, detail="rule not found after create")
    return _out(
        row,
        retroactively_applied=ledger_applied,
        statement_import_applied=statement_applied,
    )


@router.put("/{rule_id}", response_model=MerchantRuleOut)
async def update_rule(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    rule_id: int,
    body: MerchantRuleUpdate,
) -> dict[str, object]:
    try:
        ok = await merchant_rules_repo.update_rule(
            conn,
            rule_id,
            match_type=body.match_type,
            match_value=body.match_value,
            canonical_merchant=body.canonical_merchant,
            merchant_type=body.merchant_type,
            category=body.category,
            confidence=body.confidence,
            priority=body.priority,
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=409, detail="an active rule already exists for this match value"
        ) from e
    if not ok:
        raise HTTPException(status_code=404, detail="rule not found")
    ledger_applied, statement_applied = await merchant_rules_repo.bulk_apply_rule(conn, rule_id)
    row = await merchant_rules_repo.get_rule(conn, rule_id)
    if row is None:
        raise HTTPException(status_code=500, detail="rule not found after update")
    return _out(
        row,
        retroactively_applied=ledger_applied,
        statement_import_applied=statement_applied,
    )


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    rule_id: int,
) -> None:
    ok = await merchant_rules_repo.deactivate_rule(conn, rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="rule not found")


@router.post("/classify-suggest", response_model=list[LlmSuggestionOut])
async def classify_suggest(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    api_settings: Annotated[ApiSettings, Depends(get_settings)],
    body: ClassifySuggestBody,
) -> list[LlmSuggestionOut]:
    """Read-only: asks the local LLM to classify a batch of raw merchants. Persists nothing —
    the dashboard shows these as editable, unchecked-by-default suggestions until the user
    calls classify-confirm on the ones they approve."""
    if not api_settings.local_llm_active:
        raise HTTPException(
            status_code=400, detail="Local LLM is not configured (set LOCAL_LLM_URL)"
        )
    known_rules = await merchant_rules_repo.list_rules(conn)
    client = async_openai_for_local_llm(api_settings)
    try:
        suggestions = await suggest_classifications(
            client, api_settings.local_llm_model, body.merchants, known_rules
        )
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return [
        LlmSuggestionOut(
            raw_merchant=s.raw_merchant,
            canonical_merchant=s.canonical_merchant,
            merchant_type=s.merchant_type,
            category=s.category,
            confidence=s.confidence,
        )
        for s in suggestions
    ]


@router.post("/classify-confirm", response_model=ClassifyConfirmResult)
async def classify_confirm(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: ClassifyConfirmBody,
) -> ClassifyConfirmResult:
    """Persists only the suggestions the user explicitly approved (source='llm')."""
    created: list[MerchantRuleOut] = []
    total_ledger = 0
    total_statement = 0
    for s in body.suggestions:
        try:
            rid = await merchant_rules_repo.create_rule(
                conn,
                match_type=s.match_type,
                match_value=s.raw_merchant,
                canonical_merchant=s.canonical_merchant,
                merchant_type=s.merchant_type,
                category=s.category,
                source="llm",
                confidence=0.8,
            )
        except sqlite3.IntegrityError:
            continue  # a rule for this merchant already exists — skip rather than fail the batch
        ledger_applied, statement_applied = await merchant_rules_repo.bulk_apply_rule(conn, rid)
        total_ledger += ledger_applied
        total_statement += statement_applied
        row = await merchant_rules_repo.get_rule(conn, rid)
        if row is not None:
            created.append(
                MerchantRuleOut.model_validate(
                    _out(
                        row,
                        retroactively_applied=ledger_applied,
                        statement_import_applied=statement_applied,
                    )
                )
            )
    return ClassifyConfirmResult(
        created=created,
        total_retroactively_applied=total_ledger,
        total_statement_import_applied=total_statement,
    )
