"""Lightweight SQLite migrations after schema bootstrap."""

from __future__ import annotations

import aiosqlite


async def _column_names(conn: aiosqlite.Connection, table: str) -> set[str]:
    cur = await conn.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return {str(r[1]) for r in rows}


async def apply_migrations(conn: aiosqlite.Connection) -> None:
    """Add columns / tables that may be missing on existing databases."""
    inv_cols = await _column_names(conn, "investments")
    if "sector" not in inv_cols:
        await conn.execute("ALTER TABLE investments ADD COLUMN sector TEXT")
    if "equity_tax_class" not in inv_cols:
        await conn.execute(
            "ALTER TABLE investments ADD COLUMN equity_tax_class TEXT DEFAULT 'unspecified'"
        )
    await conn.commit()

    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='subscriptions'"
    )
    sub_table = await cur.fetchone()
    if sub_table is None:
        await conn.executescript(
            """
            CREATE TABLE subscriptions (
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
            CREATE INDEX idx_subscriptions_active ON subscriptions(is_active);
            """
        )
        await conn.commit()

    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='credit_cards'"
    )
    if await cur.fetchone() is None:
        await conn.executescript(
            """
            CREATE TABLE credit_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                issuer TEXT,
                last_four TEXT,
                credit_limit_paise INTEGER NOT NULL,
                current_balance_paise INTEGER,
                notes TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE credit_card_statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                credit_card_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                extraction_preview TEXT,
                summary_json TEXT,
                line_items_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending_review',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (credit_card_id) REFERENCES credit_cards(id) ON DELETE CASCADE
            );
            CREATE INDEX idx_cc_statements_card ON credit_card_statements(credit_card_id);
            """
        )
        await conn.commit()

    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='credit_card_emis'"
    )
    if await cur.fetchone() is None:
        await conn.executescript(
            """
            CREATE TABLE credit_card_emis (
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
            CREATE INDEX idx_cc_emis_card ON credit_card_emis(credit_card_id);
            """
        )
        await conn.commit()

    tx_cols = await _column_names(conn, "transactions")
    if "transaction_type" not in tx_cols:
        await conn.execute(
            "ALTER TABLE transactions ADD COLUMN transaction_type TEXT NOT NULL DEFAULT 'debit'"
        )
        await conn.commit()
    tx_cols = await _column_names(conn, "transactions")
    if "account_id" not in tx_cols:
        await conn.execute("ALTER TABLE transactions ADD COLUMN account_id INTEGER")
    if "transfer_pair_id" not in tx_cols:
        await conn.execute("ALTER TABLE transactions ADD COLUMN transfer_pair_id TEXT")
    if "tags" not in tx_cols:
        await conn.execute("ALTER TABLE transactions ADD COLUMN tags TEXT")
    await conn.commit()
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_transfer_pair ON transactions(transfer_pair_id)"
    )
    await conn.commit()

    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='transaction_templates'"
    )
    if await cur.fetchone() is None:
        await conn.executescript(
            """
            CREATE TABLE transaction_templates (
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
            """
        )
        await conn.commit()

    emi_cols = await _column_names(conn, "credit_card_emis")
    if emi_cols and "loan_type" not in emi_cols:
        await conn.execute("ALTER TABLE credit_card_emis ADD COLUMN loan_type TEXT")
    if emi_cols and "creation_date" not in emi_cols:
        await conn.execute("ALTER TABLE credit_card_emis ADD COLUMN creation_date TEXT")
    if emi_cols and "finish_date" not in emi_cols:
        await conn.execute("ALTER TABLE credit_card_emis ADD COLUMN finish_date TEXT")
    if emi_cols and "principal_paise" not in emi_cols:
        await conn.execute("ALTER TABLE credit_card_emis ADD COLUMN principal_paise INTEGER")
    if emi_cols and "outstanding_instalment_paise" not in emi_cols:
        await conn.execute(
            "ALTER TABLE credit_card_emis ADD COLUMN outstanding_instalment_paise INTEGER",
        )
    await conn.commit()

    # ── Assets + Insurance module ──────────────────────────────────────────────
    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assets'"
    )
    if await cur.fetchone() is None:
        await conn.executescript(
            """
            CREATE TABLE assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
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
            CREATE INDEX idx_assets_type ON assets(type);
            CREATE INDEX idx_assets_deleted ON assets(is_deleted);

            CREATE TABLE asset_real_estate (
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
                possession_date_estimated TEXT,
                possession_date_actual TEXT,
                agreement_value_paise INTEGER,
                circle_rate_psf_paise INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
            );

            CREATE TABLE asset_vehicles (
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

            CREATE TABLE asset_costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                cost_type TEXT NOT NULL,
                description TEXT,
                amount_paise INTEGER NOT NULL,
                date TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
            );
            CREATE INDEX idx_asset_costs_asset ON asset_costs(asset_id);

            CREATE TABLE asset_loans (
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
            CREATE INDEX idx_asset_loans_asset ON asset_loans(asset_id);
            CREATE INDEX idx_asset_loans_debt ON asset_loans(debt_id);

            CREATE TABLE asset_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                payment_date TEXT NOT NULL,
                amount_paise INTEGER NOT NULL,
                milestone TEXT,
                payment_mode TEXT,
                reference_number TEXT,
                receipt_number TEXT,
                receipt_date TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
            );
            CREATE INDEX idx_asset_payments_asset ON asset_payments(asset_id);
            """
        )
        await conn.commit()

    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='insurance_policies'"
    )
    if await cur.fetchone() is None:
        await conn.executescript(
            """
            CREATE TABLE insurance_policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
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
                asset_id INTEGER,
                tax_deduction_section TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                is_deleted INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (asset_id) REFERENCES assets(id)
            );
            CREATE INDEX idx_insurance_status ON insurance_policies(status);
            CREATE INDEX idx_insurance_deleted ON insurance_policies(is_deleted);

            CREATE TABLE insurance_premiums (
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
            CREATE INDEX idx_insurance_premiums_policy ON insurance_premiums(policy_id);
            """
        )
        await conn.commit()

    # ── Debt enhancements: tenure, first EMI date, phased disbursal ──────────
    debt_cols = await _column_names(conn, "debts")
    if "tenure_months" not in debt_cols:
        await conn.execute("ALTER TABLE debts ADD COLUMN tenure_months INTEGER")
    if "first_emi_date" not in debt_cols:
        await conn.execute("ALTER TABLE debts ADD COLUMN first_emi_date TEXT")
    if "full_emi_start_date" not in debt_cols:
        await conn.execute("ALTER TABLE debts ADD COLUMN full_emi_start_date TEXT")
    await conn.commit()

    # ── Asset cost enhancements: is_paid flag ────────────────────────────────
    cost_cols = await _column_names(conn, "asset_costs")
    if "is_paid" not in cost_cols:
        await conn.execute(
            "ALTER TABLE asset_costs ADD COLUMN is_paid INTEGER NOT NULL DEFAULT 1"
        )
        await conn.commit()

    # ── Asset payment enhancements: is_paid flag ─────────────────────────────
    payment_cols = await _column_names(conn, "asset_payments")
    if "is_paid" not in payment_cols:
        await conn.execute(
            "ALTER TABLE asset_payments ADD COLUMN is_paid INTEGER NOT NULL DEFAULT 0"
        )
        await conn.commit()
    if "due_date" not in payment_cols:
        await conn.execute("ALTER TABLE asset_payments ADD COLUMN due_date TEXT")
    if "paid_date" not in payment_cols:
        await conn.execute("ALTER TABLE asset_payments ADD COLUMN paid_date TEXT")
    if "fund_source" not in payment_cols:
        await conn.execute(
            "ALTER TABLE asset_payments ADD COLUMN fund_source TEXT NOT NULL DEFAULT 'cash'"
        )
    had_split_amount_cols = "amount_cash_paise" in payment_cols
    if "amount_cash_paise" not in payment_cols:
        await conn.execute(
            "ALTER TABLE asset_payments ADD COLUMN amount_cash_paise INTEGER NOT NULL DEFAULT 0"
        )
    if "amount_loan_paise" not in payment_cols:
        await conn.execute(
            "ALTER TABLE asset_payments ADD COLUMN amount_loan_paise INTEGER NOT NULL DEFAULT 0"
        )
    await conn.commit()
    if not had_split_amount_cols:
        await conn.execute(
            """
            UPDATE asset_payments
            SET amount_cash_paise = CASE WHEN fund_source = 'bank_loan' THEN 0 ELSE amount_paise END,
                amount_loan_paise = CASE WHEN fund_source = 'bank_loan' THEN amount_paise ELSE 0 END
            """
        )
        await conn.commit()
    # Legacy rows (no due date, still on old is_paid=0 default): treat payment_date as paid.
    await conn.execute(
        """
        UPDATE asset_payments
        SET paid_date = payment_date,
            is_paid = 1
        WHERE (paid_date IS NULL OR paid_date = '')
          AND (due_date IS NULL OR due_date = '')
          AND is_paid = 0
        """
    )
    await conn.commit()

    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='home_items'"
    )
    if await cur.fetchone() is None:
        await conn.executescript(
            """
            CREATE TABLE home_items (
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
            CREATE INDEX idx_home_items_category ON home_items(category);
            CREATE INDEX idx_home_items_deleted ON home_items(is_deleted);
            CREATE INDEX idx_home_items_warranty ON home_items(warranty_end_date);
            CREATE TABLE home_item_service_events (
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
            CREATE INDEX idx_home_service_item ON home_item_service_events(home_item_id);
            CREATE INDEX idx_home_service_date ON home_item_service_events(service_date);
            """
        )
        await conn.commit()

    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='loan_disbursals'"
    )
    if await cur.fetchone() is None:
        await conn.executescript(
            """
            CREATE TABLE loan_disbursals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                debt_id         INTEGER NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
                disbursal_date  TEXT NOT NULL,
                amount_paise    INTEGER NOT NULL,
                notes           TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX idx_loan_disbursals_debt ON loan_disbursals(debt_id);
            """
        )
        await conn.commit()

    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='construction_projects'"
    )
    if await cur.fetchone() is None:
        await conn.executescript(
            """
            CREATE TABLE construction_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE construction_zone_labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES construction_projects(id) ON DELETE CASCADE,
                zone_key TEXT NOT NULL,
                label TEXT NOT NULL,
                UNIQUE (project_id, zone_key)
            );
            CREATE INDEX idx_construction_zone_labels_project ON construction_zone_labels(project_id);
            CREATE TABLE construction_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES construction_projects(id) ON DELETE CASCADE,
                as_of_date TEXT NOT NULL,
                source_filename TEXT NOT NULL,
                file_sha256 TEXT,
                parse_warnings_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (project_id, as_of_date)
            );
            CREATE INDEX idx_construction_snapshots_project_date ON construction_snapshots(project_id, as_of_date DESC);
            CREATE TABLE construction_progress_rows (
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
            CREATE INDEX idx_construction_rows_snapshot ON construction_progress_rows(snapshot_id);
            CREATE INDEX idx_construction_rows_zone ON construction_progress_rows(snapshot_id, zone_key);
            """
        )
        await conn.commit()

    cur = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='journal_entries'"
    )
    if await cur.fetchone() is None:
        await conn.executescript(
            """
            CREATE TABLE journal_entries (
                entry_date TEXT PRIMARY KEY NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        await conn.commit()
