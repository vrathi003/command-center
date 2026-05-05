"""Populate the local SQLite DB with demo rows (debts, transactions, budgets, investments).

Usage:
  uv run python scripts/seed_demo_data.py              # append demo financial rows (does not delete existing data)
  uv run python scripts/seed_demo_data.py --force      # DELETE rows in core financial tables only, then reseed those
  uv run python scripts/seed_demo_data.py --home-only  # append demo home-inventory items only (never touches other tables)
  uv run python scripts/seed_demo_data.py --home-only --replace-home   # clear home tables only, then seed home demo
  uv run python scripts/seed_demo_data.py --construction-only          # append synthetic construction snapshots only
  uv run python scripts/seed_demo_data.py --construction-only --replace-construction  # clear construction tables only, then seed

Requires DB_PATH in .env (see .env.example).

Safety:
  • Without --force, this script only INSERTs. Your existing transactions, debts, budgets, etc. are kept.
  • --force deletes ONLY: transactions, debts, budgets, investments, fixed_income, net_worth_history,
    goals, income_sources. It does NOT touch accounts, home inventory, credit cards, assets, insurance, etc.
  • --home-only never runs the financial demo inserts and never uses --force clearing.
  • --replace-home (with --home-only only) deletes rows in home_item_service_events and home_items, then inserts demos.
  • --construction-only never touches transactions, debts, budgets, home inventory, or any other non-construction table.
  • --replace-construction (with --construction-only only) deletes construction_projects (cascades snapshots/rows/labels), then seeds.
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
from datetime import date, timedelta
from typing import Any

import aiosqlite
from loguru import logger

from finance_common.config import AppSettings
from finance_common.db import ensure_database, open_db
from finance_common.repositories import budgets as budget_repo
from finance_common.repositories import construction_progress as construction_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories import fixed_income as fi_repo
from finance_common.repositories import goals as goals_repo
from finance_common.repositories import home_items as home_repo
from finance_common.repositories import income_sources as income_repo
from finance_common.repositories import investments as inv_repo
from finance_common.repositories import net_worth as nw_repo
from finance_common.repositories import settings_repo
from finance_common.repositories import transactions as tx_repo
from finance_common.types import (
    Category,
    DebtType,
    IncomeFrequency,
    IncomeType,
    PaymentMode,
    Taxability,
    rupees_to_paise,
)


async def _clear_financial_tables(conn: aiosqlite.Connection) -> None:
    """Destructive: core financial demo tables only. Does not touch home_items, accounts, assets, etc."""
    await conn.execute("DELETE FROM transactions")
    await conn.execute("DELETE FROM debts")
    await conn.execute("DELETE FROM budgets")
    await conn.execute("DELETE FROM investments")
    await conn.execute("DELETE FROM fixed_income")
    await conn.execute("DELETE FROM net_worth_history")
    await conn.execute("DELETE FROM goals")
    await conn.execute("DELETE FROM income_sources")
    await conn.commit()
    logger.info(
        "Cleared transactions, debts, budgets, investments, fixed_income, net_worth_history, "
        "goals, income_sources (home inventory and other modules unchanged)",
    )


async def _clear_home_tables(conn: aiosqlite.Connection) -> None:
    await conn.execute("DELETE FROM home_item_service_events")
    await conn.execute("DELETE FROM home_items")
    await conn.commit()
    logger.info("Cleared home_item_service_events and home_items")


async def _clear_construction_tables(conn: aiosqlite.Connection) -> None:
    """Remove all construction demo data; cascades snapshots, progress rows, zone labels."""
    await conn.execute("DELETE FROM construction_projects")
    await conn.commit()
    logger.info("Cleared construction_projects (cascades snapshots, rows, zone labels)")


async def _seed_home_demo(conn: aiosqlite.Connection) -> None:
    """Insert a few demo appliances / furniture rows with optional service history."""
    fridge_id = await home_repo.insert_home_item(
        conn,
        name="Refrigerator (double door)",
        category="appliance",
        brand="LG",
        model="GL-T432APZY",
        serial_number=None,
        room_location="Kitchen",
        purchase_date="2023-08-15",
        purchase_price_paise=rupees_to_paise(42_000),
        retailer="Reliance Digital",
        warranty_end_date="2026-08-14",
        extended_warranty=False,
        condition_status="good",
        notes="Demo seed row",
    )
    await home_repo.insert_service_event(
        conn,
        home_item_id=fridge_id,
        service_date=(date.today() - timedelta(days=120)).isoformat(),
        event_type="preventive",
        vendor="LG Service",
        description="Annual gas check",
        cost_paise=rupees_to_paise(1_200),
        next_service_due=None,
        notes=None,
    )

    ac_id = await home_repo.insert_home_item(
        conn,
        name="Split AC 1.5T",
        category="appliance",
        brand="Daikin",
        model=None,
        serial_number=None,
        room_location="Bedroom",
        purchase_date="2022-05-01",
        purchase_price_paise=rupees_to_paise(38_500),
        retailer=None,
        warranty_end_date="2025-05-01",
        extended_warranty=False,
        condition_status="good",
        notes=None,
    )
    await home_repo.insert_service_event(
        conn,
        home_item_id=ac_id,
        service_date=(date.today() - timedelta(days=45)).isoformat(),
        event_type="repair",
        vendor="Authorized service",
        description="Gas refill + clean",
        cost_paise=rupees_to_paise(3_500),
        next_service_due=(date.today() + timedelta(days=300)).isoformat(),
        notes=None,
    )

    await home_repo.insert_home_item(
        conn,
        name="Sofa (3-seater)",
        category="furniture",
        brand="Urban Ladder",
        model=None,
        serial_number=None,
        room_location="Living room",
        purchase_date="2024-01-20",
        purchase_price_paise=rupees_to_paise(28_000),
        retailer="Online",
        warranty_end_date=None,
        extended_warranty=False,
        condition_status="good",
        notes="Demo seed — no warranty on furniture",
    )

    logger.info("Inserted demo home inventory rows")


async def _seed_construction_demo(conn: aiosqlite.Connection) -> None:
    """Synthetic two-month snapshot so the Construction chart has points without uploading a PDF."""
    p = await construction_repo.get_or_create_default_project(conn)
    warn = ["Synthetic demo rows (not from a PDF upload)."]
    dec_zones: list[dict[str, Any]] = [
        {
            "zone_key": "tower:1",
            "zone_type": "tower",
            "tower_number": 1,
            "tabular_index": 1,
            "rows": [
                {
                    "section": "Structure",
                    "activity_raw": "Brickwork",
                    "floors_complete": 20,
                    "pct_complete": 80,
                    "status": "WIP",
                    "remark": None,
                },
                {
                    "section": "Finishing",
                    "activity_raw": "Wall Tiles",
                    "floors_complete": 10,
                    "pct_complete": 40,
                    "status": "WIP",
                    "remark": None,
                },
            ],
        },
        {
            "zone_key": "tower:14",
            "zone_type": "tower",
            "tower_number": 14,
            "tabular_index": 13,
            "rows": [
                {
                    "section": "Structure",
                    "activity_raw": "Brickwork",
                    "floors_complete": 15,
                    "pct_complete": 60,
                    "status": "WIP",
                    "remark": None,
                },
            ],
        },
    ]
    mar_zones: list[dict[str, Any]] = [
        {
            "zone_key": "tower:1",
            "zone_type": "tower",
            "tower_number": 1,
            "tabular_index": 1,
            "rows": [
                {
                    "section": "Structure",
                    "activity_raw": "Brickwork",
                    "floors_complete": 26,
                    "pct_complete": 100,
                    "status": "Completed",
                    "remark": None,
                },
                {
                    "section": "Finishing",
                    "activity_raw": "Wall Tiles",
                    "floors_complete": 18,
                    "pct_complete": 70,
                    "status": "WIP",
                    "remark": None,
                },
            ],
        },
        {
            "zone_key": "tower:14",
            "zone_type": "tower",
            "tower_number": 14,
            "tabular_index": 13,
            "rows": [
                {
                    "section": "Structure",
                    "activity_raw": "Brickwork",
                    "floors_complete": 22,
                    "pct_complete": 85,
                    "status": "WIP",
                    "remark": None,
                },
            ],
        },
    ]
    await construction_repo.replace_snapshot(
        conn,
        project_id=p.id,
        as_of_date="2025-12-01",
        source_filename="demo-seed-construction-dec25.txt",
        file_sha256=None,
        parse_warnings=warn,
        zone_rows=dec_zones,
    )
    await construction_repo.replace_snapshot(
        conn,
        project_id=p.id,
        as_of_date="2026-03-01",
        source_filename="demo-seed-construction-mar26.txt",
        file_sha256=None,
        parse_warnings=warn,
        zone_rows=mar_zones,
    )
    logger.info("Inserted demo construction snapshots (2025-12-01, 2026-03-01)")


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


async def seed_demo(*, force: bool) -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)

    async with open_db(settings.db_path) as conn:
        if force:
            await _clear_financial_tables(conn)

        fy = await settings_repo.get_current_fy(conn)
        fy_s = str(fy)
        today = date.today()

        demo_budgets: list[tuple[str, int]] = [
            ("Food Delivery", 30_000 * 100),
            ("Groceries", 25_000 * 100),
            ("Transport & Fuel", 15_000 * 100),
            ("Housing & Rent", 45_000 * 100),
            ("Entertainment", 10_000 * 100),
            ("Health & Medical", 8_000 * 100),
        ]
        for cat, cap in demo_budgets:
            await budget_repo.set_monthly_budget(
                conn,
                category=cat,
                fy_year=fy_s,
                monthly_amount_paise=cap,
                effective_from=today,
            )

        await debt_repo.insert_debt(
            conn,
            name="HDFC Home Loan",
            lender="HDFC Ltd",
            type_=DebtType.HOME_LOAN.value,
            original_amount_paise=65_00_000 * 100,
            current_balance_paise=42_50_000 * 100,
            emi_paise=38_500 * 100,
            rate_percent=8.45,
            start_date="2021-06-01",
            next_emi_date=(today + timedelta(days=10)).isoformat(),
            status="active",
        )
        await debt_repo.insert_debt(
            conn,
            name="ICICI Car Loan",
            lender="ICICI Bank",
            type_=DebtType.CAR_LOAN.value,
            original_amount_paise=12_00_000 * 100,
            current_balance_paise=4_20_000 * 100,
            emi_paise=28_900 * 100,
            rate_percent=9.15,
            start_date="2023-01-15",
            next_emi_date=(today + timedelta(days=5)).isoformat(),
            status="active",
        )
        await debt_repo.insert_debt(
            conn,
            name="HDFC Credit Card (revolving)",
            lender="HDFC Bank",
            type_=DebtType.CC_REVOLVING.value,
            original_amount_paise=None,
            current_balance_paise=1_85_000 * 100,
            emi_paise=None,
            rate_percent=42.0,
            start_date=None,
            next_emi_date=None,
            status="active",
        )

        month_start = today.replace(day=1)
        samples: list[tuple[date, float, str, str | None, str, str | None]] = [
            (today, 480, Category.FOOD_DELIVERY.value, "Swiggy", PaymentMode.UPI.value, "dinner"),
            (
                today - timedelta(days=1),
                1200,
                Category.CLOTHING.value,
                "Amazon",
                PaymentMode.HDFC_CC.value,
                None,
            ),
            (
                today - timedelta(days=2),
                3500,
                Category.GROCERIES.value,
                "BigBasket",
                PaymentMode.UPI.value,
                None,
            ),
            (
                today - timedelta(days=3),
                2000,
                Category.TRANSPORT_FUEL.value,
                "Shell",
                PaymentMode.UPI.value,
                None,
            ),
            (
                today - timedelta(days=4),
                380,
                Category.FOOD_DELIVERY.value,
                "Zomato",
                PaymentMode.UPI.value,
                None,
            ),
            (
                today - timedelta(days=5),
                25000,
                Category.HOUSING_RENT.value,
                "Landlord",
                PaymentMode.BANK_TRANSFER.value,
                None,
            ),
            (
                month_start + timedelta(days=2),
                18000,
                Category.EMI_LOAN.value,
                "Car EMI",
                PaymentMode.EMI.value,
                None,
            ),
            (
                month_start + timedelta(days=5),
                899,
                Category.SUBSCRIPTIONS.value,
                "Streaming",
                PaymentMode.HDFC_CC.value,
                None,
            ),
            (
                month_start + timedelta(days=8),
                1200,
                Category.HEALTH_MEDICAL.value,
                "Pharmacy",
                PaymentMode.UPI.value,
                None,
            ),
        ]

        for d, amt, cat, mer, pm, note in samples:
            await tx_repo.insert_transaction(
                conn,
                tx_date=d,
                amount_paise=rupees_to_paise(amt),
                category=cat,
                merchant=mer,
                payment_mode=pm,
                account=None,
                notes=note,
                source="demo_seed",
            )

        await conn.execute(
            """
            INSERT INTO investments (
                instrument, type, isin_code, units,
                avg_price_paise, current_price_paise, last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, date('now', 'localtime'))
            """,
            (
                "Nifty 50 Index Fund — Direct Growth",
                "Mutual Fund",
                "INF204KB14I2",
                1847.329,
                250 * 100,
                265 * 100,
            ),
        )
        await conn.execute(
            """
            INSERT INTO investments (
                instrument, type, isin_code, units,
                avg_price_paise, current_price_paise, last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, date('now', 'localtime'))
            """,
            (
                "HDFC Bank",
                "Stock",
                "INE040A01034",
                120.0,
                1450 * 100,
                1680 * 100,
            ),
        )
        await conn.execute(
            """
            INSERT INTO fixed_income (
                institution, type, principal_paise, rate_percent, start_date, maturity_date
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("EPFO / PPF", "PPF", 15_00_000 * 100, 7.1, "2020-04-01", None),
        )
        await conn.execute(
            """
            INSERT INTO fixed_income (
                institution, type, principal_paise, rate_percent, start_date, maturity_date
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("SBI", "Fixed Deposit", 5_00_000 * 100, 7.25, "2025-01-10", "2028-01-10"),
        )

        await goals_repo.insert_goal(
            conn,
            name="Emergency fund",
            category="Cash",
            target_amount_paise=rupees_to_paise(5_00_000),
            current_amount_paise=rupees_to_paise(1_50_000),
            monthly_contribution_paise=rupees_to_paise(25_000),
            target_date="2026-03-31",
        )
        await goals_repo.insert_goal(
            conn,
            name="Next holiday",
            category="Travel",
            target_amount_paise=rupees_to_paise(2_00_000),
            current_amount_paise=rupees_to_paise(40_000),
            monthly_contribution_paise=rupees_to_paise(10_000),
            target_date="2025-12-31",
        )

        await income_repo.insert_income_source(
            conn,
            name="Salary — primary",
            type_=IncomeType.SALARY.value,
            amount_paise=rupees_to_paise(1_50_000),
            frequency=IncomeFrequency.MONTHLY.value,
            taxability=Taxability.FULLY_TAXABLE.value,
        )
        await income_repo.insert_income_source(
            conn,
            name="Freelance clients",
            type_=IncomeType.FREELANCE.value,
            amount_paise=rupees_to_paise(45_000),
            frequency=IncomeFrequency.MONTHLY.value,
            taxability=Taxability.FULLY_TAXABLE.value,
        )
        await income_repo.insert_income_source(
            conn,
            name="Flat rent",
            type_=IncomeType.RENTAL.value,
            amount_paise=rupees_to_paise(3_60_000),
            frequency=IncomeFrequency.ANNUAL.value,
            taxability=Taxability.FULLY_TAXABLE.value,
        )
        await settings_repo.set_value(conn, "tax_regime", "new")
        await settings_repo.set_value(conn, "tax_80c_annual_paise", str(rupees_to_paise(150_000)))

        _, mkt, _, _ = await inv_repo.portfolio_totals(conn)
        fi_total, _ = await fi_repo.total_principal(conn)
        debt_total, _, _ = await debt_repo.aggregate_active(conn)
        assets_now = mkt + fi_total
        liabilities_now = debt_total

        anchor = today.replace(day=1)
        month_starts = [_add_months(anchor, -i) for i in range(5, -1, -1)]
        for idx, d in enumerate(month_starts):
            growth_paise = (len(month_starts) - 1 - idx) * 4_000_000
            a = max(0, assets_now - growth_paise)
            await nw_repo.upsert_snapshot(
                conn,
                snapshot_date=d.isoformat(),
                total_assets_paise=a,
                total_liabilities_paise=liabilities_now,
            )
        if today != month_starts[-1]:
            await nw_repo.upsert_snapshot(
                conn,
                snapshot_date=today.isoformat(),
                total_assets_paise=assets_now,
                total_liabilities_paise=liabilities_now,
            )

    logger.info("Demo data written to {}", settings.db_path)


async def seed_home_only(*, replace_home: bool) -> None:
    """Only home inventory demo rows. Never touches transactions, debts, etc."""
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        if replace_home:
            await _clear_home_tables(conn)
        await _seed_home_demo(conn)
    logger.info("Home inventory demo written to {}", settings.db_path)


async def seed_construction_only(*, replace_construction: bool) -> None:
    """Only construction progress demo rows. Never touches financial or home tables."""
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        if replace_construction:
            await _clear_construction_tables(conn)
        await _seed_construction_demo(conn)
    logger.info("Construction demo written to {}", settings.db_path)


def main() -> None:
    p = argparse.ArgumentParser(description="Seed demo data into SQLite.")
    p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Delete existing rows in core financial tables only (see docstring), then reseed those. "
            "Does not affect home inventory. Cannot be used with --home-only."
        ),
    )
    p.add_argument(
        "--home-only",
        action="store_true",
        help="Only insert demo home-inventory rows; skip all financial demo inserts.",
    )
    p.add_argument(
        "--replace-home",
        action="store_true",
        help=(
            "With --home-only: delete home_item_service_events and home_items first, "
            "then insert demos."
        ),
    )
    p.add_argument(
        "--construction-only",
        action="store_true",
        help=(
            "Only insert synthetic construction-progress snapshots; skip financial and home demo."
        ),
    )
    p.add_argument(
        "--replace-construction",
        action="store_true",
        help=(
            "With --construction-only: delete construction tables (projects CASCADE), then seed."
        ),
    )
    args = p.parse_args()
    if args.home_only and args.force:
        logger.error(
            "Use --home-only alone, or --home-only --replace-home. "
            "Do not combine with --force.",
        )
        raise SystemExit(2)
    if args.replace_home and not args.home_only:
        logger.error("--replace-home requires --home-only")
        raise SystemExit(2)
    if args.construction_only and args.force:
        logger.error("--construction-only cannot be combined with --force (financial wipe).")
        raise SystemExit(2)
    if args.construction_only and args.home_only:
        logger.error("Use --construction-only alone, or --home-only alone — not both.")
        raise SystemExit(2)
    if args.replace_construction and not args.construction_only:
        logger.error("--replace-construction requires --construction-only")
        raise SystemExit(2)
    if args.home_only:
        asyncio.run(seed_home_only(replace_home=args.replace_home))
    elif args.construction_only:
        asyncio.run(seed_construction_only(replace_construction=args.replace_construction))
    else:
        asyncio.run(seed_demo(force=args.force))


if __name__ == "__main__":
    main()
