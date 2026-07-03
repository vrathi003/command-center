# Credit Cards — User Guide

This guide covers everything on the **Credit Cards** section of Personal Finance OS, from adding your first card to understanding your spending patterns. Start here if you've never used this part of the dashboard before.

---

## Table of Contents

1. [Overview](#overview)
2. [Adding a Credit Card](#adding-a-credit-card)
3. [The Credit Cards List](#the-credit-cards-list)
4. [The Card Detail Page](#the-card-detail-page)
   - [KPI Strip (the numbers at the top)](#kpi-strip)
   - [Interest Leakage Warning](#interest-leakage-warning)
   - [Pay Bill](#pay-bill)
   - [Insights — Spend Trend & Rewards](#insights)
   - [Transactions](#transactions)
   - [EMI Plans](#emi-plans)
   - [Card Details (editing the card)](#card-details)
   - [Upload Statement](#upload-statement)
5. [Importing a Credit Card Statement](#importing-a-credit-card-statement)
6. [How the Live Balance Works](#how-the-live-balance-works)
7. [Gmail CC Alerts](#gmail-cc-alerts)
8. [Key Concepts Explained](#key-concepts-explained)

---

## Overview

The Credit Cards section lets you:

- Track every credit card you own in one place
- See your **live outstanding balance** (calculated from real transactions, not just the statement)
- Import statements (PDF, CSV, or Excel) to pull in all your spending
- Log bill payments so your balance stays accurate
- Track EMI (no-cost or otherwise) purchases on your card
- See how much interest you've paid and get a reward earnings estimate

Navigate to **Credit Cards** from the left sidebar.

---

## Adding a Credit Card

1. Go to **Credit Cards** in the sidebar.
2. Click **Add card** (top right of the page).
3. Fill in the details:

| Field | What to enter | Required? |
|-------|--------------|-----------|
| Card name | A nickname, e.g. "HDFC Regalia" | Yes |
| Issuer | Bank name, e.g. "HDFC" | No |
| Last four digits | Last 4 digits of your card number | No |
| Credit limit | Your card's total credit limit in ₹ | Yes |
| Statement day | Day of the month your statement is generated, e.g. 15 | No |
| Due date | Day of the month your bill is due, e.g. 5 (of the next month) | No |
| Minimum due % | Minimum payment as a % of outstanding (usually 5%) | No |
| Reward rate % | Cashback or reward points rate, e.g. 1.5 for 1.5% cashback | No |

4. Click **Save**.

> **What happens behind the scenes:** When you save a new card, the system automatically creates a linked **account** of type "Credit Card" in your Accounts list. This is what allows transactions to be associated with the card and enables the live balance calculation.

---

## The Credit Cards List

Each card on the list shows:

- **Live balance** — how much you currently owe (calculated from transaction history)
- **Credit limit** — your total limit
- **Utilization %** — live balance ÷ credit limit. High utilization (over 30%) affects credit scores
- **EMI info** — if you have active EMI plans, shows limit blocked and monthly EMI amount

Click any card name to open its detail page.

---

## The Card Detail Page

This is where you manage everything for a single card. It has several sections described below.

---

### KPI Strip

The row of number cards at the top of the detail page. Here's what each one means:

| KPI | What it shows |
|-----|--------------|
| **Live balance** | Current outstanding amount calculated from your actual transactions. More accurate than the statement balance because it includes spending since the last statement. |
| **Credit limit** | Your approved credit limit for this card. |
| **Utilization** | Live balance as a percentage of your credit limit. |
| **Statement day** | The day of the month your billing cycle ends and a statement is generated. |
| **Due date** | The day by which you must pay at least the minimum due to avoid late fees. |
| **Minimum due %** | The minimum payment percentage (typically 5%). Used to estimate minimum payment. |
| **Reward rate** | Your cashback or reward earn rate in %. Used for reward estimates in the Insights section. |
| **Interest paid (this FY)** | Total interest and finance charges paid on this card in the current financial year. |
| **Interest paid (all time)** | Total interest ever paid on this card across all imported transactions. |

> **Tip:** If a KPI shows "—" or "No linked account", it means transactions haven't been linked to this card yet. Import a statement or add spending via the Transactions page to see live data.

---

### Interest Leakage Warning

If you've paid any interest or finance charges on this card, a **red warning banner** appears below the KPI strip showing how much interest you've paid this financial year.

This is called "leakage" because it's money lost to interest that could have been avoided by paying the full bill each month.

**How it detects interest:** Any transaction on this card where the merchant/description contains words like "interest", "finance charge", "late fee", "overlimit fee", etc., is automatically flagged. These transactions are also automatically categorised as **Bank Charges** when you import a statement.

---

### Pay Bill

The **Pay Bill** button (top right of the card detail page) is how you record a credit card payment — i.e., when you transfer money from your bank account to pay off your credit card bill.

**Step by step:**

1. Click **Pay Bill**.
2. A panel slides open with these fields:
   - **Pay from account** — select the bank account you're paying from (e.g., HDFC Savings). Credit card accounts are excluded from this list.
   - **Amount (₹)** — the amount you're paying. Can be the full balance, minimum due, or any amount.
   - **Date** — the date you made/will make the payment.
   - **Notes** — optional, e.g. "Full payment for June cycle".
3. Click **Pay**.

**What happens:** A **transfer** transaction is created — a debit on your bank account and a credit on your credit card account. This reduces the live balance on your credit card.

> **Important:** This does not actually send any money to your bank. It's just a record in the dashboard so your balances stay accurate.

---

### Insights

The **Insights** section appears below the interest leakage warning (only visible if the card has a linked account with transactions).

**Monthly spend chart:** A bar chart showing your total spending on this card for each of the last 6 calendar months. Use this to spot months where you overspent or to understand your average monthly card usage.

**Reward optimisation:** If you've set a reward rate % on the card, this section shows an estimate of the total cashback/rewards you've earned based on your total transaction history. For example, if you've spent ₹2,00,000 in total and your card gives 1.5% cashback, the estimate shows ₹3,000.

> **To see reward estimates:** Go to **Card Details** (the edit section at the bottom of the page) and fill in the **Reward rate %** field.

---

### Transactions

Below the Insights section is a full list of all transactions on this card, grouped by **billing cycle**.

**Billing cycle grouping:** If you've set a Statement day (e.g., 15), transactions are grouped from the 15th of one month to the 14th of the next, matching your actual statement periods. If no statement day is set, they're grouped by calendar month.

Each billing cycle shows:
- Total spent (debits)
- Total credits (refunds, cashback)
- Interest/fees total (highlighted in red if any)
- Transaction count

Each transaction row shows:
- Date
- Merchant / description
- Amount with DR/CR badge
- Category
- **Interest/fee transactions** are highlighted in a distinct colour so they stand out

**How transactions get here:** Transactions appear here when they are linked to this card's account. This happens when you:
1. Import a statement (see [Importing a Statement](#importing-a-credit-card-statement))
2. Manually add a transaction and select this card's account
3. A Gmail bank alert is matched to this card (see [Gmail CC Alerts](#gmail-cc-alerts))

---

### EMI Plans

This section tracks **purchases converted to EMIs** on your credit card — for example, a ₹60,000 phone purchased on a 6-month no-cost EMI, or a personal loan linked to your card.

**Adding an EMI plan:**

1. Scroll to **EMI plans** on the card detail page.
2. Fill in the form:

| Field | What to enter |
|-------|--------------|
| Description | Name of the purchase, e.g. "iPhone 15 EMI" |
| Loan type | Optional type, e.g. "No-cost EMI", "Personal loan" |
| Limit blocked (₹) | How much of your credit limit this EMI is blocking |
| EMI/loan amount (₹) | The original purchase amount (principal) |
| Monthly EMI (₹) | How much you pay per month |
| No. of installments | Total tenure in months |
| Installments paid | How many you've already paid |
| Outstanding instalment (₹) | If shown on your statement, the outstanding EMI balance |
| Creation date | When the EMI was created |
| Finish date | When it ends |

3. Click **Add plan**.

**EMI details:** Click **Details** on any EMI plan to see a breakdown including total interest estimated, interest paid to date, and amount paid so far.

**Track in Debts:** If you want to include this EMI in your overall **Debt** tracking (for the Debt page and net worth calculations), click **Track in Debts**. This creates a matching entry on the Debt page with the outstanding balance pre-filled. After clicking, the button changes to **View in Debts →** — click it to navigate directly to the Debt page.

**Edit / Remove:** Use the **Edit** and **Remove** buttons to update or delete an EMI plan.

---

### Card Details

The **Card Details** section at the bottom of the page is the edit form for the card itself. Use this to:

- Change the card name or issuer
- Update the credit limit
- Set or update the **Statement day**, **Due date**, **Minimum due %**, and **Reward rate %**
- Deactivate the card (toggle "Active")

After making changes, click **Save**.

> **Tip:** Setting the Statement day and Due date unlocks the due date alerts — the system will send you a Discord DM the day before and on the day your bill is due.

---

### Upload Statement

Use this to import a credit card statement file directly. Supported formats:

- **PDF** — text is extracted automatically. Works best with digital PDFs (not scanned images).
- **CSV / Excel (.csv, .xlsx, .xls)** — must have columns for date, amount/debit/credit, and optionally merchant/description.

**Step by step:**

1. If your PDF statement is password-protected, enter the password in the **PDF password** field.
2. Click **Choose file** and select your statement file.
3. Click **Upload**.
4. The system parses the file and shows you a **preview** of the extracted transactions (the "Statement review" section).
5. Review the line items. You can see date, amount, description, category, and transaction type for each row.
6. When you're happy, click **Apply to transactions** to import them all into your transaction ledger.

**What the parser does automatically:**
- **Payment entries** (e.g., "Payment received - thank you") are **skipped** — they would double-count your payments.
- **Interest and fee entries** (e.g., "Finance charge", "Late payment fee") are categorised as **Bank Charges** and flagged as debits.
- **Cashback/reward credits** are categorised as **Income**.
- **Refunds** are imported as credits.
- All other entries are categorised based on the merchant name (e.g., Swiggy → Food Delivery, Amazon → Online Shopping).

---

## Importing a Credit Card Statement

End-to-end walkthrough for a first-time import:

1. Download your statement from your bank's net banking portal (PDF or CSV).
2. Go to your card's detail page (Credit Cards → click your card).
3. Scroll to **Upload statement**.
4. If PDF: enter the password if it's encrypted.
5. Choose the file and click **Upload**.
6. Wait a few seconds — you'll see a preview table appear below with all extracted transactions.
7. Check the table:
   - Dates look correct?
   - Amounts look right?
   - Payment entries are absent (they should be auto-skipped)?
8. Click **Apply to transactions**.
9. The transactions now appear in the **Transactions** section of this card and in the main **Transactions** page.

> **Tip:** You can upload the same statement again without duplicating — the system detects existing transactions by date + amount + merchant and prevents duplicates.

---

## How the Live Balance Works

The **live balance** shown at the top of each card detail page is **not** taken from a statement. It is calculated in real time from your transaction history:

```
Live balance = Total debits on this card − Total credits on this card
```

This means:
- Every import you do, every manual transaction on this card, and every bill payment you log all affect the live balance immediately.
- If the live balance looks wrong, it usually means some transactions are missing (import a more recent statement) or a bill payment hasn't been logged yet (use **Pay Bill**).

---

## Gmail CC Alerts

If you've configured Gmail integration (see `docs/SETUP_AND_OPERATIONS.md`), the system syncs bank alert emails automatically every 3 hours.

When a bank alert mentions a specific credit card (e.g., "Your HDFC card ending 4321 has been debited ₹1,500"), the system:
1. Detects the last 4 digits (4321 in this example)
2. Finds the matching card in your dashboard
3. Pre-fills the account when staging the transaction in the **Gmail Inbox** page

This means when you review and approve the email in the Gmail Inbox, the transaction is automatically linked to the correct credit card without you having to select it manually.

---

## Key Concepts Explained

**Billing cycle vs calendar month**
A billing cycle runs from your statement day to the day before the next statement. For example, if your statement day is the 15th, your cycle runs 15 Jan → 14 Feb. This is different from a calendar month (1 Jan → 31 Jan). The Transactions section groups by billing cycle when a statement day is set.

**Live balance vs statement balance**
Your statement balance is what the bank calculated at the end of your last billing cycle. The live balance in this dashboard includes all spending and payments since then, so it's more current. They won't match if you've spent on the card after your last statement date.

**Limit blocked by EMI**
When you take an EMI on a credit card, that principal amount is "blocked" from your available credit — you can't spend it even though it's not in your regular outstanding balance. The utilization calculation includes EMI-blocked amount alongside your live balance for a more accurate picture.

**Bank Charges category**
Any interest, finance charge, or fee on your credit card is automatically categorised as "Bank Charges" when imported. This makes it easy to filter and see exactly how much you're paying in charges across all cards on the main Transactions page.

**Transfer transactions**
When you pay your credit card bill using **Pay Bill**, it creates two transactions:
1. A debit from your bank account
2. A credit to your credit card account

These are linked as a "transfer pair" and are excluded from your spending totals and budget calculations — so your spend reports won't show your bill payment as an expense.
