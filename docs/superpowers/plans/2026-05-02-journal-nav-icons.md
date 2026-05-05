# Journal + sidebar icons — Implementation Plan

> **For agentic workers:** Use **superpowers:subagent-driven-development** (recommended) or **superpowers:executing-plans** to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `journal_entries` in SQLite with REST endpoints, a `/journal` dashboard page (month grid + markdown editor + sanitized preview), and **lucide-react** icons for every sidebar item including the new Journal link (between Reports and Settings).

**Architecture:** Follow existing **vertical slice**: `schema.sql` + optional `migrations.py` guard (for parity with older DB bootstrap habits), **`finance_common.repositories`** module, **`finance_api` router + Pydantic schemas**, **`TestClient`** API tests, then **`dashboard`** (`api.ts`, `types/api.ts`, `JournalPage`, `App.tsx`, `AppShell.tsx`). No `audit_log` writes for journal.

**Tech Stack:** SQLite, aiosqlite, FastAPI, Pydantic v2, pytest + Starlette `TestClient`, React 19, TanStack Query v5, Vite, Tailwind 4, **lucide-react**, **react-markdown**, **rehype-sanitize**, **remark-gfm**.

**User constraint:** Do **not** run git commands during this work unless the user asks.

---

## File map (create / modify)

| Path | Role |
|------|------|
| `packages/common/src/finance_common/db/schema.sql` | Append `CREATE TABLE IF NOT EXISTS journal_entries (...)` |
| `packages/common/src/finance_common/db/migrations.py` | Append `sqlite_master` check + `CREATE TABLE journal_entries` if missing (mirror `home_items` block style) |
| `packages/common/src/finance_common/repositories/journal.py` | **Create** — CRUD helpers |
| `packages/api/src/finance_api/schemas/journal.py` | **Create** — `JournalEntryOut`, `JournalPut` |
| `packages/api/src/finance_api/routers/journal.py` | **Create** — GET list, GET by date, PUT upsert/delete |
| `packages/api/src/finance_api/main.py` | Import `journal` router; `app.include_router(journal.router, prefix="/api")` alongside peers |
| `tests/test_journal_api.py` | **Create** — API behavior tests |
| `dashboard/package.json` | Add deps: `lucide-react`, `react-markdown`, `rehype-sanitize`, `remark-gfm` |
| `dashboard/src/types/api.ts` | Add `JournalEntryOut` type |
| `dashboard/src/lib/api.ts` | Add `fetchJournalEntry`, `fetchJournalRange`, `putJournalEntry` |
| `dashboard/src/pages/JournalPage.tsx` | **Create** — calendar + editor + preview + save |
| `dashboard/src/App.tsx` | Register `<Route path="journal" element={<JournalPage />} />` |
| `dashboard/src/components/layout/AppShell.tsx` | Icons per nav row + Journal `NavLink` |

---

## Deferred decisions (locked here)

- **`GET /api/journal/`** with **no** `from`/`to`: return rows where `entry_date >= (today - 90 days)` AND `entry_date <= today`, ordered by `entry_date` descending. Only days with rows are returned.
- **Calendar:** custom month grid (no new npm calendar dependency): `Intl` + `Date`, Sunday or Monday week start — pick **Monday** start to match common Indian calendar apps; document in code comment.
- **Journal nav icon:** `NotebookPen` from `lucide-react`.

---

## Spec coverage checklist (self-review)

| Spec section | Tasks |
|--------------|-------|
| Table `journal_entries` | Task 1–2 |
| GET/PUT/GET list + validation | Task 3–5 |
| No audit_log | Task 5 (do not import audit helpers) |
| Dashboard route + shell icons | Task 8–9 |
| Markdown + sanitize | Task 7 |
| Acceptance / tests | Task 6, 10 |

---

### Task 1: Add `journal_entries` to `schema.sql`

**Files:**

- Modify: `packages/common/src/finance_common/db/schema.sql` (append near end of file, before any final comments)

**Steps:**

- [ ] **Step 1: Append DDL**

Add exactly:

```sql
CREATE TABLE IF NOT EXISTS journal_entries (
    entry_date TEXT PRIMARY KEY NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 2: Smoke bootstrap**

Run: `uv run python -c "from pathlib import Path; import asyncio; from finance_common.db import ensure_database; asyncio.run(ensure_database(Path('/tmp/pfos-journal-smoke.db')))"`

Expected: no traceback; optional: `sqlite3 /tmp/pfos-journal-smoke.db ".schema journal_entries"` shows the table.

---

### Task 2: Migration guard for `journal_entries`

**Files:**

- Modify: `packages/common/src/finance_common/db/migrations.py` (append at end of `apply_migrations`, before final return if any)

**Steps:**

- [ ] **Step 1: Add migration block**

Mirror the `construction_projects` pattern: query `sqlite_master` for `name='journal_entries'`; if missing, `executescript` the same `CREATE TABLE journal_entries (...)` as in Task 1 (without `IF NOT EXISTS` is fine inside guarded block), then `commit`.

- [ ] **Step 2: Re-run tests later** (Task 6) — ensures `api_client` fixture still gets DB with table.

---

### Task 3: Repository `finance_common.repositories.journal`

**Files:**

- Create: `packages/common/src/finance_common/repositories/journal.py`

**Steps:**

- [ ] **Step 1: Create file with full content**

```python
"""Daily journal entries (one row per calendar date)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class JournalRow:
    entry_date: str
    body: str
    created_at: str
    updated_at: str


def _row(r: tuple[Any, ...]) -> JournalRow:
    return JournalRow(
        entry_date=str(r[0]),
        body=str(r[1]),
        created_at=str(r[2]),
        updated_at=str(r[3]),
    )


async def get_by_date(conn: aiosqlite.Connection, entry_date: str) -> JournalRow | None:
    cur = await conn.execute(
        """
        SELECT entry_date, body, created_at, updated_at
        FROM journal_entries WHERE entry_date = ?
        """,
        (entry_date,),
    )
    r = await cur.fetchone()
    return _row(tuple(r)) if r else None


async def upsert(conn: aiosqlite.Connection, *, entry_date: str, body: str) -> JournalRow:
    await conn.execute(
        """
        INSERT INTO journal_entries (entry_date, body, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(entry_date) DO UPDATE SET
            body = excluded.body,
            updated_at = datetime('now')
        """,
        (entry_date, body),
    )
    await conn.commit()
    row = await get_by_date(conn, entry_date)
    if row is None:
        raise RuntimeError("journal upsert failed")
    return row


async def delete_by_date(conn: aiosqlite.Connection, entry_date: str) -> None:
    await conn.execute("DELETE FROM journal_entries WHERE entry_date = ?", (entry_date,))
    await conn.commit()


async def list_between(
    conn: aiosqlite.Connection, *, date_from: str, date_to: str
) -> list[JournalRow]:
    cur = await conn.execute(
        """
        SELECT entry_date, body, created_at, updated_at
        FROM journal_entries
        WHERE entry_date >= ? AND entry_date <= ?
        ORDER BY entry_date DESC
        """,
        (date_from, date_to),
    )
    rows = await cur.fetchall()
    return [_row(tuple(x)) for x in rows]
```

- [ ] **Step 2: Quick import check**

Run: `uv run python -c "from finance_common.repositories import journal as j; print(j.JournalRow)"`

Expected: prints class or similar without error.

---

### Task 4: Pydantic schemas

**Files:**

- Create: `packages/api/src/finance_api/schemas/journal.py`

**Steps:**

- [ ] **Step 1: Add schemas**

```python
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
```

---

### Task 5: Router `journal.py` + register in `main.py`

**Files:**

- Create: `packages/api/src/finance_api/routers/journal.py`
- Modify: `packages/api/src/finance_api/main.py` (import + `include_router`)

**Steps:**

- [ ] **Step 1: Implement router** (full file)

```python
"""Daily journal API."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder

from finance_api.deps import get_conn
from finance_api.schemas.journal import JournalEntryOut, JournalPut
from finance_common.repositories import journal as journal_repo

router = APIRouter(prefix="/journal", tags=["journal"])


def _parse_iso_date(label: str, value: str) -> str:
    try:
        d = date.fromisoformat(value)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"invalid {label}") from e
    return d.isoformat()


@router.get("/", response_model=list[JournalEntryOut])
async def list_journal_entries(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
) -> list[JournalEntryOut]:
    today = date.today()
    if date_from is None and date_to is None:
        df = (today - timedelta(days=90)).isoformat()
        dt = today.isoformat()
    else:
        if date_from is None or date_to is None:
            raise HTTPException(
                status_code=422, detail="from and to must both be set or both omitted"
            )
        df = _parse_iso_date("from", date_from)
        dt = _parse_iso_date("to", date_to)
        if df > dt:
            raise HTTPException(status_code=422, detail="from must be <= to")

    rows = await journal_repo.list_between(conn, date_from=df, date_to=dt)
    return [
        JournalEntryOut(
            entry_date=r.entry_date,
            body=r.body,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get("/{entry_date}", response_model=JournalEntryOut)
async def get_journal_entry(
    entry_date: str,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> JournalEntryOut:
    d = _parse_iso_date("entry_date", entry_date)
    row = await journal_repo.get_by_date(conn, d)
    if row is None:
        raise HTTPException(status_code=404, detail="journal entry not found")
    return JournalEntryOut(
        entry_date=row.entry_date,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.put("/{entry_date}")
async def put_journal_entry(
    entry_date: str,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: JournalPut,
) -> Response:
    d = _parse_iso_date("entry_date", entry_date)
    text = body.body.strip()
    if text == "":
        await journal_repo.delete_by_date(conn, d)
        return Response(status_code=204)

    row = await journal_repo.upsert(conn, entry_date=d, body=text)
    out = JournalEntryOut(
        entry_date=row.entry_date,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return Response(
        content=jsonable_encoder(out.model_dump()),
        media_type="application/json",
        status_code=200,
    )
```

Note: `get_conn` does not auto-commit; **`journal_repo.upsert` and `journal_repo.delete_by_date` must call `await conn.commit()`** (same as `goals_repo`).

- [ ] **Step 2: Register router**

In `main.py`:

```python
from finance_api.routers import (
    ...
    journal,
)
```

and after other routers:

```python
app.include_router(journal.router, prefix="/api")
```

(Place near `goals` / `settings` alphabetically or grouped with “lifestyle” routers — order only matters for OpenAPI readability.)

---

### Task 6: API tests (TDD-style ordering)

**Files:**

- Create: `tests/test_journal_api.py`

**Steps:**

- [ ] **Step 1: Add tests file**

```python
"""Journal API tests."""

from __future__ import annotations

from datetime import date

from starlette.testclient import TestClient


def test_journal_get_missing(api_client: TestClient) -> None:
    r = api_client.get("/api/journal/2020-01-15")
    assert r.status_code == 404


def test_journal_put_get_round_trip(api_client: TestClient) -> None:
    r = api_client.put(
        "/api/journal/2020-01-15",
        json={"body": "  # Hello\n\nworld  "},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["entry_date"] == "2020-01-15"
    assert data["body"] == "# Hello\n\nworld"

    r = api_client.get("/api/journal/2020-01-15")
    assert r.status_code == 200
    assert r.json()["body"] == "# Hello\n\nworld"


def test_journal_put_empty_deletes(api_client: TestClient) -> None:
    api_client.put("/api/journal/2020-02-01", json={"body": "x"})
    r = api_client.put("/api/journal/2020-02-01", json={"body": "   "})
    assert r.status_code == 204
    r = api_client.get("/api/journal/2020-02-01")
    assert r.status_code == 404


def test_journal_put_empty_idempotent(api_client: TestClient) -> None:
    r = api_client.put("/api/journal/2030-03-03", json={"body": ""})
    assert r.status_code == 204
    r = api_client.get("/api/journal/2030-03-03")
    assert r.status_code == 404


def test_journal_invalid_date(api_client: TestClient) -> None:
    r = api_client.get("/api/journal/not-a-date")
    assert r.status_code == 422


def test_journal_list_default_range(api_client: TestClient) -> None:
    d = date.today().isoformat()
    r = api_client.put(f"/api/journal/{d}", json={"body": "today entry"})
    assert r.status_code == 200
    r = api_client.get("/api/journal/")
    assert r.status_code == 200
    dates = [row["entry_date"] for row in r.json()]
    assert d in dates


def test_journal_list_range(api_client: TestClient) -> None:
    api_client.put("/api/journal/2019-01-01", json={"body": "a"})
    api_client.put("/api/journal/2019-01-31", json={"body": "b"})
    r = api_client.get("/api/journal/?from=2019-01-01&to=2019-01-31")
    assert r.status_code == 200
    dates = sorted(row["entry_date"] for row in r.json())
    assert dates == ["2019-01-01", "2019-01-31"]


def test_journal_list_from_only_rejected(api_client: TestClient) -> None:
    r = api_client.get("/api/journal/?from=2019-01-01")
    assert r.status_code == 422


def test_journal_list_bad_range(api_client: TestClient) -> None:
    r = api_client.get("/api/journal/?from=2019-02-01&to=2019-01-01")
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_journal_api.py -v`

Expected: all pass after Tasks 1–5 are correct.

- [ ] **Step 3: Full suite**

Run: `make test`

Expected: entire suite green.

---

### Task 7: Dashboard — dependencies + API client + types

**Files:**

- Modify: `dashboard/package.json`
- Modify: `dashboard/src/types/api.ts`
- Modify: `dashboard/src/lib/api.ts`

**Steps:**

- [ ] **Step 1: Install npm packages**

From `dashboard/`: `npm install lucide-react react-markdown rehype-sanitize remark-gfm`

- [ ] **Step 2: Add TypeScript type**

In `types/api.ts`, add:

```typescript
export type JournalEntryOut = {
  entry_date: string
  body: string
  created_at: string
  updated_at: string
}
```

- [ ] **Step 3: Add API helpers** in `api.ts` (match existing `fetchGoals` error handling style — copy the `if (!res.ok) throw new Error(...)` pattern):

```typescript
import type { JournalEntryOut } from '@/types/api'

export async function fetchJournalEntry(entryDate: string): Promise<JournalEntryOut | null> {
  const res = await fetch(`${apiBase()}/api/journal/${entryDate}`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`journal get failed: ${res.status}`)
  return (await res.json()) as JournalEntryOut
}

export async function fetchJournalRange(
  from: string,
  to: string,
): Promise<JournalEntryOut[]> {
  const q = new URLSearchParams({ from, to })
  const res = await fetch(`${apiBase()}/api/journal/?${q}`)
  if (!res.ok) throw new Error(`journal list failed: ${res.status}`)
  return (await res.json()) as JournalEntryOut[]
}

export async function putJournalEntry(
  entryDate: string,
  body: string,
): Promise<JournalEntryOut | null> {
  const res = await fetch(`${apiBase()}/api/journal/${entryDate}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  })
  if (res.status === 204) return null
  if (!res.ok) throw new Error(`journal put failed: ${res.status}`)
  return (await res.json()) as JournalEntryOut
}
```

---

### Task 8: `JournalPage.tsx`

**Files:**

- Create: `dashboard/src/pages/JournalPage.tsx`

**Steps:**

- [ ] **Step 1: Implement page** with:

  - `useState` for `selectedDate` (ISO string), `draftBody`, `dirty` flag.
  - `useQuery` keyed `['journal', selectedDate]` calling `fetchJournalEntry`; on success set `draftBody` from server or `''` if null; reset `dirty` when data loads for that date.
  - `useMutation` for save calling `putJournalEntry`; on success invalidate `['journal']` queries (range + day); if result `null`, body was cleared.
  - **Month grid:** derive year/month from `selectedDate`; `fetchJournalRange(firstOfMonth, lastOfMonth)` in `useQuery` key `['journal-month', y, m]` to know which days have dots.
  - **Editor:** `<textarea className="min-h-[240px] w-full font-mono text-sm ...">`
  - **Preview:** `<ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{draftBody}</ReactMarkdown>` inside a `Panel` or bordered div with `prose` classes if you use `@tailwindcss/typography` — if **not** installed, use plain `text-sm space-y-2` and default markdown spacing.
  - **Save** button disabled when `!dirty` (optional: allow force save).
  - Reuse `PageHero`, `PageLoading`, `PageError` like `GoalsPage.tsx`.

- [ ] **Step 2: Lint**

Run: `cd dashboard && npm run lint`

Expected: no new errors.

---

### Task 9: Routes + `AppShell` icons

**Files:**

- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/src/components/layout/AppShell.tsx`

**Steps:**

- [ ] **Step 1: Lazy or static import `JournalPage`**

In `App.tsx`, add route inside `AppShell`:

```tsx
<Route path="journal" element={<JournalPage />} />
```

- [ ] **Step 2: Refactor `NAV`**

Change `NAV` to include `icon` per row, e.g.:

```tsx
import {
  LayoutDashboard,
  Wallet,
  ArrowLeftRight,
  PieChart,
  Landmark,
  CreditCard,
  Repeat,
  TrendingUp,
  Scale,
  Building2,
  HardHat,
  House,
  Shield,
  Target,
  IndianRupee,
  FileText,
  NotebookPen,
  Settings,
  type LucideIcon,
} from 'lucide-react'

const NAV: { to: string; label: string; icon: LucideIcon }[] = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/accounts', label: 'Accounts', icon: Wallet },
  { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { to: '/budget', label: 'Budget', icon: PieChart },
  { to: '/debt', label: 'Debt', icon: Landmark },
  { to: '/credit-cards', label: 'Credit cards', icon: CreditCard },
  { to: '/recurring', label: 'Subscriptions & EMIs', icon: Repeat },
  { to: '/investments', label: 'Investments', icon: TrendingUp },
  { to: '/net-worth', label: 'Net worth', icon: Scale },
  { to: '/assets', label: 'Assets', icon: Building2 },
  { to: '/construction', label: 'Construction', icon: HardHat },
  { to: '/home', label: 'Home Inventory', icon: House },
  { to: '/insurance', label: 'Insurance', icon: Shield },
  { to: '/goals', label: 'Goals', icon: Target },
  { to: '/income', label: 'Income & tax', icon: IndianRupee },
  { to: '/reports', label: 'Reports', icon: FileText },
  { to: '/journal', label: 'Journal', icon: NotebookPen },
  { to: '/settings', label: 'Settings', icon: Settings },
]
```

Map in JSX:

```tsx
const Icon = item.icon
<NavLink ...>
  <span className="flex items-center gap-2">
    <Icon className="size-4 shrink-0 opacity-80" aria-hidden />
    {item.label}
  </span>
</NavLink>
```

- [ ] **Step 3: Build dashboard**

Run: `cd dashboard && npm run build`

Expected: TypeScript + Vite build succeed.

---

### Task 10: Manual QA + full verification

**Steps:**

- [ ] **Step 1: Manual checklist**

  - Start API + dashboard (`make dev` / `make dev-dashboard` per project docs).
  - Open `/journal`, pick today, type markdown, Save, refresh — text persists.
  - Clear body, Save — GET returns empty state in UI.
  - Sidebar: every link shows icon; Journal between Reports and Settings.

- [ ] **Step 2: Run full tests**

Run: `make test`

Expected: all tests pass.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-05-02-journal-nav-icons.md`.

**1. Subagent-driven (recommended)** — Fresh subagent per task; review between tasks.

**2. Inline execution** — Run through tasks in this chat with checkpoints.

Which approach do you want for implementation?
