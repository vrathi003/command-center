"""Send Discord DMs via REST (bot token) — used by scheduled jobs."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def send_discord_dm(*, bot_token: str, user_id: str, content: str) -> bool:
    """Create or reuse a DM channel and post ``content`` (truncated to Discord limits)."""
    text = (content or "").strip()
    if not text:
        return False
    if len(text) > 2000:
        text = text[:1997] + "…"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }
    base = "https://discord.com/api/v10"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            ch = await client.post(
                f"{base}/users/@me/channels",
                headers=headers,
                json={"recipient_id": user_id},
            )
            if ch.status_code not in (200, 201):
                logger.warning("Discord DM channel: HTTP %s %s", ch.status_code, ch.text[:200])
                return False
            channel_id = ch.json().get("id")
            if not channel_id:
                return False
            msg = await client.post(
                f"{base}/channels/{channel_id}/messages",
                headers=headers,
                json={"content": text},
            )
            if msg.status_code not in (200, 201):
                logger.warning("Discord DM send: HTTP %s %s", msg.status_code, msg.text[:200])
                return False
    except Exception:
        logger.exception("Discord DM failed")
        return False
    return True
