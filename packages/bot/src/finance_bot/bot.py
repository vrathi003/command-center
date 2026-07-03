"""Discord client and slash commands."""

from __future__ import annotations

import calendar
import contextlib
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import ClassVar

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from finance_bot.settings import BotSettings
from finance_bot.transfer_flow import (
    PICK_EMOJIS,
    PendingTransfer,
    accounts_to_likes,
    pick_accounts_for_display,
    resolve_transfer_accounts,
)
from finance_common.classification.matcher import match_merchant
from finance_common.db import ensure_database, open_db
from finance_common.parsing.account_mentions import (
    AccountLike,
    extract_account_fragment,
    match_account_fuzzy,
)
from finance_common.parsing.expense_parser import (
    ExpenseParseError,
    ParsedExpense,
    ParsedTransferLine,
    parse_expense_line,
    try_parse_transfer_line,
)
from finance_common.parsing.template_line import (
    match_template_longest_prefix,
    strip_template_prefix,
)
from finance_common.reports_fy import build_fy_summary
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import budgets as budget_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories import goals as goals_repo
from finance_common.repositories import merchant_rules as merchant_rules_repo
from finance_common.repositories import net_worth as nw_repo
from finance_common.repositories import settings_repo
from finance_common.repositories import transaction_templates as tmpl_repo
from finance_common.repositories import transactions as tx_repo
from finance_common.types import Category, PaymentMode

REACTION_EDIT = "\U0001f504"  # 🔄
REACTION_DELETE = "\u274c"  # ❌

# Plain-text log: "log 250 zomato yesterday" (same NL format as /log `entry`)
_LOG_LINE_RE = re.compile(r"^\s*log\s+(.+)$", re.IGNORECASE | re.DOTALL)


def _parse_tx_id_footer(text: str | None) -> int | None:
    if not text:
        return None
    t = text.strip()
    m = re.match(r"ids=(\d+)\+(\d+)", t)
    if m:
        return int(m.group(1))
    m = re.match(r"id=(\d+)", t)
    if m:
        return int(m.group(1))
    return None


@dataclass(frozen=True, slots=True)
class PersistExpenseResult:
    parsed: ParsedExpense
    tid: int
    account_name: str | None = None


@dataclass(frozen=True, slots=True)
class PersistTransferResult:
    entry: str
    out_id: int
    in_id: int
    pair_id: str
    amount_paise: int


def _rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"


class FinanceBot(commands.Bot):
    def __init__(self, settings: BotSettings) -> None:
        self._settings = settings
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        intents.reactions = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        self._settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        await ensure_database(self._settings.db_path)
        await self.add_cog(ExpenseCog(self, self._settings))
        guild_id = self._settings.discord_dev_guild_id
        if guild_id and guild_id.strip():
            g = discord.Object(id=int(guild_id.strip()))
            self.tree.copy_global_to(guild=g)
            await self.tree.sync(guild=g)
            logger.info("Discord command tree synced to guild {}", guild_id)
        else:
            await self.tree.sync()
            logger.info("Discord command tree synced globally")


class ExpenseCog(commands.Cog):
    """Expense logging, balances, and read-only finance summaries."""

    _pending_transfers: ClassVar[dict[int, PendingTransfer]] = {}

    def __init__(self, bot: FinanceBot, settings: BotSettings) -> None:
        self.bot = bot
        self._settings = settings

    def _allowed(self, interaction: discord.Interaction) -> bool:
        return self._allowed_user_id(interaction.user.id)

    def _allowed_user_id(self, user_id: int) -> bool:
        if not self._settings.discord_user_id:
            logger.warning("DISCORD_USER_ID not set — allowing all users (dev only).")
            return True
        return str(user_id) == str(self._settings.discord_user_id).strip()

    async def _merge_transfer_from_template(
        self,
        tpl: tmpl_repo.TemplateRow,
        remainder: str,
    ) -> tuple[ParsedTransferLine | None, str | None]:
        """Build a ParsedTransferLine from a transfer template + optional remainder text."""
        rem = remainder.strip()
        pt = try_parse_transfer_line(rem) if rem else None
        if pt:
            merged = replace(pt, notes=rem or pt.notes)
        elif tpl.amount is not None and rem:
            merged = ParsedTransferLine(
                amount_paise=tpl.amount,
                fragment_from=None,
                fragment_to=rem,
                transaction_date=date.today(),
                notes=rem,
            )
        elif tpl.amount is not None and not rem:
            return (
                None,
                "Add a destination after the template name "
                "(e.g. `template MyXfer to icici`).",
            )
        else:
            return None, "Transfer template needs an amount on the template or in the message."

        if tpl.account_id is not None:
            async with open_db(self._settings.db_path) as conn:
                acc = await accounts_repo.get_account(conn, tpl.account_id)
            if acc is not None:
                merged = replace(merged, fragment_from=acc.name)
        return merged, None

    async def _persist_template_expense(
        self,
        tpl: tmpl_repo.TemplateRow,
        remainder: str,
        original_entry: str,
        discord_message_id: str,
    ) -> tuple[PersistExpenseResult | None, str | None]:
        """Insert a debit/credit row from a template + optional NL remainder."""
        rem = remainder.strip()
        if rem:
            try:
                pe = parse_expense_line(rem)
            except ExpenseParseError as e:
                return None, str(e)
            amount_paise = pe.amount_paise
            tx_date = pe.transaction_date
            cat_str = tpl.category if tpl.category else pe.category.value
            merchant = tpl.merchant if tpl.merchant else pe.merchant
            pay_str = tpl.payment_mode if tpl.payment_mode else pe.payment_mode.value
        else:
            if tpl.amount is None:
                return (
                    None,
                    "Add an amount after the template name, "
                    "or set a default amount on the template.",
                )
            amount_paise = tpl.amount
            tx_date = date.today()
            cat_str = tpl.category or Category.OTHER.value
            merchant = tpl.merchant
            pay_str = tpl.payment_mode or PaymentMode.UPI.value

        tx_type = tpl.transaction_type
        if tx_type not in ("debit", "credit"):
            tx_type = "debit"

        async with open_db(self._settings.db_path) as conn:
            aid = tpl.account_id
            acc_name = None
            if aid is not None:
                row = await accounts_repo.get_account(conn, aid)
                if row:
                    acc_name = row.name
            else:
                accts = await accounts_repo.list_accounts(conn, active_only=True)
                likes = [AccountLike(id=a.id, name=a.name) for a in accts]
                frag = extract_account_fragment(rem if rem else original_entry)
                matched = match_account_fuzzy(frag, likes) if frag else None
                if matched:
                    row = await accounts_repo.get_account(conn, matched.id)
                    if row:
                        acc_name = row.name
                        aid = row.id

            tid = await tx_repo.insert_transaction(
                conn,
                tx_date=tx_date,
                amount_paise=amount_paise,
                category=cat_str,
                merchant=merchant,
                payment_mode=pay_str,
                account=acc_name,
                notes=original_entry,
                source="discord",
                discord_message_id=discord_message_id,
                account_id=aid,
                transaction_type=tx_type,
                tags=tpl.tags,
            )

        parsed = ParsedExpense(
            amount_paise=amount_paise,
            category=Category.from_string(cat_str),
            merchant=merchant,
            payment_mode=PaymentMode.from_string(pay_str),
            transaction_date=tx_date,
            notes=original_entry,
        )
        return PersistExpenseResult(parsed=parsed, tid=tid, account_name=acc_name), None

    async def _persist_log(
        self,
        entry: str,
        discord_message_id: str,
        channel: discord.abc.Messageable,
        user_id: int,
    ) -> tuple[PersistExpenseResult | PersistTransferResult | None, str | None]:
        """Returns (result, error). (None, None) means a transfer account-pick message was sent."""
        stripped = strip_template_prefix(entry)
        if stripped is not None:
            async with open_db(self._settings.db_path) as conn:
                templates = await tmpl_repo.list_templates(conn)
            matched = match_template_longest_prefix(stripped, templates)
            if matched is None:
                return (
                    None,
                    f"No template matched {stripped!r}. Create one under Transactions → Templates.",
                )
            tpl, remainder = matched
            if tpl.transaction_type == "transfer":
                pt_merged, terr = await self._merge_transfer_from_template(tpl, remainder)
                if terr:
                    return None, terr
                if pt_merged is None:
                    return None, "Could not build transfer from template."
                return await self._persist_transfer_flow(
                    pt_merged, discord_message_id, channel, user_id
                )
            return await self._persist_template_expense(
                tpl, remainder, entry, discord_message_id
            )

        pt = try_parse_transfer_line(entry)
        if pt is not None:
            return await self._persist_transfer_flow(pt, discord_message_id, channel, user_id)
        async with open_db(self._settings.db_path) as conn:
            rules = await merchant_rules_repo.list_active_rules_for_matching(conn)
            parsed = parse_expense_line(
                entry, classify=lambda m: match_merchant(m, rules)
            )
            accounts = await accounts_repo.list_accounts(conn, active_only=True)
            likes = [AccountLike(id=a.id, name=a.name) for a in accounts]
            frag = extract_account_fragment(entry)
            matched = match_account_fuzzy(frag, likes) if frag else None
            acc_name = None
            aid = None
            if matched:
                row = await accounts_repo.get_account(conn, matched.id)
                if row:
                    acc_name = row.name
                    aid = row.id
            tid = await tx_repo.insert_transaction(
                conn,
                tx_date=parsed.transaction_date,
                amount_paise=parsed.amount_paise,
                category=parsed.category.value,
                merchant=parsed.merchant,
                payment_mode=parsed.payment_mode.value,
                account=acc_name,
                notes=parsed.notes,
                source="discord",
                discord_message_id=discord_message_id,
                account_id=aid,
            )
        return PersistExpenseResult(parsed=parsed, tid=tid, account_name=acc_name), None

    async def _insert_transfer_pair_discord(
        self,
        conn: aiosqlite.Connection,
        pt: ParsedTransferLine,
        from_id: int,
        to_id: int,
        discord_message_id: str,
    ) -> tuple[int, int, str]:
        from_a = await accounts_repo.get_account(conn, from_id)
        to_a = await accounts_repo.get_account(conn, to_id)
        if from_a is None or to_a is None:
            msg = "account missing"
            raise RuntimeError(msg)
        return await tx_repo.insert_transfer_pair(
            conn,
            amount_paise=pt.amount_paise,
            tx_date=pt.transaction_date,
            from_account_id=from_id,
            to_account_id=to_id,
            from_account_name=from_a.name,
            to_account_name=to_a.name,
            notes=pt.notes,
            tags=None,
            source="discord",
            discord_message_id=discord_message_id,
        )

    async def _persist_transfer_flow(
        self,
        pt: ParsedTransferLine,
        discord_message_id: str,
        channel: discord.abc.Messageable,
        user_id: int,
    ) -> tuple[PersistTransferResult | None, str | None]:
        async with open_db(self._settings.db_path) as conn:
            accounts = await accounts_repo.list_accounts(conn, active_only=True)
        if len(accounts) < 2:
            return (
                None,
                "Add at least two active accounts in the dashboard (Accounts page) first.",
            )
        from_a, to_a = resolve_transfer_accounts(accounts, pt)
        if from_a and to_a:
            if from_a.id == to_a.id:
                return None, "From and to accounts must be different."
            async with open_db(self._settings.db_path) as conn:
                out_id, in_id, pair_id = await self._insert_transfer_pair_discord(
                    conn, pt, from_a.id, to_a.id, discord_message_id
                )
            return (
                PersistTransferResult(
                    entry=pt.notes or "",
                    out_id=out_id,
                    in_id=in_id,
                    pair_id=pair_id,
                    amount_paise=pt.amount_paise,
                ),
                None,
            )
        if from_a and not to_a:
            shown = pick_accounts_for_display(accounts, pt.fragment_to, exclude={from_a.id})
            if not shown:
                return None, "No destination account available (need different from source)."
            return await self._send_transfer_pick(
                pt,
                discord_message_id,
                channel,
                user_id,
                pick_for="to",
                resolved_from_id=from_a.id,
                resolved_from_name=from_a.name,
                resolved_to_id=None,
                resolved_to_name=None,
                account_rows=shown,
            )
        if to_a and not from_a:
            shown = pick_accounts_for_display(accounts, pt.fragment_from, exclude={to_a.id})
            if not shown:
                return None, "No source account available."
            return await self._send_transfer_pick(
                pt,
                discord_message_id,
                channel,
                user_id,
                pick_for="from",
                resolved_from_id=None,
                resolved_from_name=None,
                resolved_to_id=to_a.id,
                resolved_to_name=to_a.name,
                account_rows=shown,
            )
        shown = pick_accounts_for_display(
            accounts,
            pt.fragment_from or pt.fragment_to,
            exclude=None,
        )
        if not shown:
            return None, "No accounts to pick from."
        return await self._send_transfer_pick(
            pt,
            discord_message_id,
            channel,
            user_id,
            pick_for="from",
            resolved_from_id=None,
            resolved_from_name=None,
            resolved_to_id=None,
            resolved_to_name=None,
            account_rows=shown,
        )

    async def _send_transfer_pick(
        self,
        pt: ParsedTransferLine,
        discord_message_id: str,
        channel: discord.abc.Messageable,
        user_id: int,
        *,
        pick_for: str,
        resolved_from_id: int | None,
        resolved_from_name: str | None,
        resolved_to_id: int | None,
        resolved_to_name: str | None,
        account_rows: list,
    ) -> tuple[None, None]:
        title = (
            "Which account is the transfer **from**?"
            if pick_for == "from"
            else "Which account is the transfer **to**?"
        )
        lines = "\n".join(
            f"{PICK_EMOJIS[i]} {a.name}" for i, a in enumerate(account_rows[:4])
        )
        lines += f"\n{PICK_EMOJIS[4]} Skip (cancel)"
        embed = discord.Embed(title=title, description=lines, color=0x9B59B6)
        embed.set_footer(text=f"Amount {_rupees(pt.amount_paise)} · reply with a reaction")
        msg = await channel.send(embed=embed)
        for e in PICK_EMOJIS:
            with contextlib.suppress(discord.HTTPException):
                await msg.add_reaction(e)
        ExpenseCog._pending_transfers[msg.id] = PendingTransfer(
            user_id=user_id,
            amount_paise=pt.amount_paise,
            tx_date=pt.transaction_date,
            notes=pt.notes,
            source_discord_message_id=discord_message_id,
            pick_for=pick_for,
            resolved_from_id=resolved_from_id,
            resolved_from_name=resolved_from_name,
            resolved_to_id=resolved_to_id,
            resolved_to_name=resolved_to_name,
            fragment_from=pt.fragment_from,
            fragment_to=pt.fragment_to,
            account_ids_shown=[a.id for a in account_rows[:4]],
        )
        return None, None

    def _make_log_embed(
        self,
        entry: str,
        parsed: ParsedExpense,
        tid: int,
        *,
        account_name: str | None = None,
    ) -> discord.Embed:
        embed = discord.Embed(title="Logged", description=f"**{entry}**", color=0x2ECC71)
        embed.add_field(name="Amount", value=_rupees(parsed.amount_paise), inline=True)
        embed.add_field(name="Category", value=parsed.category.value, inline=True)
        embed.add_field(name="Payment", value=parsed.payment_mode.value, inline=True)
        if account_name:
            embed.add_field(name="Account", value=account_name, inline=True)
        if parsed.merchant:
            embed.add_field(name="Merchant", value=parsed.merchant, inline=False)
        embed.set_footer(
            text=(
                f"id={tid} · React: {REACTION_DELETE} remove · "
                f"{REACTION_EDIT} edit hint"
            )
        )
        return embed

    def _make_transfer_embed(self, entry: str, r: PersistTransferResult) -> discord.Embed:
        embed = discord.Embed(title="Transfer logged", description=f"**{entry}**", color=0x9B59B6)
        embed.add_field(name="Amount", value=_rupees(r.amount_paise), inline=True)
        embed.add_field(name="Pair id", value=r.pair_id[:8] + "…", inline=True)
        embed.set_footer(
            text=(
                f"ids={r.out_id}+{r.in_id} · React: {REACTION_DELETE} remove both · "
                f"{REACTION_EDIT} edit hint"
            )
        )
        return embed

    async def _handle_transfer_reaction(
        self,
        payload: discord.RawReactionActionEvent,
        msg: discord.Message,
    ) -> bool:
        """Handle 1–5 reaction on an account picker. Returns True if this was a pending pick."""
        pending = ExpenseCog._pending_transfers.get(payload.message_id)
        if pending is None:
            return False
        if pending.user_id != payload.user_id:
            return True
        emoji_s = str(payload.emoji)
        if emoji_s not in PICK_EMOJIS:
            return True
        idx = PICK_EMOJIS.index(emoji_s)
        ExpenseCog._pending_transfers.pop(payload.message_id, None)
        ch = msg.channel
        if not isinstance(ch, discord.abc.Messageable):
            return True
        if idx == 4:
            with contextlib.suppress(discord.HTTPException):
                await msg.reply("Transfer cancelled.", mention_author=False)
            return True
        if idx >= len(pending.account_ids_shown):
            return True
        picked_id = pending.account_ids_shown[idx]
        async with open_db(self._settings.db_path) as conn:
            accounts = await accounts_repo.list_accounts(conn, active_only=True)
        acc_map = {a.id: a for a in accounts}
        picked = acc_map.get(picked_id)
        if picked is None:
            with contextlib.suppress(discord.HTTPException):
                await msg.reply("That account no longer exists.", mention_author=False)
            return True
        pt = ParsedTransferLine(
            amount_paise=pending.amount_paise,
            fragment_from=pending.fragment_from,
            fragment_to=pending.fragment_to,
            transaction_date=pending.tx_date,
            notes=pending.notes,
        )
        entry_text = pending.notes or ""
        if pending.pick_for == "from":
            from_id = picked.id
            likes = accounts_to_likes(accounts)
            to_m = match_account_fuzzy(pt.fragment_to, likes)
            if to_m and to_m.id != from_id:
                async with open_db(self._settings.db_path) as conn:
                    out_id, in_id, pair_id = await self._insert_transfer_pair_discord(
                        conn,
                        pt,
                        from_id,
                        to_m.id,
                        pending.source_discord_message_id or "",
                    )
                r = PersistTransferResult(
                    entry=entry_text,
                    out_id=out_id,
                    in_id=in_id,
                    pair_id=pair_id,
                    amount_paise=pt.amount_paise,
                )
                embed = self._make_transfer_embed(entry_text, r)
                with contextlib.suppress(discord.HTTPException):
                    reply = await msg.reply(embed=embed, mention_author=False)
                    await reply.add_reaction(REACTION_DELETE)
                    await reply.add_reaction(REACTION_EDIT)
                return True
            shown = pick_accounts_for_display(accounts, pt.fragment_to, exclude={from_id})
            if not shown:
                with contextlib.suppress(discord.HTTPException):
                    await msg.reply(
                        "Could not pick a destination account.",
                        mention_author=False,
                    )
                return True
            await self._send_transfer_pick(
                pt,
                pending.source_discord_message_id or "",
                ch,
                pending.user_id,
                pick_for="to",
                resolved_from_id=from_id,
                resolved_from_name=picked.name,
                resolved_to_id=None,
                resolved_to_name=None,
                account_rows=shown,
            )
            with contextlib.suppress(discord.HTTPException):
                await msg.reply(
                    "Pick the **to** account on the new message.",
                    mention_author=False,
                )
            return True
        to_id = picked.id
        from_id = pending.resolved_from_id
        if from_id is None:
            return True
        if from_id == to_id:
            with contextlib.suppress(discord.HTTPException):
                await msg.reply("From and to must be different accounts.", mention_author=False)
            return True
        async with open_db(self._settings.db_path) as conn:
            out_id, in_id, pair_id = await self._insert_transfer_pair_discord(
                conn,
                pt,
                from_id,
                to_id,
                pending.source_discord_message_id or "",
            )
        r = PersistTransferResult(
            entry=entry_text,
            out_id=out_id,
            in_id=in_id,
            pair_id=pair_id,
            amount_paise=pt.amount_paise,
        )
        embed = self._make_transfer_embed(entry_text, r)
        with contextlib.suppress(discord.HTTPException):
            reply = await msg.reply(embed=embed, mention_author=False)
            await reply.add_reaction(REACTION_DELETE)
            await reply.add_reaction(REACTION_EDIT)
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not self._allowed_user_id(message.author.id):
            return
        m = _LOG_LINE_RE.match(message.content or "")
        if not m:
            return
        entry = (m.group(1) or "").strip()
        if not entry:
            return
        try:
            result, err = await self._persist_log(
                entry, str(message.id), message.channel, message.author.id
            )
        except ExpenseParseError as e:
            with contextlib.suppress(discord.HTTPException):
                await message.reply(f"Could not parse: {e}", mention_author=False)
            return
        if err:
            with contextlib.suppress(discord.HTTPException):
                await message.reply(err, mention_author=False)
            return
        if result is None:
            return
        if isinstance(result, PersistTransferResult):
            embed = self._make_transfer_embed(entry, result)
        else:
            embed = self._make_log_embed(
                entry,
                result.parsed,
                result.tid,
                account_name=result.account_name,
            )
        try:
            reply = await message.reply(embed=embed, mention_author=False)
            await reply.add_reaction(REACTION_DELETE)
            await reply.add_reaction(REACTION_EDIT)
        except discord.HTTPException as e:
            logger.warning("plain-text log reply failed: {}", e)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        me = self.bot.user
        if me is None:
            return
        if payload.user_id == me.id:
            return
        if not self._allowed_user_id(payload.user_id):
            return
        emoji_s = str(payload.emoji)
        try:
            ch = self.bot.get_channel(payload.channel_id)
            if ch is None:
                ch = await self.bot.fetch_channel(payload.channel_id)
            if not isinstance(ch, discord.abc.Messageable):
                return
            msg = await ch.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logger.debug("reaction fetch failed: {}", e)
            return
        if payload.message_id in ExpenseCog._pending_transfers and emoji_s in PICK_EMOJIS:
            await self._handle_transfer_reaction(payload, msg)
            return
        if emoji_s not in (REACTION_EDIT, REACTION_DELETE):
            return
        if msg.author.id != me.id or not msg.embeds:
            return
        embed = msg.embeds[0]
        tid = _parse_tx_id_footer(embed.footer.text if embed.footer else None)
        if tid is None:
            return
        async with open_db(self._settings.db_path) as conn:
            row = await tx_repo.get_by_id(conn, tid)
            if row is None:
                return
            if row.source != "discord":
                return
            if emoji_s == REACTION_DELETE:
                ok = await tx_repo.soft_delete_by_id(conn, tid)
                with contextlib.suppress(discord.HTTPException):
                    if ok:
                        await msg.reply(
                            "That expense was removed (soft delete).",
                            mention_author=False,
                        )
                    else:
                        await msg.reply(
                            "Could not remove that expense (already gone?).",
                            mention_author=False,
                        )
                return
            if row.transaction_type == "transfer":
                with contextlib.suppress(discord.HTTPException):
                    await msg.reply(
                        "Transfers are not editable via /edit. Delete this receipt "
                        "(removes both legs) and log again.",
                        mention_author=False,
                    )
                return
            with contextlib.suppress(discord.HTTPException):
                await msg.reply(
                    f"To change this entry, use `/edit` with `transaction_id={tid}` "
                    f"and a new `entry` text (same format as `/log`).",
                    mention_author=False,
                )

    @app_commands.command(name="log", description="Log an expense in natural language")
    @app_commands.describe(
        entry=(
            "Expense, transfer, or template: `template Netflix 500` / `t rent` "
            "(create templates in dashboard)"
        ),
    )
    async def log_expense(self, interaction: discord.Interaction, entry: str) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return
        if interaction.channel is None or not isinstance(
            interaction.channel, discord.abc.Messageable
        ):
            await interaction.response.send_message("No channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            result, err = await self._persist_log(
                entry, str(interaction.id), interaction.channel, interaction.user.id
            )
        except ExpenseParseError as e:
            await interaction.followup.send(f"Could not parse: {e}", ephemeral=True)
            return
        if err:
            await interaction.followup.send(err, ephemeral=True)
            return
        if result is None:
            await interaction.followup.send(
                "Use reactions on the account picker message to finish the transfer.",
                ephemeral=True,
            )
            return
        if isinstance(result, PersistTransferResult):
            embed = self._make_transfer_embed(entry, result)
        else:
            embed = self._make_log_embed(
                entry,
                result.parsed,
                result.tid,
                account_name=result.account_name,
            )
        try:
            msg = await interaction.followup.send(embed=embed, wait=True)
            await msg.add_reaction(REACTION_DELETE)
            await msg.add_reaction(REACTION_EDIT)
        except discord.HTTPException as e:
            logger.warning("Could not add confirmation reactions: {}", e)

    @app_commands.command(name="edit", description="Edit a Discord-logged transaction by id")
    @app_commands.describe(
        transaction_id="Footer id= on the /log receipt",
        entry="New natural-language expense line",
    )
    async def edit_expense(
        self,
        interaction: discord.Interaction,
        transaction_id: int,
        entry: str,
    ) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return
        try:
            parsed = parse_expense_line(entry)
        except ExpenseParseError as e:
            await interaction.response.send_message(f"Could not parse: {e}", ephemeral=True)
            return
        async with open_db(self._settings.db_path) as conn:
            row = await tx_repo.get_by_id(conn, transaction_id)
            if row is None:
                await interaction.response.send_message("Transaction not found.", ephemeral=True)
                return
            if row.source != "discord":
                await interaction.response.send_message(
                    "Only Discord-logged rows can be edited here.",
                    ephemeral=True,
                )
                return
            if row.transaction_type == "transfer":
                await interaction.response.send_message(
                    "Transfers cannot be edited via /edit; delete the receipt and log again.",
                    ephemeral=True,
                )
                return
            ok = await tx_repo.update_transaction_fields(
                conn,
                transaction_id,
                tx_date=parsed.transaction_date,
                amount_paise=parsed.amount_paise,
                category=parsed.category.value,
                merchant=parsed.merchant,
                payment_mode=parsed.payment_mode.value,
                notes=parsed.notes,
                source_must_be="discord",
            )
        if not ok:
            await interaction.response.send_message("Update failed.", ephemeral=True)
            return
        embed = discord.Embed(title="Updated", description=f"**{entry}**", color=0x3498DB)
        embed.add_field(name="Amount", value=_rupees(parsed.amount_paise), inline=True)
        embed.add_field(name="Category", value=parsed.category.value, inline=True)
        embed.set_footer(text=f"id={transaction_id}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="balance", description="Spending summary (today / week / month)")
    async def balance(self, interaction: discord.Interaction) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return
        d = date.today()
        async with open_db(self._settings.db_path) as conn:
            today = await tx_repo.sum_between(conn, start=d, end=d)
            w0 = d - timedelta(days=d.weekday())
            w1 = w0 + timedelta(days=6)
            week = await tx_repo.sum_between(conn, start=w0, end=w1)
            last = calendar.monthrange(d.year, d.month)[1]
            m0 = date(d.year, d.month, 1)
            m1 = date(d.year, d.month, last)
            month = await tx_repo.sum_between(conn, start=m0, end=m1)

        msg = (
            f"Today: {_rupees(today)}\n"
            f"This week: {_rupees(week)}\n"
            f"This month: {_rupees(month)}"
        )
        await interaction.response.send_message(msg)

    @app_commands.command(name="undo", description="Soft-delete your last Discord-logged expense")
    async def undo(self, interaction: discord.Interaction) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return
        async with open_db(self._settings.db_path) as conn:
            tid = await tx_repo.soft_delete_last(conn, source="discord")
        if tid is None:
            await interaction.response.send_message("Nothing to undo.")
        else:
            await interaction.response.send_message(
                f"Removed transaction **#{tid}** (soft delete)."
            )

    @app_commands.command(name="budget", description="FY budget caps (from settings)")
    async def budget_cmd(self, interaction: discord.Interaction) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return
        async with open_db(self._settings.db_path) as conn:
            fy = await settings_repo.get_current_fy(conn)
            rows = await budget_repo.effective_budgets_for_fy(conn, str(fy))
        if not rows:
            await interaction.response.send_message(f"FY **{fy}**: no budgets set yet.")
            return
        lines = [f"**FY {fy}** — monthly caps"]
        for r in rows[:25]:
            lines.append(f"· {r.category}: {_rupees(r.monthly_amount_paise)}/mo")
        if len(rows) > 25:
            lines.append(f"… +{len(rows) - 25} more (see dashboard)")
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="debt", description="Active debt summary")
    async def debt_cmd(self, interaction: discord.Interaction) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return
        async with open_db(self._settings.db_path) as conn:
            tot, emi, n = await debt_repo.aggregate_active(conn)
            rows = await debt_repo.list_debts(conn)
        active = [r for r in rows if r.status == "active"]
        lines = [
            f"**Debt** — {n} active loan(s)",
            f"Outstanding: {_rupees(tot)}",
            f"Combined EMI (est.): {_rupees(emi)}",
        ]
        for r in active[:12]:
            rate = f"{r.rate_percent:.2f}%" if r.rate_percent is not None else "—"
            lines.append(f"· **{r.name}** — {_rupees(r.current_balance_paise)} @ {rate}")
        if len(active) > 12:
            lines.append(f"… +{len(active) - 12} more")
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="goal", description="List savings goals")
    async def goal_cmd(self, interaction: discord.Interaction) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return
        async with open_db(self._settings.db_path) as conn:
            goals = await goals_repo.list_goals(conn)
        if not goals:
            await interaction.response.send_message("No goals yet.")
            return
        lines = ["**Goals**"]
        for g in goals[:20]:
            pct = (
                (g.current_amount_paise / g.target_amount_paise * 100)
                if g.target_amount_paise > 0
                else 0
            )
            lines.append(
                f"· **{g.name}** — {_rupees(g.current_amount_paise)} / "
                f"{_rupees(g.target_amount_paise)} ({pct:.0f}%)"
            )
        if len(goals) > 20:
            lines.append(f"… +{len(goals) - 20} more")
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="net-worth", description="Latest net worth snapshot (if recorded)")
    async def net_worth_cmd(self, interaction: discord.Interaction) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return
        async with open_db(self._settings.db_path) as conn:
            hist = await nw_repo.list_history(conn, limit=1)
        if not hist:
            await interaction.response.send_message(
                "No snapshots yet. Record one from the dashboard (Net worth) or API."
            )
            return
        snap = hist[-1]
        await interaction.response.send_message(
            f"**{snap.snapshot_date}** — Net: {_rupees(snap.net_worth_paise)} "
            f"(assets {_rupees(snap.total_assets_paise)}, "
            f"liabilities {_rupees(snap.total_liabilities_paise)})"
        )

    @app_commands.command(name="report", description="FY spending vs income run-rate (current FY)")
    async def report_cmd(self, interaction: discord.Interaction) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return
        async with open_db(self._settings.db_path) as conn:
            fy = await settings_repo.get_current_fy(conn)
            fy_s, spent, run_rate, implied = await build_fy_summary(conn, fy)
        await interaction.response.send_message(
            f"**FY {fy_s}**\n"
            f"Spent (FY to date): {_rupees(spent)}\n"
            f"Income run-rate ×12: {_rupees(run_rate)}\n"
            f"Implied balance: {_rupees(implied)}"
        )

    @app_commands.command(name="finance_help", description="Show Finance OS commands")
    async def finance_help(self, interaction: discord.Interaction) -> None:
        text = (
            "**Personal Finance OS**\n"
            "`/log` — natural language expense, transfer, or **template**\n"
            "Examples: `500 swiggy using hdfc savings` · `transfer 5000 to hdfc` · "
            "`10000 from sbi to icici`\n"
            "**Templates:** `template <name>` or `t <name>` — optional amount/date after the name "
            "(dashboard → Transactions → Templates)\n"
            "Or send a message starting with `log ` (same text you’d put in `/log`)\n"
            "`/edit` — rewrite a Discord-logged row (use `transaction_id` from receipt)\n"
            "`/balance` — today / week / month totals\n"
            "`/undo` — soft-delete last Discord expense\n"
            "`/budget` — FY budget caps\n"
            "`/debt` — debt summary\n"
            "`/goal` — savings goals\n"
            "`/net-worth` — latest snapshot\n"
            "`/report` — FY spend vs income run-rate\n"
            "Reactions on `/log` receipts: ❌ remove · 🔄 edit hint\n"
            "API: http://127.0.0.1:8000/docs"
        )
        await interaction.response.send_message(text)
