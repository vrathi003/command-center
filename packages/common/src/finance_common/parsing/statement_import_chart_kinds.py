"""Chart kind resolution for statement import (mirrors dashboard logic)."""

from __future__ import annotations

REFUND_MATCH_TOLERANCE_INR = 15


def _tx_kind(row: dict) -> str:
    return str(row.get("tx_kind") or "spend").lower()


def _amounts_match(spend_amount: float, refund_amount: float) -> bool:
    diff = abs(abs(spend_amount) - abs(refund_amount))
    return diff <= REFUND_MATCH_TOLERANCE_INR


def _match_score(spend: dict, refund: dict) -> float:
    diff = abs(abs(float(spend["amount"])) - abs(float(refund["amount"])))
    same_period = 0 if spend.get("statement_period") == refund.get("statement_period") else 1
    date_ok = 0 if spend["date"] <= refund["date"] else 1
    return same_period * 1000 + date_ok * 100 + diff


def resolve_chart_kind_rows(rows: list[dict]) -> list[dict]:
    spends = [r for r in rows if _tx_kind(r) == "spend"]
    refunds = [r for r in rows if _tx_kind(r) == "refund"]
    others = [r for r in rows if _tx_kind(r) not in ("spend", "refund")]

    used_spend_ids: set[str] = set()
    offset_refund_ids: set[str] = set()

    for refund in refunds:
        best: tuple[dict, float] | None = None
        for spend in spends:
            if spend["id"] in used_spend_ids:
                continue
            if spend["bank"] != refund["bank"] or spend["card"] != refund["card"]:
                continue
            if not _amounts_match(float(spend["amount"]), float(refund["amount"])):
                continue
            score = _match_score(spend, refund)
            if best is None or score < best[1]:
                best = (spend, score)
        if best:
            used_spend_ids.add(best[0]["id"])
            offset_refund_ids.add(refund["id"])

    result: list[dict] = []
    for t in spends:
        if t["id"] in used_spend_ids:
            continue
        result.append({"id": t["id"], "kind": "spend", "amount": abs(float(t["amount"]))})
    for t in refunds:
        if t["id"] in offset_refund_ids:
            continue
        result.append({"id": t["id"], "kind": "payment", "amount": abs(float(t["amount"]))})
    for t in others:
        result.append({"id": t["id"], "kind": _tx_kind(t), "amount": abs(float(t["amount"]))})
    return result


def aggregate_chart_kinds_by_type(rows: list[dict]) -> dict[str, dict[str, float | int]]:
    sums: dict[str, dict[str, float | int]] = {}
    for row in resolve_chart_kind_rows(rows):
        kind = row["kind"]
        if kind not in sums:
            sums[kind] = {"count": 0, "amount": 0.0}
        sums[kind]["count"] = int(sums[kind]["count"]) + 1
        sums[kind]["amount"] = float(sums[kind]["amount"]) + float(row["amount"])
    return sums
