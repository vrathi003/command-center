# Design: Journal (daily markdown) + sidebar icons

**Status:** Approved (brainstorming session, 2026-05-02).  
**Scope:** Dashboard navigation icons for all items; new Journal section with server-backed daily entries.

---

## 1. Goals

- Every primary sidebar link shows a **consistent icon + label** (existing `AppShell` `NAV` list).
- Users can open **Journal** (`/journal`), pick a **calendar day**, write **markdown**, preview rendered output, and **save** so data persists in the same SQLite database as the rest of Personal Finance OS.
- **One row per calendar date** (`YYYY-MM-DD`). Saving replaces that day’s content; clearing all content **deletes** the row.
- **No** `audit_log` rows for journal CRUD (privacy / noise).

---

## 2. Non-goals (v1)

- Autosave, version history, encryption-at-rest beyond the existing DB file, Discord/bot integration, multi-user permissions, attachments/images in entries, full-text search, export-only journal.
- Rich WYSIWYG editor (markdown source + preview only).

---

## 3. Data model

**Table:** `journal_entries`

| Column       | Type | Constraints |
|-------------|------|-------------|
| `entry_date` | TEXT | `PRIMARY KEY NOT NULL` — ISO `YYYY-MM-DD` (same convention as `transactions.date`). |
| `body`       | TEXT | `NOT NULL` — markdown source. |
| `created_at` | TEXT | `NOT NULL DEFAULT (datetime('now'))` |
| `updated_at` | TEXT | `NOT NULL DEFAULT (datetime('now'))` — updated on upsert. |

**Indexes:** Primary key sufficient for `GET` by date and listing by range on `entry_date`. No extra index unless profiling shows need.

**Bootstrap:** Add `CREATE TABLE IF NOT EXISTS` to `packages/common/src/finance_common/db/schema.sql`. Add a **`journal_entries` absent** branch in `packages/common/src/finance_common/db/migrations.py` (same `sqlite_master` check + `executescript` pattern as `subscriptions`, `home_items`, etc.) so existing databases gain the table without a manual reset.

---

## 4. API

**Router:** New FastAPI module, e.g. `packages/api/src/finance_api/routers/journal.py`, registered in `main.py` with `prefix="/api"` and router prefix **`/journal`**, tag `journal`.

**Endpoints:**

| Method | Path | Behavior |
|--------|------|------------|
| `GET` | `/journal/{entry_date}` | Return JSON `{ entry_date, body, created_at, updated_at }` if row exists; **`404`** if none. |
| `PUT` | `/journal/{entry_date}` | Body JSON: `{ "body": "<markdown string>" }`. Trim surrounding whitespace. If trimmed body is **empty**, **delete** row if present, return **`204 No Content`**; if no row, **`204`** (idempotent). If non-empty, **upsert** and return **`200`** with full record. |
| `GET` | `/journal` | List entries in an optional **`from` / `to`** inclusive date range (ISO). If omitted, default range documented in OpenAPI (e.g. last 90 days **with rows only**) to cap payload size. |

**Validation:**

- `entry_date` must be valid calendar `YYYY-MM-DD`; invalid → **`422 Unprocessable Entity`**.
- `from` / `to` invalid or `from > to` → **`422`**.

**Errors:** SQLite / unexpected failures → **`500`** with generic message; align with sibling routers.

**Audit:** Do **not** call shared audit logging for journal operations.

---

## 5. Common layer

- **Repository** under `packages/common/src/finance_common/repositories/` (e.g. `journal.py`): `get_by_date`, `upsert`, `delete_by_date`, `list_range` using `aiosqlite` patterns used by peers.
- Optional small **types** if useful for return DTOs; keep Pydantic models primarily in the API package unless shared is already the norm for similar resources.

---

## 6. Dashboard UI

**Routing:** `App.tsx` — new route `path="journal"` under `AppShell`, element `JournalPage`.

**Navigation:** `AppShell.tsx`:

- Add dependency **`lucide-react`** (tree-shakeable icons; stable with Vite + React 19).
- Extend each nav entry with a **`LucideIcon`** reference; render **icon + label** with fixed size (~16–18px) and `gap-2`, preserving current active/hover styles.
- New item: **label** `Journal`, route **`/journal`**, icon e.g. **`NotebookPen`** or **`BookMarked`** (pick one at implementation). **Placement:** after **Reports**, before **Settings**.

**Journal page layout (recommended):**

- **Month calendar** (or equivalent) to pick `entry_date`; highlight days that have entries (requires list endpoint for visible month range).
- **Editor:** `<textarea>` for markdown (monospace-friendly classes).
- **Preview:** **`react-markdown`** + **`rehype-sanitize`**; optionally **`remark-gfm`** for GFM tables/task lists if dependency budget allows. No trusted raw HTML from user markdown.
- **Save:** explicit primary **Save** button; no autosave in v1.
- **Empty state:** `GET` returns 404 → editor starts empty; first save creates row.
- **Dirty state:** optional simple “unsaved changes” warning before navigation — **nice-to-have** in implementation plan if time allows; not blocking for v1.

**Data fetching:** TanStack `useQuery` / `useMutation` consistent with other pages; base URL from existing API config pattern.

---

## 7. Testing

- **pytest (API):** GET 404 missing; PUT create; PUT update; PUT empty deletes; PUT empty idempotent on missing; invalid date `422`; list range filters correctly.
- **Dashboard:** Manual checklist or add frontend tests only if the repo already has a harness for React (otherwise document manual QA in implementation plan).

---

## 8. Implementation strategy

**Vertical slice:** schema + migration + repository + router + `main.py` registration + dashboard route + `JournalPage` + `AppShell` icons and journal link in **one cohesive delivery**, with tests for the API slice first or in parallel.

---

## 9. Open decisions deferred to implementation plan

- Exact default window for `GET /journal` when `from`/`to` omitted (e.g. 90 days vs current month).
- Calendar widget: minimal custom grid vs small dependency — choose for maintainability.
- Icon-to-route mapping table (single source in `AppShell`).

---

## 10. Acceptance criteria

- All existing nav labels remain with an icon; new **Journal** appears between Reports and Settings.
- `/journal` loads; selecting a date loads saved markdown or empty; Save persists; clearing all text and Save removes row; reload shows empty for that date.
- Markdown renders safely in preview (sanitized).
- `make test` (or project test command) passes including new API tests.
