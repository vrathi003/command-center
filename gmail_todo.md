# Gmail Transaction Inbox — Setup & TODO

## One-time Setup

### 1. Create a GCP project and enable the Gmail API
1. Go to https://console.cloud.google.com/
2. Create a new project (e.g. "Personal Finance OS")
3. Navigate to **APIs & Services → Library**
4. Search for "Gmail API" and click **Enable**

### 2. Create OAuth2 credentials
1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Name it anything (e.g. "Finance Local")
5. Download the JSON file — save it as `~/finance/gmail_credentials.json`

### 3. Configure OAuth consent screen
1. Go to **APIs & Services → OAuth consent screen**
2. User type: **External** (for personal use, this is fine)
3. Fill in app name and your email
4. Add scope: `https://www.googleapis.com/auth/gmail.readonly`
5. Add your Gmail address as a **Test user**

### 4. Run the setup script (one-time browser consent)
```bash
python scripts/setup_gmail.py --credentials ~/finance/gmail_credentials.json
```
This opens a browser tab, you grant consent, and a token file is saved to `~/finance/gmail_token.json`.

### 5. Set environment variables in `.env`
```env
GMAIL_CREDENTIALS_PATH=~/finance/gmail_credentials.json
GMAIL_TOKEN_PATH=~/finance/gmail_token.json
GMAIL_SYNC_LOOKBACK_HOURS=4
```

### 6. Install Python dependencies (if not already done)
```bash
uv sync
# or within the api package:
cd packages/api && uv pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### 7. Restart the API server
```bash
make dev
# or
python start.py
```
On startup, the scheduler registers a Gmail sync job that runs every 3 hours.

---

## Trigger a Manual Sync

- **From the dashboard:** Go to `/email-inbox` → click **Sync now**
- **Via API:** `POST http://localhost:8000/api/email-inbox/sync`

---

## How the Inbox Works

1. Gmail is polled every 3 hours for emails from known bank/merchant domains
2. Parsed transactions appear in the **Pending** tab at `/email-inbox`
3. Review each item — edit date, amount, category, merchant, payment mode if needed
4. Click **Approve** to create the transaction in the ledger (`source = "gmail"`)
5. Click **Reject** to dismiss — rejected items can be bulk-cleared

---

## Supported Email Sources

**Banks (transaction alerts):**
HDFC, ICICI, SBI, Axis, Kotak, IndusInd, IDFC First, Federal Bank, Yes Bank, PNB, Bank of Baroda, RBL

**Merchants (order/payment confirmations):**
Swiggy, Zomato, Amazon, Flipkart, Myntra, Paytm, PhonePe, MakeMyTrip, IRCTC, BigBasket, Blinkit, Zepto, Airtel

---

## TODO / Future Improvements

- [ ] **CC statement PDF from email** — detect emails from banks with PDF attachments matching statement filename patterns; auto-queue to `/transactions/import` PDF pipeline (deferred from initial scope)
- [ ] **Unsubscribe / ignore sender** — let user mark a sender domain as "never parse" so future emails from that domain are skipped at the sync stage
- [ ] **Account auto-suggestion** — match the bank/card in the email sender to an account in the DB automatically (currently left as `suggested_account_id = null`)
- [ ] **Duplicate detection with existing transactions** — before showing in pending, cross-check if a transaction with same date+amount+merchant already exists in the ledger (within ±1 day)
- [ ] **Bulk approve** — select multiple pending items and approve all at once
- [ ] **Push notification** — send Discord DM when N+ new items land in the inbox after a sync
- [ ] **Token refresh alerting** — if the Gmail token expires and cannot be auto-refreshed (refresh_token missing), send a Discord alert with instructions to re-run `setup_gmail.py`
- [ ] **Pagination** — inbox currently shows up to 200 items; add pagination for large inboxes
