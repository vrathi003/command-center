# Gmail Transaction Inbox — Setup Guide

## How parsing works

**100% local, no LLM.** The parser (`packages/common/src/finance_common/parsing/gmail_email.py`) uses:
- Regex to extract amounts (`₹`, `Rs.`, `INR` patterns)
- Keyword matching to detect debit vs credit (`debited`, `credited`, `payment successful`, etc.)
- UPI narration patterns to extract merchant name
- The same 54-rule merchant→category table used for CSV bank statement imports

Zero data leaves your machine during parsing.

---

## What you need

| File | What it is | How you get it |
|------|-----------|----------------|
| `gmail_credentials.json` | Your app's identity on Google Cloud (public) | Download from Google Cloud Console (you already have this ✓) |
| `gmail_token.json` | Your personal Gmail authorization token | **Generated automatically** when you run `scripts/setup_gmail.py` |

`setup_gmail.py` opens a browser, you click Allow, and it saves the token to `~/finance/gmail_token.json`. You only do this once. After that, the token auto-refreshes silently.

---

## Step-by-step Google Cloud setup (current UI — July 2026)

> Google recently renamed sections. It's now **"Google Auth Platform"** instead of "APIs & Services → OAuth consent screen".

### Step 1 — Create a project (skip if done)
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Top bar → click the project dropdown → **New Project**
3. Name it (e.g. "Personal Finance") → **Create**

### Step 2 — Enable Gmail API
1. In your project, go to **APIs & Services → Library**
2. Search **"Gmail API"** → click it → **Enable**

### Step 3 — Configure OAuth consent screen (Google Auth Platform)
1. Left menu → **Google Auth Platform** → **Branding**
   - If you see "Google Auth Platform not configured yet" → click **Get Started**
2. Fill in:
   - **App name**: anything (e.g. "Personal Finance OS")
   - **User support email**: your Gmail address
   - **Developer contact email**: your Gmail address
3. **Audience**: Select **External**
   - (Internal is only for Google Workspace orgs — not for personal Gmail accounts)
4. Click through and **Save**

### Step 4 — Add yourself as a test user (fixes "OAuth access is restricted" error)
1. Left menu → **Google Auth Platform** → **Audience**
2. Scroll to **Test users** section → click **Add Users**
3. Add **your own Gmail address** (the account you'll use to authorize)
4. Click **Save**

> This is why you saw "OAuth access is restricted to test users" — your app is in Testing mode, which limits it to up to 100 listed test users. Adding yourself fixes it. You do **not** need to publish the app or go through verification for personal use.

### Step 5 — Add Gmail scope
1. Left menu → **Google Auth Platform** → **Data Access**
2. Click **Add or Remove Scopes**
3. Search for `gmail.readonly` → check the box → **Update**
4. **Save and continue**

### Step 6 — Create credentials
1. Left menu → **Google Auth Platform** → **Clients**
   (Or: **APIs & Services → Credentials → Create Credentials → OAuth Client ID**)
2. Click **Create Client**
3. Application type: **Desktop app**
4. Name: anything → **Create**
5. Click **Download JSON** → save as `~/finance/gmail_credentials.json`

> This is the file you already have ✓

---

## Step 7 — Run the setup script (generates gmail_token.json)

### If you run the API on the same machine as your browser (most common)
```bash
python scripts/setup_gmail.py --credentials ~/finance/gmail_credentials.json
```
A browser tab opens. Sign in with the Gmail you added as a test user in Step 4. Click **Allow**. The script saves `~/finance/gmail_token.json` and prints the env vars to set.

### If you run the API on a remote/headless machine (Tailscale server, no browser)
Use the `--console` flag — it gives you a URL to open on any browser, then paste back the code:
```bash
python scripts/setup_gmail.py --credentials ~/finance/gmail_credentials.json --console
```
1. Copy the URL it prints
2. Open it in any browser (on your laptop, phone, anything)
3. Sign in and click Allow
4. Copy the authorization code shown in the browser
5. Paste it back into the terminal prompt

The token is saved on the server where the API runs. You only do this once.

---

## Step 8 — Set env vars

Add to your `.env`:
```env
GMAIL_CREDENTIALS_PATH=~/finance/gmail_credentials.json
GMAIL_TOKEN_PATH=~/finance/gmail_token.json
GMAIL_SYNC_LOOKBACK_HOURS=4
```

---

## Step 9 — Restart and verify

```bash
# Restart the API
make dev
# OR
python start.py
```

You should see in the logs:
```
Registered background jobs (timezone=Asia/Kolkata, ... gmail=enabled)
```

Then open `http://localhost:3000/email-inbox` (or your Tailscale URL) and click **Sync now**.

---

## Tailscale note

The API server and token file live on whatever machine runs `start.py` / `make dev`. Your dashboard can be accessed from any device via Tailscale — that's fine. But the OAuth setup (`setup_gmail.py`) must run **on the same machine as the API server** so the token file is saved in the right place.

- **API server has a browser** (e.g. your main Mac/PC): use normal mode (Step 7, first option)
- **API server is headless** (e.g. a home server, Raspberry Pi, remote box via SSH over Tailscale): use `--console` mode (Step 7, second option)

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| "OAuth access is restricted to the test users listed on your OAuth consent screen" | Add your Gmail to test users in Google Auth Platform → Audience (Step 4) |
| "redirect_uri_mismatch" | You're using the wrong credential type — re-create with **Desktop app** not Web |
| "invalid_client" | Credentials file is corrupted or wrong project — re-download |
| Token expires / "invalid_grant" | Delete `~/finance/gmail_token.json` and re-run `setup_gmail.py` |
| Script opens browser but nothing happens | Try `--console` flag |
| Sync returns 0 items | Gmail query may not match your bank's sender domain — check `_GMAIL_QUERY` in `gmail_sync.py` and add your bank's domain if missing |

---

## TODO / Future Improvements

- [ ] **CC statement PDF from email** — detect emails from banks with PDF attachments, auto-queue to `/transactions/import` PDF pipeline
- [ ] **Unsubscribe / ignore sender** — let user mark a sender domain as "never parse"
- [ ] **Account auto-suggestion** — match bank sender to an account in the DB
- [ ] **Duplicate check against ledger** — before staging, cross-check same date+amount+merchant already in transactions (within ±1 day)
- [ ] **Bulk approve** — select multiple pending items and approve all at once
- [ ] **Discord DM on new items** — send notification when N+ items land after a sync
- [ ] **Token expiry alert** — if refresh fails, send Discord DM with re-auth instructions
- [ ] **Add missing bank domains** — check your bank's alert sender against `_GMAIL_QUERY` in `gmail_sync.py`
