"""CRUD for `merchant_rules` (merchant identity + category classification)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import aiosqlite

from finance_common.repositories import statement_import as si_repo


@dataclass(frozen=True, slots=True)
class MerchantRuleRow:
    id: int
    match_type: str  # 'exact' | 'contains'
    match_value: str
    canonical_merchant: str
    merchant_type: str | None
    category: str
    source: str  # 'heuristic' | 'user' | 'llm'
    confidence: float
    priority: int
    is_active: bool
    created_at: str
    updated_at: str
    last_matched_at: str | None


@dataclass(frozen=True, slots=True)
class UncategorizedGroup:
    merchant: str
    frequency: int
    total_paise: int
    sources: tuple[str, ...] = ()


_COLUMNS = (
    "id, match_type, match_value, canonical_merchant, merchant_type, category, "
    "source, confidence, priority, is_active, created_at, updated_at, last_matched_at"
)


def _row(r: tuple[object, ...]) -> MerchantRuleRow:
    return MerchantRuleRow(
        id=int(r[0]),
        match_type=str(r[1]),
        match_value=str(r[2]),
        canonical_merchant=str(r[3]),
        merchant_type=str(r[4]) if r[4] else None,
        category=str(r[5]),
        source=str(r[6]),
        confidence=float(r[7]),
        priority=int(r[8]),
        is_active=bool(r[9]),
        created_at=str(r[10]),
        updated_at=str(r[11]),
        last_matched_at=str(r[12]) if r[12] else None,
    )


async def list_rules(
    conn: aiosqlite.Connection, *, source: str | None = None
) -> list[MerchantRuleRow]:
    if source is not None:
        cur = await conn.execute(
            f"SELECT {_COLUMNS} FROM merchant_rules WHERE is_active = 1 AND source = ? "
            "ORDER BY canonical_merchant COLLATE NOCASE",
            (source,),
        )
    else:
        cur = await conn.execute(
            f"SELECT {_COLUMNS} FROM merchant_rules WHERE is_active = 1 "
            "ORDER BY canonical_merchant COLLATE NOCASE"
        )
    rows = await cur.fetchall()
    return [_row(tuple(r)) for r in rows]


async def list_active_rules_for_matching(conn: aiosqlite.Connection) -> list[MerchantRuleRow]:
    """All active rules, unordered — callers rank matches (see classification.matcher)."""
    cur = await conn.execute(f"SELECT {_COLUMNS} FROM merchant_rules WHERE is_active = 1")
    rows = await cur.fetchall()
    return [_row(tuple(r)) for r in rows]


async def get_rule(conn: aiosqlite.Connection, rule_id: int) -> MerchantRuleRow | None:
    cur = await conn.execute(f"SELECT {_COLUMNS} FROM merchant_rules WHERE id = ?", (rule_id,))
    r = await cur.fetchone()
    return _row(tuple(r)) if r else None


async def create_rule(
    conn: aiosqlite.Connection,
    *,
    match_type: str,
    match_value: str,
    canonical_merchant: str,
    merchant_type: str | None,
    category: str,
    source: str = "user",
    confidence: float = 1.0,
    priority: int = 0,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO merchant_rules (
            match_type, match_value, canonical_merchant, merchant_type,
            category, source, confidence, priority
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            match_type,
            match_value.strip().lower(),
            canonical_merchant.strip(),
            merchant_type,
            category,
            source,
            confidence,
            priority,
        ),
    )
    await conn.commit()
    lid = cur.lastrowid
    if lid is None:
        msg = "INSERT merchant_rules did not set lastrowid"
        raise RuntimeError(msg)
    return int(lid)


async def update_rule(
    conn: aiosqlite.Connection,
    rule_id: int,
    *,
    match_type: str,
    match_value: str,
    canonical_merchant: str,
    merchant_type: str | None,
    category: str,
    confidence: float,
    priority: int,
) -> bool:
    cur = await conn.execute(
        """
        UPDATE merchant_rules SET
            match_type = ?, match_value = ?, canonical_merchant = ?, merchant_type = ?,
            category = ?, confidence = ?, priority = ?, updated_at = datetime('now')
        WHERE id = ? AND is_active = 1
        """,
        (
            match_type,
            match_value.strip().lower(),
            canonical_merchant.strip(),
            merchant_type,
            category,
            confidence,
            priority,
            rule_id,
        ),
    )
    await conn.commit()
    return cur.rowcount > 0


async def deactivate_rule(conn: aiosqlite.Connection, rule_id: int) -> bool:
    cur = await conn.execute(
        """
        UPDATE merchant_rules SET is_active = 0, updated_at = datetime('now')
        WHERE id = ? AND is_active = 1
        """,
        (rule_id,),
    )
    await conn.commit()
    return cur.rowcount > 0


async def list_uncategorized_grouped(
    conn: aiosqlite.Connection, *, limit: int = 100
) -> list[UncategorizedGroup]:
    """Uncategorized spend merchants from ledger + latest statement-import snapshot."""
    cur = await conn.execute(
        """
        SELECT merchant, COUNT(*) AS freq, SUM(amount_paise) AS total_paise
        FROM transactions
        WHERE is_deleted = 0 AND category = 'Other' AND merchant IS NOT NULL AND merchant != ''
        GROUP BY merchant
        ORDER BY freq DESC
        """
    )
    rows = await cur.fetchall()
    merged: dict[str, UncategorizedGroup] = {}
    for r in rows:
        merchant = str(r[0])
        key = merchant.lower()
        merged[key] = UncategorizedGroup(
            merchant=merchant,
            frequency=int(r[1]),
            total_paise=int(r[2] or 0),
            sources=("ledger",),
        )

    snapshot = await si_repo.get_latest_snapshot(conn)
    if snapshot is not None:
        try:
            tx_rows = json.loads(snapshot.transactions_json or "[]")
        except json.JSONDecodeError:
            tx_rows = []
        if isinstance(tx_rows, list):
            si_counts: dict[str, tuple[str, int, float]] = {}
            for t in tx_rows:
                if not isinstance(t, dict):
                    continue
                kind = str(t.get("tx_kind") or "spend").lower()
                if kind != "spend":
                    continue
                cat = str(t.get("category") or "Other")
                if cat != "Other":
                    continue
                desc = str(t.get("description") or "").strip()
                if not desc:
                    continue
                key = desc.lower()
                display, freq, total = si_counts.get(key, (desc, 0, 0.0))
                si_counts[key] = (display, freq + 1, total + abs(float(t.get("amount") or 0)))

            for key, (display, freq, total_rupees) in si_counts.items():
                paise = int(round(total_rupees * 100))
                existing = merged.get(key)
                if existing:
                    sources = tuple(sorted(set((*existing.sources, "statement_import"))))
                    merged[key] = UncategorizedGroup(
                        merchant=existing.merchant,
                        frequency=existing.frequency + freq,
                        total_paise=existing.total_paise + paise,
                        sources=sources,
                    )
                else:
                    merged[key] = UncategorizedGroup(
                        merchant=display,
                        frequency=freq,
                        total_paise=paise,
                        sources=("statement_import",),
                    )

    return sorted(merged.values(), key=lambda g: g.frequency, reverse=True)[:limit]


def _text_matches_rule(text: str, rule: MerchantRuleRow) -> bool:
    low = text.lower()
    if rule.match_type == "exact":
        return low == rule.match_value
    return rule.match_value in low


async def bulk_apply_rule_to_statement_import(conn: aiosqlite.Connection, rule_id: int) -> int:
    """Apply a rule to spend lines in the latest statement-import snapshot."""
    rule = await get_rule(conn, rule_id)
    if rule is None:
        return 0
    snapshot = await si_repo.get_latest_snapshot(conn)
    if snapshot is None:
        return 0
    try:
        transactions = json.loads(snapshot.transactions_json or "[]")
    except json.JSONDecodeError:
        return 0
    if not isinstance(transactions, list):
        return 0

    updated = 0
    for t in transactions:
        if not isinstance(t, dict):
            continue
        if str(t.get("tx_kind") or "spend").lower() != "spend":
            continue
        desc = str(t.get("description") or "").strip()
        if not desc or not _text_matches_rule(desc, rule):
            continue
        t["category"] = rule.category
        t["description"] = rule.canonical_merchant
        t["category_source"] = "rules"
        updated += 1

    if updated > 0:
        await si_repo.update_snapshot_transactions(conn, snapshot.id, transactions)
    return updated


async def bulk_apply_rule(conn: aiosqlite.Connection, rule_id: int) -> tuple[int, int]:
    """Retroactively apply a rule to ledger transactions and statement-import preview."""
    ledger = await bulk_apply_rule_to_transactions(conn, rule_id)
    statement = await bulk_apply_rule_to_statement_import(conn, rule_id)
    return ledger, statement


async def bulk_apply_rule_to_transactions(conn: aiosqlite.Connection, rule_id: int) -> int:
    """Retroactively apply a rule's category + canonical merchant to matching existing rows."""
    rule = await get_rule(conn, rule_id)
    if rule is None:
        return 0
    if rule.match_type == "exact":
        cur = await conn.execute(
            """
            UPDATE transactions
            SET category = ?, merchant = ?, updated_at = datetime('now')
            WHERE is_deleted = 0 AND LOWER(merchant) = ?
            """,
            (rule.category, rule.canonical_merchant, rule.match_value),
        )
    else:
        cur = await conn.execute(
            """
            UPDATE transactions
            SET category = ?, merchant = ?, updated_at = datetime('now')
            WHERE is_deleted = 0 AND LOWER(merchant) LIKE '%' || ? || '%'
            """,
            (rule.category, rule.canonical_merchant, rule.match_value),
        )
    await conn.commit()
    return cur.rowcount
