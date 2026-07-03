"""LLM-assisted merchant classification suggestions — batch/on-demand only, never auto-trusted.

Callers must run the returned suggestions through an explicit user-confirmation step before
they are persisted as real merchant_rules (source='llm'). See routers/merchant_rules.py
classify-suggest / classify-confirm for the two-step trust boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from finance_common.parsing.bank_statement_pdf import parse_json_object_from_model_text
from finance_common.repositories.merchant_rules import MerchantRuleRow
from finance_common.types import Category

MAX_MERCHANTS_PER_CALL = 30
MAX_FEW_SHOT_RULES = 20


@dataclass(frozen=True, slots=True)
class LlmSuggestion:
    raw_merchant: str
    canonical_merchant: str
    merchant_type: str | None
    category: str
    confidence: float


def _category_list_for_prompt() -> str:
    return ", ".join(f'"{m.value}"' for m in Category)


def _few_shot_block(known_rules: list[MerchantRuleRow]) -> str:
    sample = [r for r in known_rules if r.source in ("user", "llm")][:MAX_FEW_SHOT_RULES]
    if not sample:
        return "(no prior confirmed examples yet)"
    return "\n".join(
        f'- "{r.match_value}" -> canonical_merchant: "{r.canonical_merchant}", '
        f'merchant_type: {r.merchant_type!r}, category: "{r.category}"'
        for r in sample
    )


_SYSTEM_PROMPT = (
    "You classify raw merchant strings from Indian bank/UPI transaction narrations into a "
    "canonical merchant name, a short merchant type label, and an expense category. "
    "You MUST reply with exactly one JSON object and nothing else: no reasoning, no markdown, "
    "no text before or after the JSON. The first character of your reply must be { and the last "
    "must be }. Only classify merchants given in the input list below — never invent others."
)


def _user_prompt(merchants: list[str], known_rules: list[MerchantRuleRow]) -> str:
    merchant_list = "\n".join(f"- {m}" for m in merchants)
    return f"""Classify each raw merchant string below.

Examples of this user's own already-confirmed classifications (follow this style/granularity):
{_few_shot_block(known_rules)}

Output exactly one JSON object with this shape (nothing else):
{{"suggestions":[{{...}}, ...]}}

Each suggestion must have:
- "raw_merchant": string — copied exactly from the input list below
- "canonical_merchant": string — a clean, short display name for this merchant
- "merchant_type": string or null — a short label for what kind of merchant this is
  (e.g. "Food Delivery Platform"), else null
- "category": one of: {_category_list_for_prompt()}
- "confidence": number between 0 and 1

Merchants to classify:
{merchant_list}
"""


async def suggest_classifications(
    client: AsyncOpenAI,
    model: str,
    merchants: list[str],
    known_rules: list[MerchantRuleRow],
) -> list[LlmSuggestion]:
    """Ask the local LLM to classify a batch of raw merchant strings. Returns [] on any
    request/parse failure rather than raising — callers treat an empty result as
    'nothing to review', consistent with how the bank-statement LLM fallback degrades."""
    batch = [m.strip() for m in merchants[:MAX_MERCHANTS_PER_CALL] if m and m.strip()]
    if not batch:
        return []
    requested = {m.lower() for m in batch}

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(batch, known_rules)},
            ],
            temperature=0,
        )
    except Exception as e:
        msg = f"Local LLM request failed: {e}"
        raise ValueError(msg) from e

    choice = resp.choices[0].message.content
    if not choice:
        return []
    try:
        data = parse_json_object_from_model_text(choice, key="suggestions")
    except ValueError:
        return []
    items = data.get("suggestions")
    if not isinstance(items, list):
        return []

    out: list[LlmSuggestion] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_merchant = str(item.get("raw_merchant") or "").strip()
        # Anti-hallucination: only accept merchants we actually asked about.
        if not raw_merchant or raw_merchant.lower() not in requested:
            continue
        category_raw = item.get("category")
        if not category_raw:
            continue
        category = Category.from_string(str(category_raw))
        # from_string() falls back to OTHER on no match — reject unless the model literally
        # said "Other" (otherwise this hides a category the model hallucinated).
        if category == Category.OTHER and str(category_raw).strip().lower() != "other":
            continue
        canonical = str(item.get("canonical_merchant") or raw_merchant).strip()
        merchant_type = item.get("merchant_type")
        merchant_type_s = str(merchant_type).strip() if merchant_type else None
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        out.append(
            LlmSuggestion(
                raw_merchant=raw_merchant,
                canonical_merchant=canonical,
                merchant_type=merchant_type_s,
                category=category.value,
                confidence=confidence,
            )
        )
    return out
