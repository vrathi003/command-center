"""Discord bot entrypoint: `python -m finance_bot.main`."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from finance_bot.bot import FinanceBot
from finance_bot.settings import BotSettings
from finance_common.db import ensure_database, open_db
from finance_common.project_config import load_project_config


async def amain() -> None:
    settings = BotSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        project_config = await load_project_config(conn)
    if not project_config.discord_enabled:
        logger.info("Discord bot is disabled in project settings; exiting.")
        return
    if not settings.discord_bot_token.strip():
        logger.error("DISCORD_BOT_TOKEN is missing. Set it in .env (see .env.example).")
        sys.exit(1)
    bot = FinanceBot(settings)
    await bot.start(settings.discord_bot_token.strip())


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
