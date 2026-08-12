# Set up from scratch

End-to-end path: empty machine → running Personal Finance OS (local or Ubuntu
services) → optional Discord, Gmail, LLM, and remote access.

For day-to-day money flows after install, see {doc}`workflows/index` and
{doc}`dashboard/index`. For env var / job detail, see ``docs/SETUP_AND_OPERATIONS.md``.

---

## 0. What you will end up with

| Piece | Default |
|-------|---------|
| API | ``http://127.0.0.1:8000`` (Swagger at ``/docs``) |
| Dashboard | ``http://127.0.0.1:3000`` (dev) or ``4173`` (production build + Tailscale) |
| Database | SQLite at ``DB_PATH`` (e.g. ``~/finance/finance.db``) |
| Bot (optional) | Discord expense entry |
| Jobs | APScheduler inside the **API** process (prices, backups, alerts, digests) |

New installs default to **``ledger_engine=double_entry``**. Schema migrations run on API startup.

---

## 1. Prerequisites

Install on the host that will run the stack:

1. **Python 3.14+** and **[uv](https://docs.astral.sh/uv/)**:

   ```bash
   curl -Lsf https://astral.sh/uv/install.sh | sh
   # ensure ~/.local/bin is on PATH
   ```

2. **Node.js 20+** and **npm** (nvm is fine on Ubuntu).

3. **Git**, and a clone of this repo:

   ```bash
   git clone <your-fork-or-remote-url> Personal-Finance-OS
   cd Personal-Finance-OS
   ```

4. Optional later:

   - Discord application (bot token + Message Content Intent)
   - Google Cloud OAuth client (Gmail sync)
   - Ollama or LM Studio (PDF LLM fallback)
   - Tailscale (remote HTTPS without opening the firewall)

---

## 2. Install dependencies

```bash
make install
# equivalent: uv sync  &&  npm install --prefix dashboard
```

One-click helper (uv sync + copy ``.env.example`` → ``.env`` if missing):

```bash
uv run python setup.py
# or: uv run python scripts/setup.py
```

---

## 3. Configure ``.env``

```bash
cp .env.example .env   # skip if setup.py already created it
mkdir -p ~/finance ~/finance/backups
```

Edit **``.env``** at the repo root. **Do not commit secrets.** Use placeholders, not real tokens, in any shared notes.

### Minimum (local dashboard + API)

```bash
DB_PATH=~/finance/finance.db
API_HOST=127.0.0.1
API_PORT=8000
DASHBOARD_PORT=3000
APP_ENV=development
LOG_LEVEL=INFO
# Leave empty for local unauthenticated access:
# APP_SECRET_KEY=
```

### Recommended for anything beyond pure localhost

```bash
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
APP_SECRET_KEY=replace_me
APP_ENV=production
BACKUP_DIR=~/finance/backups
JOBS_ENABLED=true
SCHEDULER_TIMEZONE=Asia/Kolkata
```

Dashboard auth uses ``APP_SECRET_KEY`` as a static API key when set. Leave it empty only for trusted local-only use.

### Discord (optional)

1. Create an application at the [Discord Developer Portal](https://discord.com/developers/applications).
2. Bot → enable **Message Content Intent**.
3. Invite the bot to a server you use (or DM-capable setup for DMs).
4. Set:

```bash
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_USER_ID=your_numeric_user_id
# Optional — faster slash sync while testing:
# DISCORD_DEV_GUILD_ID=
```

API scheduled DMs (budget / EMI) also need these when Discord is enabled.

### Local LLM for PDF bank statements (optional)

Heuristic PDF parsing always runs first. LLM is a fallback:

```bash
LOCAL_LLM_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=qwen2.5:1.5b
LOCAL_LLM_TIMEOUT_SECONDS=600
```

Example with Ollama: ``ollama pull qwen2.5:1.5b``. Details: ``docs/BANK_STATEMENT_PARSING.md``.

### Gmail sync (optional)

1. Create a Google Cloud OAuth **Desktop** client; download JSON to e.g. ``~/finance/gmail_credentials.json``.
2. Run consent once:

   ```bash
   # Machine with a browser:
   uv run python scripts/setup_gmail.py --credentials ~/finance/gmail_credentials.json

   # Headless server: SSH tunnel then --console (see script docstring)
   ```

3. Set:

```bash
GMAIL_CREDENTIALS_PATH=~/finance/gmail_credentials.json
GMAIL_TOKEN_PATH=~/finance/gmail_token.json
# GMAIL_SYNC_LOOKBACK_HOURS=4
```

---

## 4. First run (development)

Terminal A — API + bot:

```bash
make dev
# or: uv run python start.py
```

Terminal B — React:

```bash
make dev-dashboard
```

Checks:

```bash
curl -fsS http://127.0.0.1:8000/health
# open http://127.0.0.1:3000
# API docs: http://127.0.0.1:8000/docs
```

Optional demo data (wipes selected demo tables — read the script before ``--force``):

```bash
make seed-demo
```

---

## 5. First-hour product checklist

Do this once the dashboard loads (skip seed if you want a clean books start):

1. **Settings** — confirm financial year; keep **ledger engine** on ``double_entry``.
2. **Accounts** — add banks / wallets you use.
3. **Credit cards** — add cards (creates ``liability_cc`` accounts); check the portfolio KPI strip.
4. **Debt** — add loans if needed; set payment account for EMI posting.
5. **Budget** — set category caps for the current FY.
6. **Transactions** — import a small statement or add a manual debit/credit.
7. **Goals / Assets / Investments** — optional; wealth seeds create investment ledger accounts on first bind.

If you already had **legacy** ``transactions`` history from an older install:

```text
POST /api/migration/legacy-ledger/dry-run
POST /api/migration/legacy-ledger/apply
```

Prefer Settings UI if exposed; apply takes a DB backup first. Fresh installs usually **skip** this.

Excel history (optional):

```bash
make migrate-dry
make migrate    # uses Makefile XLSX / DB defaults — edit paths as needed
```

---

## 6. Production on Ubuntu (systemd)

Assumes the repo lives on the server (e.g. ``~/Documents/WorkSpace/.../Personal-Finance-OS``), ``.env`` is filled, and ``make install`` already succeeded for that user.

```bash
# From repo root, as a user with sudo:
sudo make install-services
# → scripts/install_systemd_services.sh
```

That installs and enables:

- ``finance-api.service`` — uvicorn on ``127.0.0.1:8000``
- ``finance-dashboard.service`` — Vite production preview / built UI (see unit file)
- ``finance-bot.service`` — Discord bot

Useful commands:

```bash
make service-status
# or:
sudo systemctl status finance-api.service finance-dashboard.service finance-bot.service
sudo journalctl -u finance-api.service -n 80 --no-pager

# After git pull:
cd /path/to/repo
git pull
make install
sudo systemctl restart finance-api.service finance-dashboard.service finance-bot.service
```

API migrations apply on API process start — **restart API after pull** when schema changes land.

### macOS / Windows alternatives

| Platform | Helper |
|----------|--------|
| macOS | ``scripts/launchd/com.personalfinance.api.plist`` (edit paths) |
| Windows | ``scripts/windows/register-api-task.ps1`` (edit paths) |

---

## 7. Remote access (Tailscale)

Keep services bound to localhost; expose via Tailscale Serve:

```bash
make configure-tailscale
# → scripts/configure_tailscale_serve.sh
```

Requires Tailscale installed and ``sudo tailscale up``. The script serves HTTPS to the dashboard port and ``/api`` to the API. Open the printed ``https://…`` MagicDNS URL from any device on your tailnet.

Alternative tunnels: ``uv run python scripts/expose.py --help`` (ngrok / Tailscale helpers).

---

## 8. Verify a healthy stack

```bash
make health
# or:
curl -fsS http://127.0.0.1:8000/health
```

Expect:

- API returns healthy JSON
- Dashboard loads; authenticated calls work if ``APP_SECRET_KEY`` is set
- Settings show ``double_entry``
- Creating a credit card or investment does not error; transactions list loads (including wealth-seed rows)

If transactions 500 after wealth seeds, ensure you are on a build that maps non-cash ledger legs in the transactions façade (see {doc}`getting-started`).

---

## 9. Backups and jobs

With ``BACKUP_DIR`` set and the API running, a daily **02:00** job copies ``DB_PATH`` (timezone ``SCHEDULER_TIMEZONE``). Also keep occasional offline copies of ``~/finance/``.

Job schedule summary: ``docs/SETUP_AND_OPERATIONS.md``.

---

## 10. Docs site (optional)

```bash
uv sync --group docs
make docs          # writes docs/site/
make docs-serve    # http://127.0.0.1:8000 — stop API first or use another port
```

Start at ``docs/site/index.html`` or this page after rebuild.

---

## Quick reference

| Goal | Command / place |
|------|-----------------|
| Install deps | ``make install`` |
| Dev API + bot | ``make dev`` |
| Dev UI | ``make dev-dashboard`` |
| Seed demo | ``make seed-demo`` |
| Systemd | ``sudo make install-services`` |
| Tailscale | ``make configure-tailscale`` |
| Health | ``make health`` |
| Gmail OAuth | ``uv run python scripts/setup_gmail.py …`` |
| Product guide | {doc}`index` |

---

## Security checklist

- [ ] ``.env`` is gitignored and never committed
- [ ] ``APP_SECRET_KEY`` set when the dashboard is reachable beyond loopback
- [ ] API/dashboard bind to ``127.0.0.1``; use Tailscale/VPN instead of public bind
- [ ] Discord token and Gmail OAuth JSON stay under ``~/finance/`` with tight permissions
- [ ] ``BACKUP_DIR`` set before you rely on the stack for real money data
