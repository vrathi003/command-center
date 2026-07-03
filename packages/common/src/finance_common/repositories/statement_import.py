"""Statement import rules, tag rules, snapshots, and Gmail dedup."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class StatementImportRuleRow:
    id: int
    bank: str
    card: str
    from_emails: list[str]
    subject_contains: str | None
    pdf_password: str | None
    credit_card_id: int | None
    is_enabled: bool
    created_at: str | None
    updated_at: str | None


@dataclass(frozen=True, slots=True)
class StatementTagRuleRow:
    id: int
    tag_name: str
    regex_patterns: list[str]
    is_enabled: bool
    created_at: str | None
    updated_at: str | None


@dataclass(frozen=True, slots=True)
class StatementImportSnapshotRow:
    id: int
    fetched_at: str
    gmail_scanned: int
    statements_parsed: int
    skipped_json: str | None
    transactions_json: str
    source_gmail_ids_json: str


def _parse_emails_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x).strip()]


def _parse_patterns_json(raw: str | None) -> list[str]:
    return _parse_emails_json(raw)


def _rule_from_tuple(r: tuple[Any, ...]) -> StatementImportRuleRow:
    return StatementImportRuleRow(
        id=int(r[0]),
        bank=str(r[1]),
        card=str(r[2]),
        from_emails=_parse_emails_json(str(r[3]) if r[3] is not None else None),
        subject_contains=str(r[4]) if r[4] is not None else None,
        pdf_password=str(r[5]) if r[5] is not None else None,
        credit_card_id=int(r[6]) if r[6] is not None else None,
        is_enabled=bool(int(r[7])),
        created_at=str(r[8]) if len(r) > 8 and r[8] is not None else None,
        updated_at=str(r[9]) if len(r) > 9 and r[9] is not None else None,
    )


def _tag_from_tuple(r: tuple[Any, ...]) -> StatementTagRuleRow:
    return StatementTagRuleRow(
        id=int(r[0]),
        tag_name=str(r[1]),
        regex_patterns=_parse_patterns_json(str(r[2]) if r[2] is not None else None),
        is_enabled=bool(int(r[3])),
        created_at=str(r[4]) if len(r) > 4 and r[4] is not None else None,
        updated_at=str(r[5]) if len(r) > 5 and r[5] is not None else None,
    )


def _snapshot_from_tuple(r: tuple[Any, ...]) -> StatementImportSnapshotRow:
    return StatementImportSnapshotRow(
        id=int(r[0]),
        fetched_at=str(r[1]),
        gmail_scanned=int(r[2]),
        statements_parsed=int(r[3]),
        skipped_json=str(r[4]) if r[4] is not None else None,
        transactions_json=str(r[5]) if r[5] is not None else "[]",
        source_gmail_ids_json=str(r[6]) if r[6] is not None else "[]",
    )


_RULE_SELECT = """
    SELECT id, bank, card, from_emails_json, subject_contains, pdf_password,
           credit_card_id, is_enabled, created_at, updated_at
    FROM statement_import_rules
"""


async def count_rules(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute("SELECT COUNT(*) FROM statement_import_rules")
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def list_rules(
    conn: aiosqlite.Connection,
    *,
    enabled_only: bool = False,
) -> list[StatementImportRuleRow]:
    if enabled_only:
        cur = await conn.execute(
            _RULE_SELECT + " WHERE is_enabled = 1 ORDER BY bank, card, id"
        )
    else:
        cur = await conn.execute(_RULE_SELECT + " ORDER BY bank, card, id")
    rows = await cur.fetchall()
    return [_rule_from_tuple(r) for r in rows]


async def get_rule(conn: aiosqlite.Connection, rule_id: int) -> StatementImportRuleRow | None:
    cur = await conn.execute(_RULE_SELECT + " WHERE id = ?", (rule_id,))
    row = await cur.fetchone()
    return _rule_from_tuple(row) if row else None


async def create_rule(
    conn: aiosqlite.Connection,
    *,
    bank: str,
    card: str,
    from_emails: list[str],
    subject_contains: str | None = None,
    pdf_password: str | None = None,
    credit_card_id: int | None = None,
    is_enabled: bool = True,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO statement_import_rules (
            bank, card, from_emails_json, subject_contains, pdf_password,
            credit_card_id, is_enabled, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            bank.strip(),
            card.strip(),
            json.dumps(from_emails),
            subject_contains.strip() if subject_contains else None,
            pdf_password,
            credit_card_id,
            1 if is_enabled else 0,
        ),
    )
    await conn.commit()
    return int(cur.lastrowid)


async def update_rule(
    conn: aiosqlite.Connection,
    rule_id: int,
    *,
    bank: str,
    card: str,
    from_emails: list[str],
    subject_contains: str | None = None,
    pdf_password: str | None = None,
    credit_card_id: int | None = None,
    is_enabled: bool = True,
) -> bool:
    cur = await conn.execute(
        """
        UPDATE statement_import_rules SET
            bank = ?, card = ?, from_emails_json = ?, subject_contains = ?,
            pdf_password = ?, credit_card_id = ?, is_enabled = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            bank.strip(),
            card.strip(),
            json.dumps(from_emails),
            subject_contains.strip() if subject_contains else None,
            pdf_password,
            credit_card_id,
            1 if is_enabled else 0,
            rule_id,
        ),
    )
    await conn.commit()
    return cur.rowcount > 0


async def delete_rule(conn: aiosqlite.Connection, rule_id: int) -> bool:
    cur = await conn.execute("DELETE FROM statement_import_rules WHERE id = ?", (rule_id,))
    await conn.commit()
    return cur.rowcount > 0


async def list_tag_rules(conn: aiosqlite.Connection) -> list[StatementTagRuleRow]:
    cur = await conn.execute(
        """
        SELECT id, tag_name, regex_patterns_json, is_enabled, created_at, updated_at
        FROM statement_tag_rules ORDER BY tag_name, id
        """
    )
    rows = await cur.fetchall()
    return [_tag_from_tuple(r) for r in rows]


async def replace_tag_rules(
    conn: aiosqlite.Connection,
    rules: list[tuple[str, list[str], bool]],
) -> None:
    await conn.execute("DELETE FROM statement_tag_rules")
    for tag_name, patterns, is_enabled in rules:
        await conn.execute(
            """
            INSERT INTO statement_tag_rules (tag_name, regex_patterns_json, is_enabled, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (tag_name.strip(), json.dumps(patterns), 1 if is_enabled else 0),
        )
    await conn.commit()


async def is_gmail_message_fetched(conn: aiosqlite.Connection, gmail_message_id: str) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM statement_import_fetched_messages WHERE gmail_message_id = ? LIMIT 1",
        (gmail_message_id,),
    )
    return await cur.fetchone() is not None


async def record_fetched_message(
    conn: aiosqlite.Connection,
    *,
    gmail_message_id: str,
    rule_id: int,
) -> None:
    await conn.execute(
        """
        INSERT OR IGNORE INTO statement_import_fetched_messages (gmail_message_id, rule_id)
        VALUES (?, ?)
        """,
        (gmail_message_id, rule_id),
    )
    await conn.commit()


async def insert_snapshot(
    conn: aiosqlite.Connection,
    *,
    gmail_scanned: int,
    statements_parsed: int,
    skipped: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    source_gmail_ids: list[str],
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO statement_import_snapshots (
            gmail_scanned, statements_parsed, skipped_json,
            transactions_json, source_gmail_ids_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            gmail_scanned,
            statements_parsed,
            json.dumps(skipped, ensure_ascii=False),
            json.dumps(transactions, ensure_ascii=False),
            json.dumps(source_gmail_ids),
        ),
    )
    await conn.commit()
    return int(cur.lastrowid)


async def get_latest_snapshot(conn: aiosqlite.Connection) -> StatementImportSnapshotRow | None:
    cur = await conn.execute(
        """
        SELECT id, fetched_at, gmail_scanned, statements_parsed, skipped_json,
               transactions_json, source_gmail_ids_json
        FROM statement_import_snapshots
        ORDER BY id DESC LIMIT 1
        """
    )
    row = await cur.fetchone()
    return _snapshot_from_tuple(row) if row else None
