# Discord Bot Ledger Writes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Discord bot money writes use the ledger when `ledger_engine` is `double_entry`.

**Architecture:** Shared `product_writes` helpers (`plan_postings` / `plan_transfer` + `ledger_service.post` / `void`); bot branches on `uses_ledger_books`.

**Tech Stack:** Python, aiosqlite, finance-common ledger + intake, pytest-asyncio

---

### Task 1: `product_writes` + unit tests

**Files:**
- Create: `packages/common/src/finance_common/ledger/product_writes.py`
- Create: `tests/test_discord_bot_ledger_writes.py`

### Task 2: Wire `ExpenseCog` persist / edit / undo / ❌

**Files:**
- Modify: `packages/bot/src/finance_bot/bot.py`

### Task 3: Full suite + push `main`
