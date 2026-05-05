"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finance_api.routers import (
    accounts,
    assets,
    budget,
    construction_progress,
    credit_cards,
    dashboard,
    debt,
    fixed_income,
    goals,
    health,
    home_items,
    income,
    insurance,
    investment,
    journal,
    net_worth,
    reports,
    subscriptions,
    transaction_templates,
    transactions,
)
from finance_api.routers import (
    settings as settings_router,
)
from finance_api.services.background_jobs import register_background_jobs
from finance_api.settings import ApiSettings
from finance_common.db import ensure_database

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _ = app
    api_settings = ApiSettings()
    await ensure_database(api_settings.db_path)

    scheduler = AsyncIOScheduler()
    register_background_jobs(scheduler, api_settings)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Personal Finance OS API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(accounts.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(transactions.router, prefix="/api")
    app.include_router(transaction_templates.router, prefix="/api")
    app.include_router(budget.router, prefix="/api")
    app.include_router(debt.router, prefix="/api")
    app.include_router(investment.router, prefix="/api")
    app.include_router(journal.router, prefix="/api")
    app.include_router(fixed_income.router, prefix="/api")
    app.include_router(net_worth.router, prefix="/api")
    app.include_router(goals.router, prefix="/api")
    app.include_router(income.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")
    app.include_router(settings_router.router, prefix="/api")
    app.include_router(subscriptions.router, prefix="/api")
    app.include_router(credit_cards.router, prefix="/api")
    app.include_router(assets.router, prefix="/api")
    app.include_router(insurance.router, prefix="/api")
    app.include_router(home_items.router, prefix="/api")
    app.include_router(construction_progress.router, prefix="/api")
    return app


app = create_app()
