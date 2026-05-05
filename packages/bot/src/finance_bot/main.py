"""Discord bot entrypoint: `python -m finance_bot.main`."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from finance_bot.bot import FinanceBot
from finance_bot.settings import BotSettings


async def amain() -> None:
    settings = BotSettings()
    if not settings.discord_bot_token.strip():
        logger.error("DISCORD_BOT_TOKEN is missing. Set it in .env (see .env.example).")
        sys.exit(1)
    bot = FinanceBot(settings)
    await bot.start(settings.discord_bot_token.strip())


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
