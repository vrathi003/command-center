"""Discord bot settings."""

from __future__ import annotations

from pydantic import Field

from finance_common.config import AppSettings


class BotSettings(AppSettings):
    discord_bot_token: str = Field(default="", alias="DISCORD_BOT_TOKEN")
    discord_user_id: str = Field(default="", alias="DISCORD_USER_ID")
    discord_dev_guild_id: str | None = Field(default=None, alias="DISCORD_DEV_GUILD_ID")
