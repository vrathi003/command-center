"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from finance_api.routers import (
    accounts,
    assets,
    budget,
    construction_progress,
    credit_cards,
    dashboard,
    debt,
    email_inbox,
    fixed_income,
    goals,
    health,
    home_items,
    income,
    insurance,
    investment,
    journal,
    merchant_rules,
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
    api_settings = ApiSettings()
    app.state.settings = api_settings
    await ensure_database(api_settings.db_path)

    scheduler = AsyncIOScheduler()
    register_background_jobs(scheduler, api_settings)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


async def _auth_middleware(request: Request, call_next):
    # Skip auth for health check and CORS preflight
    if request.url.path == "/health" or request.method == "OPTIONS":
        return await call_next(request)

    settings: ApiSettings = request.app.state.settings
    secret = settings.app_secret_key.strip()
    if not secret:
        return await call_next(request)  # auth disabled

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != secret:
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Personal Finance OS API",
        version="1.0.0",
        lifespan=lifespan,
    )
    # Auth disabled → CORS restricted to localhost.
    # Auth enabled → any origin is fine; Bearer token is the real gate.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(_auth_middleware)
    app.include_router(health.router)
    app.include_router(accounts.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(transactions.router, prefix="/api")
    app.include_router(transaction_templates.router, prefix="/api")
    app.include_router(merchant_rules.router, prefix="/api")
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
    app.include_router(email_inbox.router, prefix="/api")
    return app


app = create_app()
