-- Personal Finance OS — SQLite schema (spec v1.0)
-- Amounts: INTEGER paise (rupee × 100). Dates: ISO TEXT YYYY-MM-DD.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    institution TEXT,
    currency TEXT NOT NULL DEFAULT 'INR',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    category TEXT NOT NULL,
    merchant TEXT,
    payment_mode TEXT NOT NULL,
    account TEXT,
    notes TEXT,
    transaction_type TEXT NOT NULL DEFAULT 'debit',
    source TEXT NOT NULL DEFAULT 'discord',
    discord_message_id TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    account_id INTEGER REFERENCES accounts(id),
    transfer_pair_id TEXT,
    tags TEXT
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_transactions_deleted ON transactions(is_deleted);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    monthly_amount_paise INTEGER NOT NULL,
    fy_year TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (category, fy_year, effective_from)
);

CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    lender TEXT,
    type TEXT NOT NULL,
    original_amount_paise INTEGER,
    current_balance_paise INTEGER NOT NULL,
    emi_paise INTEGER,
    rate_percent REAL,
    start_date TEXT,
    next_emi_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS investments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument TEXT NOT NULL,
    type TEXT NOT NULL,
    isin_code TEXT,
    units REAL,
    avg_price_paise INTEGER,
    current_price_paise INTEGER,
    last_synced TEXT,
    sector TEXT,
    equity_tax_class TEXT DEFAULT 'unspecified',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fixed_income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution TEXT NOT NULL,
    type TEXT NOT NULL,
    principal_paise INTEGER NOT NULL,
    rate_percent REAL,
    start_date TEXT,
    maturity_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    target_amount_paise INTEGER NOT NULL,
    current_amount_paise INTEGER NOT NULL DEFAULT 0,
    monthly_contribution_paise INTEGER,
    target_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS net_worth_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL UNIQUE,
    total_assets_paise INTEGER NOT NULL,
    total_liabilities_paise INTEGER NOT NULL,
    net_worth_paise INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS income_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    amount_paise INTEGER,
    frequency TEXT NOT NULL,
    taxability TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS merchant_category_map (
    merchant_keyword TEXT PRIMARY KEY NOT NULL,
    category TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    last_used TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    old_values TEXT,
    new_values TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    provider TEXT,
    category TEXT,
    amount_paise INTEGER NOT NULL,
    billing_cycle TEXT NOT NULL DEFAULT 'monthly',
    next_billing_date TEXT,
    notes TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_active ON subscriptions(is_active);

CREATE TABLE IF NOT EXISTS credit_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    issuer TEXT,
    last_four TEXT,
    credit_limit_paise INTEGER NOT NULL,
    current_balance_paise INTEGER,
    notes TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    account_id INTEGER REFERENCES accounts(id),
    statement_day INTEGER,
    due_day INTEGER,
    minimum_due_pct REAL DEFAULT 5.0,
    reward_rate_pct REAL,
    auto_fetch_enabled INTEGER NOT NULL DEFAULT 0,
    statement_pdf_password TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS credit_card_statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_card_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    extraction_preview TEXT,
    summary_json TEXT,
    line_items_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending_review',
    source TEXT NOT NULL DEFAULT 'upload',
    gmail_message_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (credit_card_id) REFERENCES credit_cards(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cc_statements_card ON credit_card_statements(credit_card_id);
-- idx_cc_statements_gmail_message is created in migrations.py, not here: on an existing DB
-- (this CREATE TABLE IF NOT EXISTS is a no-op) the gmail_message_id column doesn't exist yet
-- until apply_migrations()'s ALTER TABLE runs, and this schema.sql executescript runs first.

CREATE TABLE IF NOT EXISTS credit_card_emis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_card_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    limit_blocked_paise INTEGER NOT NULL,
    emi_amount_paise INTEGER NOT NULL,
    tenure_months INTEGER NOT NULL,
    installments_paid INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    loan_type TEXT,
    creation_date TEXT,
    finish_date TEXT,
    principal_paise INTEGER,
    outstanding_instalment_paise INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (credit_card_id) REFERENCES credit_cards(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cc_emis_card ON credit_card_emis(credit_card_id);

-- ── Assets module ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,                        -- apartment, plot, commercial, vehicle, gold, other
    status TEXT NOT NULL DEFAULT 'active',     -- active, sold
    purchase_date TEXT,
    purchase_price_paise INTEGER,
    current_value_paise INTEGER,
    ownership_percent REAL NOT NULL DEFAULT 100.0,
    co_owner TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);
CREATE INDEX IF NOT EXISTS idx_assets_deleted ON assets(is_deleted);

CREATE TABLE IF NOT EXISTS asset_real_estate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL UNIQUE,
    address TEXT,
    city TEXT,
    state TEXT,
    pin_code TEXT,
    builder TEXT,
    project_name TEXT,
    unit_details TEXT,
    carpet_area_sqft REAL,
    builtin_area_sqft REAL,
    super_builtin_area_sqft REAL,
    purchase_psf_paise INTEGER,
    current_psf_paise INTEGER,
    psf_area_type TEXT NOT NULL DEFAULT 'super_builtin',
    possession_status TEXT NOT NULL DEFAULT 'under_construction',
    possession_date_estimated TEXT,            -- YYYY-MM (month + year)
    possession_date_actual TEXT,
    agreement_value_paise INTEGER,
    circle_rate_psf_paise INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL UNIQUE,
    make TEXT,
    model TEXT,
    variant TEXT,
    year INTEGER,
    registration_number TEXT,
    fuel_type TEXT,
    color TEXT,
    depreciation_rate_percent REAL NOT NULL DEFAULT 15.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    cost_type TEXT NOT NULL,                   -- base_price, stamp_duty, registration, gst, legal_fees, brokerage, parking, plc, ifms, club_membership, maintenance_deposit, improvement, other
    description TEXT,
    amount_paise INTEGER NOT NULL,
    date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_asset_costs_asset ON asset_costs(asset_id);

CREATE TABLE IF NOT EXISTS asset_loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    debt_id INTEGER NOT NULL,
    sanctioned_amount_paise INTEGER,
    disbursed_amount_paise INTEGER,
    pre_emi_paise INTEGER,
    final_emi_paise INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(asset_id, debt_id),
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY (debt_id) REFERENCES debts(id)
);

CREATE INDEX IF NOT EXISTS idx_asset_loans_asset ON asset_loans(asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_loans_debt ON asset_loans(debt_id);

CREATE TABLE IF NOT EXISTS asset_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    payment_date TEXT NOT NULL,                  -- legacy sort key; use COALESCE(paid_date, due_date) in app
    amount_paise INTEGER NOT NULL,               -- total = amount_cash_paise + amount_loan_paise
    amount_cash_paise INTEGER NOT NULL DEFAULT 0,
    amount_loan_paise INTEGER NOT NULL DEFAULT 0,
    milestone TEXT,                            -- booking, agreement, slab_1..4, possession, registration, other
    payment_mode TEXT,
    reference_number TEXT,
    receipt_number TEXT,
    receipt_date TEXT,
    notes TEXT,
    is_paid INTEGER NOT NULL DEFAULT 0,
    due_date TEXT,
    paid_date TEXT,
    fund_source TEXT NOT NULL DEFAULT 'cash',  -- cash | bank_loan
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_asset_payments_asset ON asset_payments(asset_id);

-- ── Insurance module ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS insurance_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,                        -- health, life, term, vehicle, home, travel, other
    provider TEXT,
    policy_number TEXT,
    sum_insured_paise INTEGER,
    premium_paise INTEGER NOT NULL,
    premium_frequency TEXT NOT NULL DEFAULT 'annual',
    start_date TEXT,
    end_date TEXT,
    renewal_date TEXT,
    policyholder TEXT NOT NULL DEFAULT 'Self',
    covered_members TEXT,
    asset_id INTEGER,                          -- nullable; links vehicle/home insurance to an asset
    tax_deduction_section TEXT,                -- 80C, 80D, 80D_parents, null
    status TEXT NOT NULL DEFAULT 'active',     -- active, lapsed, surrendered, matured
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE INDEX IF NOT EXISTS idx_insurance_status ON insurance_policies(status);
CREATE INDEX IF NOT EXISTS idx_insurance_deleted ON insurance_policies(is_deleted);

CREATE TABLE IF NOT EXISTS insurance_premiums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id INTEGER NOT NULL,
    payment_date TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    period_start TEXT,
    period_end TEXT,
    payment_mode TEXT,
    reference_number TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (policy_id) REFERENCES insurance_policies(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_insurance_premiums_policy ON insurance_premiums(policy_id);

-- ── Home inventory (appliances, furniture, etc.) ───────────────────────────────

CREATE TABLE IF NOT EXISTS home_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    brand TEXT,
    model TEXT,
    serial_number TEXT,
    room_location TEXT,
    purchase_date TEXT,
    purchase_price_paise INTEGER,
    retailer TEXT,
    warranty_end_date TEXT,
    extended_warranty INTEGER NOT NULL DEFAULT 0,
    condition_status TEXT NOT NULL DEFAULT 'good',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_home_items_category ON home_items(category);
CREATE INDEX IF NOT EXISTS idx_home_items_deleted ON home_items(is_deleted);
CREATE INDEX IF NOT EXISTS idx_home_items_warranty ON home_items(warranty_end_date);

CREATE TABLE IF NOT EXISTS home_item_service_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    home_item_id INTEGER NOT NULL,
    service_date TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'other',
    vendor TEXT,
    description TEXT,
    cost_paise INTEGER,
    next_service_due TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (home_item_id) REFERENCES home_items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_home_service_item ON home_item_service_events(home_item_id);
CREATE INDEX IF NOT EXISTS idx_home_service_date ON home_item_service_events(service_date);

CREATE TABLE IF NOT EXISTS transaction_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    amount INTEGER,
    merchant TEXT,
    category TEXT,
    account_id INTEGER REFERENCES accounts(id),
    payment_mode TEXT,
    transaction_type TEXT NOT NULL DEFAULT 'debit',
    notes TEXT,
    tags TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_deleted INTEGER NOT NULL DEFAULT 0
);

-- ── Merchant rules (user-editable merchant identity + category classification) ──

CREATE TABLE IF NOT EXISTS merchant_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_type TEXT NOT NULL DEFAULT 'contains',
    match_value TEXT NOT NULL,
    canonical_merchant TEXT NOT NULL,
    merchant_type TEXT,
    category TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    confidence REAL NOT NULL DEFAULT 1.0,
    priority INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_matched_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_merchant_rules_match
    ON merchant_rules(match_type, match_value) WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_merchant_rules_category ON merchant_rules(category);
CREATE INDEX IF NOT EXISTS idx_merchant_rules_source ON merchant_rules(source);

-- ── Construction progress (builder monthly updates) ─────────────────────────────

CREATE TABLE IF NOT EXISTS construction_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS construction_zone_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES construction_projects(id) ON DELETE CASCADE,
    zone_key TEXT NOT NULL,
    label TEXT NOT NULL,
    UNIQUE (project_id, zone_key)
);

CREATE INDEX IF NOT EXISTS idx_construction_zone_labels_project ON construction_zone_labels(project_id);

CREATE TABLE IF NOT EXISTS construction_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES construction_projects(id) ON DELETE CASCADE,
    as_of_date TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    file_sha256 TEXT,
    parse_warnings_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_construction_snapshots_project_date ON construction_snapshots(project_id, as_of_date DESC);

CREATE TABLE IF NOT EXISTS construction_progress_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES construction_snapshots(id) ON DELETE CASCADE,
    zone_key TEXT NOT NULL,
    zone_type TEXT NOT NULL DEFAULT 'tower',
    tower_number INTEGER,
    tabular_index INTEGER,
    section TEXT NOT NULL,
    activity_raw TEXT NOT NULL,
    activity_normalized_key TEXT,
    floors_complete INTEGER,
    pct_complete INTEGER,
    status TEXT,
    remark TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_construction_rows_snapshot ON construction_progress_rows(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_construction_rows_zone ON construction_progress_rows(snapshot_id, zone_key);

CREATE TABLE IF NOT EXISTS journal_entries (
    entry_date TEXT PRIMARY KEY NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS email_transaction_staging (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_message_id TEXT NOT NULL UNIQUE,
    email_date TEXT NOT NULL,
    email_subject TEXT,
    email_from TEXT,
    raw_snippet TEXT,
    parsed_date TEXT,
    parsed_amount_paise INTEGER,
    parsed_merchant TEXT,
    parsed_category TEXT,
    parsed_payment_mode TEXT,
    parsed_transaction_type TEXT,
    suggested_account_id INTEGER REFERENCES accounts(id),
    status TEXT NOT NULL DEFAULT 'pending',
    created_transaction_id INTEGER REFERENCES transactions(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_email_staging_status ON email_transaction_staging(status);
CREATE INDEX IF NOT EXISTS idx_email_staging_gmail_id ON email_transaction_staging(gmail_message_id);

-- ── Statement import (CardQL-style Gmail fetch + preview) ─────────────────────

CREATE TABLE IF NOT EXISTS statement_import_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank TEXT NOT NULL,
    card TEXT NOT NULL,
    from_emails_json TEXT NOT NULL DEFAULT '[]',
    subject_contains TEXT,
    pdf_password TEXT,
    credit_card_id INTEGER REFERENCES credit_cards(id) ON DELETE SET NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    fetch_months INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_statement_import_rules_enabled
    ON statement_import_rules(is_enabled);

CREATE TABLE IF NOT EXISTS statement_tag_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_name TEXT NOT NULL,
    regex_patterns_json TEXT NOT NULL DEFAULT '[]',
    is_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS statement_import_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    gmail_scanned INTEGER NOT NULL DEFAULT 0,
    statements_parsed INTEGER NOT NULL DEFAULT 0,
    skipped_json TEXT,
    transactions_json TEXT NOT NULL DEFAULT '[]',
    source_gmail_ids_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS statement_import_fetched_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_message_id TEXT NOT NULL UNIQUE,
    rule_id INTEGER NOT NULL REFERENCES statement_import_rules(id) ON DELETE CASCADE,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_statement_import_fetched_rule
    ON statement_import_fetched_messages(rule_id);
