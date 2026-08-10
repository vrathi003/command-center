"""LLM classification of credit-card statement lines (kind + category).

Used by statement import preview when LOCAL_LLM_URL is configured.
Model comes from AppSettings.local_llm_model (default qwen2.5:1.5b via Ollama).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finance_common.config import AppSettings
from finance_common.parsing.bank_statement_pdf import parse_json_object_from_model_text
from finance_common.parsing.llm_openai_compat import async_openai_for_local_llm
from finance_common.types import Category

MAX_LINES_PER_CALL = 25

VALID_KINDS = frozenset({"spend", "payment", "refund", "fee", "interest", "cashback"})


@dataclass(frozen=True, slots=True)
class CcLineClassification:
    description: str
    kind: str
    category: str


def _category_list_for_prompt() -> str:
    return ", ".join(f'"{m.value}"' for m in Category)


_SYSTEM_PROMPT = (
    "You classify Indian credit card statement transaction descriptions. "
    "Reply with exactly one JSON object, no markdown or reasoning."
)


def _user_prompt(lines: list[dict[str, Any]]) -> str:
    items = []
    for line in lines:
        desc = str(line.get("description") or "").strip()
        hint_kind = str(line.get("tx_kind") or "spend")
        hint_type = str(line.get("transaction_type") or "debit")
        items.append(
            f'- description: {desc!r}, parser_hint_kind: {hint_kind!r}, '
            f'parser_hint_type: {hint_type!r}'
        )
    block = "\n".join(items)
    return f"""Classify each credit card statement line below.

kind must be exactly one of:
- spend — purchase, charge, EMI debit, merchant payment OUT on the card
- payment — paying the card bill (BBPS, payment received, thank you, amount paid)
- refund — merchant reversal, credit note, purchase refund (NOT a bill payment)
- fee — late fee, annual fee, forex fee, service charge
- interest — finance/interest charges
- cashback — reward points redemption, cashback credit

Rules:
- Bill payments are NEVER refunds even if they are credits on the statement.
- Refunds reverse a prior purchase; bill payments reduce card balance from your bank.
- category: one of {_category_list_for_prompt()}; use Transfer for payment,
  Income for cashback, Bank Charges for fee/interest unless clearly otherwise.

Output exactly:
{{"classifications":[{{"description":"...", "kind":"...", "category":"..."}}, ...]}}

Lines:
{block}
"""


def _needs_llm(line: dict[str, Any]) -> bool:
    """Credit lines and uncategorized spends benefit from LLM disambiguation."""
    if str(line.get("category_source") or "") == "rules" and str(line.get("category") or "Other") != "Other":
        kind = str(line.get("tx_kind") or "")
        tx_type = str(line.get("transaction_type") or "")
        if tx_type == "credit" or kind in ("refund", "payment"):
            return True
        return False
    kind = str(line.get("tx_kind") or "")
    tx_type = str(line.get("transaction_type") or "")
    category = str(line.get("category") or "Other")
    if tx_type == "credit":
        return True
    if kind in ("refund", "payment"):
        return True
    return category == "Other" and kind == "spend"


async def enrich_cc_line_items_with_llm(
    items: list[dict[str, Any]],
    settings: AppSettings,
) -> tuple[list[dict[str, Any]], str | None]:
    """Apply LLM kind/category overrides where helpful. Returns (items, model_used)."""
    if not settings.local_llm_active or not items:
        return items, None

    to_classify = [it for it in items if _needs_llm(it)]
    if not to_classify:
        return items, None

    try:
        client = async_openai_for_local_llm(
            settings,
            timeout_override=settings.local_llm_narration_timeout_seconds,
        )
    except ValueError:
        return items, None

    model = settings.local_llm_model
    by_desc: dict[str, CcLineClassification] = {}

    for start in range(0, len(to_classify), MAX_LINES_PER_CALL):
        batch = to_classify[start : start + MAX_LINES_PER_CALL]
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _user_prompt(batch)},
                ],
                temperature=0,
            )
            content = resp.choices[0].message.content
            if not content:
                continue
            data = parse_json_object_from_model_text(content, key="classifications")
        except Exception:
            continue

        rows = data.get("classifications")
        if not isinstance(rows, list):
            continue

        requested = {str(it.get("description") or "").strip().lower() for it in batch}
        for row in rows:
            if not isinstance(row, dict):
                continue
            desc = str(row.get("description") or "").strip()
            if not desc or desc.lower() not in requested:
                continue
            kind_raw = str(row.get("kind") or "").strip().lower()
            if kind_raw not in VALID_KINDS:
                continue
            cat_raw = row.get("category")
            if not cat_raw:
                continue
            category = Category.from_string(str(cat_raw))
            if category == Category.OTHER and str(cat_raw).strip().lower() != "other":
                continue
            by_desc[desc.lower()] = CcLineClassification(
                description=desc,
                kind=kind_raw,
                category=category.value,
            )

    if not by_desc:
        return items, model

    out: list[dict[str, Any]] = []
    for item in items:
        desc = str(item.get("description") or "").strip()
        hit = by_desc.get(desc.lower())
        if hit is None:
            out.append(item)
            continue
        merged = {**item, "tx_kind": hit.kind, "transaction_type": _kind_to_tx_type(hit.kind)}
        if str(item.get("category_source") or "") != "rules" or str(item.get("category") or "Other") == "Other":
            merged["category"] = hit.category
            merged["category_source"] = "llm"
        out.append(merged)
    return out, model


def _kind_to_tx_type(kind: str) -> str:
    if kind in ("payment", "refund", "cashback"):
        return "credit"
    return "debit"
