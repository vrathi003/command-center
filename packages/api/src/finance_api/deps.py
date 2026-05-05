"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import aiosqlite
from fastapi import Depends

from finance_api.settings import ApiSettings
from finance_common.db import open_db


def get_settings() -> ApiSettings:
    return ApiSettings()


async def get_conn(
    settings: Annotated[ApiSettings, Depends(get_settings)],
) -> AsyncIterator[aiosqlite.Connection]:
    async with open_db(settings.db_path) as conn:
        yield conn
