import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Literal, Optional

from database.models import UserModel, GoldenTicketModel, RaffleDrawModel
from database.bot_config import BotConfigModel, VALID_CHANNEL_TYPES
from utils.logger import get_logger
from utils.helpers import (
    has_admin_role,
    send_error_embed,
    send_success_embed,
    format_points,
    get_tier_role_mention,
    challenge_status,
)
from config.constants import (
    BRAND_COLOR,
    MASTER_BONUS_MULTIPLIER,
    MASTER_ROLE_NAME,
    SCALER_ROLE_NAME,
    CURRENT_SEASON,
    TIERS,
    POINTS,
    OFFICIAL_FINISHER_WEEKS_RATIO,
    OFFICIAL_FINISHER_POINTS_RATIO,
    RAFFLE_TICKETS,
    GOLDEN_TICKET_NEXT_N_DEFAULT,
    GOLDEN_TICKET_STREAK_DAYS,
)
from config.settings import MAX_REFERRALS
from cogs.season_group import season_group, golden_ticket_group

logger = get_logger(__name__)


async def _require_admin(interaction: discord.Interaction) -> bool:
    """Returns True if allowed; sends the denial message and returns False
    otherwise. These commands live on a shared Group rather than as methods of
    the Admin cog, so there's no cog-level interaction_check to rely on."""
    if not await has_admin_role(interaction):
        await send_error_embed(
            interaction, "❌ You don't have permission to use admin commands."
        )
        return False
    return True


class Admin(commands.Cog):
    """Admin prefix commands (slash commands for this cog live under season_group)"""

    def __init__(self, bot):
        self.bot = bot
        logger.info("Admin cog loaded")

    @commands.command(name="sync")
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx: commands.Context):
        """[ADMIN] Register/sync all slash commands to this server"""
        try:
            await ctx.message.add_reaction("⏳")
        except discord.HTTPException:
            pass

        try:
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            logger.info(
                f"✅ {ctx.author.name} synced {len(synced)} commands to guild {ctx.guild.id}"
            )
            await ctx.send(f"✅ Synced {len(synced)} command(s) to **{ctx.guild.name}**.")
            await self._swap_reaction(ctx, "⏳", "✅")
        except Exception as e:
            logger.error(f"❌ Error in sync command: {e}")
            await ctx.send("❌ An error occurred while syncing commands.")
            await self._swap_reaction(ctx, "⏳", "❌")

    async def _swap_reaction(self, ctx: commands.Context, old: str, new: str):
        """Remove the bot's own `old` reaction and add `new` - best-effort, never fails the command"""
        try:
            await ctx.message.remove_reaction(old, self.bot.user)
        except discord.HTTPException:
            pass
        try:
            await ctx.message.add_reaction(new)
        except discord.HTTPException:
            pass

    @sync.error
    async def sync_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
        else:
            logger.error(f"❌ Error in sync command: {error}")
            await ctx.send("❌ An error occurred while syncing commands.")


# ----------------------------------------------------------------------
# Points administration
# ----------------------------------------------------------------------


@season_group.command(name="addpoints", description="[ADMIN] Add points to a user")
@app_commands.describe(
    user="The user to add points to",
    points="Number of points to add",
    reason="Reason for adding points",
    is_win="Mark this as a win award (applies the Masters +15% bonus if the user has it)",
)
async def add_points(
    interaction: discord.Interaction,
    user: discord.Member,
    points: int,
    reason: str,
    is_win: Optional[bool] = False,
):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        if points <= 0:
            await send_error_embed(interaction, "❌ Points must be greater than 0.")
            return

        user_data = await UserModel.get_or_create(user.id, user.name)

        awarded_points = points
        bonus_applied = False
        if is_win and user_data.get("is_master"):
            awarded_points = round(points * MASTER_BONUS_MULTIPLIER)
            bonus_applied = True

        updated_user = await UserModel.update_points(
            user.id, awarded_points, reason, bot=interaction.client, category="performance"
        )

        tier_role = get_tier_role_mention(updated_user["tier"], interaction.guild)

        logger.info(
            f"✅ {interaction.user.name} added {awarded_points} points to {user.name}: {reason}"
            f"{' (master bonus applied)' if bonus_applied else ''}"
        )

        bonus_note = (
            f"\n🥋 **Masters bonus applied:** {points} → {awarded_points}"
            if bonus_applied
            else ""
        )

        await send_success_embed(
            interaction,
            f"✅ Added **{format_points(awarded_points)}** points to {user.mention}{bonus_note}\n\n"
            f"**Reason:** {reason}\n"
            f"**New Total:** {updated_user['total_points']} points\n"
            f"**Tier:** {tier_role}\n"
            f"🎖️ Discord role updated automatically!",
        )

    except Exception as e:
        logger.error(f"❌ Error in add_points command: {e}")
        await send_error_embed(interaction, "❌ An error occurred while adding points.")


@season_group.command(
    name="removepoints", description="[ADMIN] Remove points from a user"
)
@app_commands.describe(
    user="The user to remove points from",
    points="Number of points to remove",
    reason="Reason for removing points",
)
async def remove_points(
    interaction: discord.Interaction,
    user: discord.Member,
    points: int,
    reason: str,
):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        if points <= 0:
            await send_error_embed(interaction, "❌ Points must be greater than 0.")
            return

        user_data = await UserModel.get_or_create(user.id, user.name)

        if user_data["total_points"] < points:
            await send_error_embed(
                interaction,
                f"❌ {user.mention} only has {user_data['total_points']} points. Cannot remove {points}.",
            )
            return

        updated_user = await UserModel.update_points(
            user.id, -points, reason, bot=interaction.client, category="performance"
        )

        tier_role = get_tier_role_mention(updated_user["tier"], interaction.guild)

        logger.info(
            f"✅ {interaction.user.name} removed {points} points from {user.name}: {reason}"
        )

        await send_success_embed(
            interaction,
            f"✅ Removed **{points}** points from {user.mention}\n\n"
            f"**Reason:** {reason}\n"
            f"**New Total:** {updated_user['total_points']} points\n"
            f"**Tier:** {tier_role}\n"
            f"🎖️ Discord role updated automatically!",
        )

    except Exception as e:
        logger.error(f"❌ Error in remove_points command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while removing points."
        )


@season_group.command(
    name="addreferral",
    description="[ADMIN] Award referral points (Whop +10 each, Discord +5 each, capped)",
)
@app_commands.describe(
    user="The user to credit",
    referral_type="Whop or Discord referral",
    count="How many referrals to add",
)
async def add_referral(
    interaction: discord.Interaction,
    user: discord.Member,
    referral_type: Literal["whop", "discord"],
    count: int,
):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        if count <= 0:
            await send_error_embed(interaction, "❌ Count must be greater than 0.")
            return

        user_data = await UserModel.get_or_create(user.id, user.name)
        current_count = user_data.get("referral_count", 0)

        remaining = MAX_REFERRALS - current_count
        if remaining <= 0:
            await send_error_embed(
                interaction,
                f"❌ {user.mention} has already reached the max of {MAX_REFERRALS} referrals.",
            )
            return

        awarded_count = min(count, remaining)
        points_per_referral = (
            POINTS["WHOP_REFERRAL"] if referral_type == "whop" else POINTS["DISCORD_REFERRAL"]
        )
        total_points = awarded_count * points_per_referral

        updated_user = await UserModel.add_referrals(
            user.id,
            awarded_count,
            total_points,
            f"{referral_type.title()} referral x{awarded_count}",
            bot=interaction.client,
        )

        logger.info(
            f"✅ {interaction.user.name} added {awarded_count} {referral_type} referrals "
            f"(+{total_points} points) to {user.name}"
        )

        capped_note = (
            f"\n⚠️ Capped at {MAX_REFERRALS} total — only {awarded_count} of {count} counted."
            if awarded_count < count
            else ""
        )

        await send_success_embed(
            interaction,
            f"✅ Added **{awarded_count}** {referral_type.title()} referral(s) "
            f"(+{total_points} points) to {user.mention}{capped_note}\n"
            f"**Total referrals:** {updated_user['referral_count']}/{MAX_REFERRALS}",
        )
    except Exception as e:
        logger.error(f"❌ Error in add_referral command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while adding referrals."
        )


@season_group.command(name="viewuser", description="[ADMIN] View detailed user stats")
@app_commands.describe(user="The user to view")
async def view_user(interaction: discord.Interaction, user: discord.Member):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        from database.supabase_client import get_supabase
        from utils.embeds import create_user_stats_embed
        from config.constants import CURRENT_SEASON

        user_data = await UserModel.get_or_create(user.id, user.name)
        embed = create_user_stats_embed(
            user_data, discord_user=user, guild=interaction.guild
        )

        supabase = get_supabase()
        history_response = (
            (await asyncio.to_thread(supabase.table("points_history")
            .select("*")
            .eq("user_id", user.id)
            .eq("season", CURRENT_SEASON)
            .order("created_at", desc=True)
            .limit(5).execute))
        )

        if history_response.data:
            history_text = ""
            for entry in history_response.data:
                points = format_points(entry["points_change"])
                history_text += f"{points} - {entry['reason']}\n"

            embed.add_field(
                name="📜 Recent Points History",
                value=history_text[:1024],
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Error in view_user command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while viewing user stats."
        )


# ----------------------------------------------------------------------
# Channel configuration
# ----------------------------------------------------------------------


@season_group.command(
    name="setchannel", description="[ADMIN] Register a channel for the bot to use"
)
@app_commands.describe(
    channel_type="Which channel role this is for",
    channel="The channel to register",
)
async def set_channel(
    interaction: discord.Interaction,
    channel_type: Literal[tuple(VALID_CHANNEL_TYPES)],
    channel: discord.TextChannel,
):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        await BotConfigModel.set_channel_id(
            channel_type, channel.id, updated_by=interaction.user.id
        )

        logger.info(
            f"✅ {interaction.user.name} set channel.{channel_type} = "
            f"#{channel.name} ({channel.id})"
        )

        await send_success_embed(
            interaction, f"✅ **{channel_type}** channel set to {channel.mention}"
        )
    except Exception as e:
        logger.error(f"❌ Error in set_channel command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while setting the channel."
        )


@season_group.command(
    name="listchannels", description="[ADMIN] Show currently configured channels"
)
async def list_channels(interaction: discord.Interaction):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        lines = []
        for channel_type in VALID_CHANNEL_TYPES:
            channel_id = BotConfigModel.get_channel_id(channel_type)
            mention = f"<#{channel_id}>" if channel_id else "*not set*"
            lines.append(f"**{channel_type}**: {mention}")

        embed = discord.Embed(
            title="📋 Configured Channels",
            description="\n".join(lines),
            color=BRAND_COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error(f"❌ Error in list_channels command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while listing channels."
        )


# ----------------------------------------------------------------------
# Tier point thresholds
# ----------------------------------------------------------------------

_TIER_DISPLAY_TO_KEY = {
    "Challenger": "OBSERVER",
    "Builder": "BUILDER",
    "Operator": "OPERATOR",
    "Elite": "ELITE",
}


@season_group.command(
    name="settierpoints",
    description="[ADMIN] Set the minimum points required for a tier role",
)
@app_commands.describe(tier="Which tier role", min_points="Minimum points required")
async def set_tier_points(
    interaction: discord.Interaction,
    tier: Literal["Challenger", "Builder", "Operator", "Elite"],
    min_points: int,
):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        if min_points < 0:
            await send_error_embed(interaction, "❌ Points must be 0 or greater.")
            return

        tier_key = _TIER_DISPLAY_TO_KEY[tier]
        await BotConfigModel.set_tier_threshold(
            tier_key, min_points, updated_by=interaction.user.id
        )

        logger.info(
            f"✅ {interaction.user.name} set {tier} tier threshold to {min_points} points"
        )

        await send_success_embed(
            interaction, f"✅ **{tier}** now requires **{min_points}+** points."
        )
    except Exception as e:
        logger.error(f"❌ Error in set_tier_points command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while setting tier points."
        )


# ----------------------------------------------------------------------
# Weekly Victory / Official Finisher thresholds
# ----------------------------------------------------------------------


@season_group.command(
    name="setweeklyvictorythreshold",
    description="[ADMIN] Override the points needed to win a week (default: auto-computed 51%)",
)
@app_commands.describe(points="Points needed to win a week")
async def set_weekly_victory_threshold(interaction: discord.Interaction, points: int):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        if points < 1:
            await send_error_embed(interaction, "❌ Points must be 1 or greater.")
            return

        await BotConfigModel.set_weekly_victory_threshold(
            points, updated_by=interaction.user.id
        )

        logger.info(
            f"✅ {interaction.user.name} set Weekly Victory threshold to {points} points"
        )

        await send_success_embed(
            interaction,
            f"✅ Weekly Victory threshold set to **{points}** points. "
            f"Already-finalized weeks are unaffected - this only applies going forward.",
        )
    except Exception as e:
        logger.error(f"❌ Error in set_weekly_victory_threshold command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while setting the Weekly Victory threshold."
        )


@season_group.command(
    name="setfinisherpoints",
    description="[ADMIN] Override the total-points path to Official Finisher (default: auto ~82.5%)",
)
@app_commands.describe(points="Total season points needed to qualify as an Official Finisher")
async def set_finisher_points(interaction: discord.Interaction, points: int):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        if points < 1:
            await send_error_embed(interaction, "❌ Points must be 1 or greater.")
            return

        await BotConfigModel.set_official_finisher_points_threshold(
            points, updated_by=interaction.user.id
        )

        logger.info(
            f"✅ {interaction.user.name} set Official Finisher points threshold to {points}"
        )

        await send_success_embed(
            interaction,
            f"✅ Official Finisher points threshold pinned to **{points}** "
            f"(overriding the auto-computed default). Members now qualify by winning "
            f"{int(OFFICIAL_FINISHER_WEEKS_RATIO * 100)}% of weeks **or** reaching this total.",
        )
    except Exception as e:
        logger.error(f"❌ Error in set_finisher_points command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while setting the finisher points threshold."
        )


# ----------------------------------------------------------------------
# Golden Ticket events - all moderator-triggered ("no warning, no
# schedule" per the doc). Nothing here fires on its own.
# ----------------------------------------------------------------------


@golden_ticket_group.command(
    name="day",
    description="[ADMIN] Flag THIS week as a Golden Ticket Day - its eventual winners get a bonus",
)
async def golden_ticket_day(interaction: discord.Interaction):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        week_number = await GoldenTicketModel.flag_golden_ticket_day(
            updated_by=interaction.user.id
        )

        if week_number is None:
            await send_error_embed(
                interaction,
                "❌ There's no active challenge week right now (dates not set, or the "
                "challenge hasn't started/has ended).",
            )
            return

        logger.info(f"🎉 {interaction.user.name} flagged Week {week_number} as Golden Ticket Day")

        await send_success_embed(
            interaction,
            f"🎉 **Week {week_number}** is now a Golden Ticket Day! Anyone who wins this week "
            f"gets **+{RAFFLE_TICKETS['GOLDEN_TICKET_DAY']}** bonus tickets on top of the normal "
            f"Win the Week reward, applied automatically once the week finalizes.",
        )
    except Exception as e:
        logger.error(f"❌ Error in golden_ticket_day command: {e}")
        await send_error_embed(interaction, "❌ An error occurred while flagging the Golden Ticket Day.")


@golden_ticket_group.command(
    name="next25",
    description="[ADMIN] Arm a bonus for the next N people to complete today's habits (doc default: 25)",
)
@app_commands.describe(count=f"How many people get the bonus (default {GOLDEN_TICKET_NEXT_N_DEFAULT})")
async def golden_ticket_next_n(interaction: discord.Interaction, count: Optional[int] = None):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        count = count or GOLDEN_TICKET_NEXT_N_DEFAULT
        if count < 1:
            await send_error_embed(interaction, "❌ Count must be 1 or greater.")
            return

        await GoldenTicketModel.arm_next_n(count, updated_by=interaction.user.id)

        logger.info(f"🎉 {interaction.user.name} armed Golden Ticket Next {count}")

        await send_success_embed(
            interaction,
            f"🎉 Armed! The next **{count}** people to complete today's habits each get "
            f"**+{RAFFLE_TICKETS['GOLDEN_TICKET_NEXT_N']}** bonus tickets, awarded automatically "
            f"in real time as they qualify.",
        )
    except Exception as e:
        logger.error(f"❌ Error in golden_ticket_next_n command: {e}")
        await send_error_embed(interaction, "❌ An error occurred while arming the bonus.")


@golden_ticket_group.command(
    name="streak",
    description=f"[ADMIN] Immediately grant a bonus to everyone on a {GOLDEN_TICKET_STREAK_DAYS}+ day streak",
)
async def golden_ticket_streak(interaction: discord.Interaction):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        awarded = await GoldenTicketModel.award_streak_bonus()

        logger.info(
            f"🎉 {interaction.user.name} triggered the streak Golden Ticket - {len(awarded)} awarded"
        )

        await send_success_embed(
            interaction,
            f"🎉 **{len(awarded)}** member(s) on a {GOLDEN_TICKET_STREAK_DAYS}+ day streak each "
            f"received **+{RAFFLE_TICKETS['GOLDEN_TICKET_STREAK']}** bonus tickets.",
        )
    except Exception as e:
        logger.error(f"❌ Error in golden_ticket_streak command: {e}")
        await send_error_embed(interaction, "❌ An error occurred while awarding the streak bonus.")


@golden_ticket_group.command(
    name="allhabits",
    description="[ADMIN] Immediately grant a bonus to everyone who's completed every habit today",
)
async def golden_ticket_all_habits(interaction: discord.Interaction):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        awarded = await GoldenTicketModel.award_all_habits_bonus()

        logger.info(
            f"🎉 {interaction.user.name} triggered the all-habits Golden Ticket - "
            f"{len(awarded)} awarded"
        )

        await send_success_embed(
            interaction,
            f"🎉 **{len(awarded)}** member(s) who completed every habit today each received "
            f"**+{RAFFLE_TICKETS['GOLDEN_TICKET_ALL_HABITS']}** bonus tickets.",
        )
    except Exception as e:
        logger.error(f"❌ Error in golden_ticket_all_habits command: {e}")
        await send_error_embed(interaction, "❌ An error occurred while awarding the bonus.")


# ----------------------------------------------------------------------
# Masters bonus role + role binding (Masters/Scalers -> actual Discord role)
# ----------------------------------------------------------------------


@season_group.command(
    name="setmaster",
    description="[ADMIN] Grant or revoke the Masters bonus role (Whop masterclass buyers)",
)
@app_commands.describe(user="The user to update", enabled="True to grant, False to revoke")
async def set_master(interaction: discord.Interaction, user: discord.Member, enabled: bool):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        await UserModel.get_or_create(user.id, user.name)
        await UserModel.set_master(user.id, enabled, bot=interaction.client)

        logger.info(
            f"✅ {interaction.user.name} set Masters role for {user.name} to {enabled}"
        )

        action = "granted to" if enabled else "revoked from"
        bonus_pct = int(round((MASTER_BONUS_MULTIPLIER - 1) * 100))
        await send_success_embed(
            interaction,
            f"✅ Masters bonus (+{bonus_pct}% on wins & value drops) {action} {user.mention}",
        )
    except Exception as e:
        logger.error(f"❌ Error in set_master command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while updating Masters status."
        )


@season_group.command(
    name="setrole",
    description="[ADMIN] Set which Discord role to use for Masters or Scalers",
)
@app_commands.describe(
    role_type="Which role this is for", role="The Discord role to bind"
)
async def set_role(
    interaction: discord.Interaction,
    role_type: Literal["masters", "scalers"],
    role: discord.Role,
):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        await BotConfigModel.set_role_id(
            role_type, role.id, updated_by=interaction.user.id
        )

        logger.info(
            f"✅ {interaction.user.name} bound role_type '{role_type}' to "
            f"role {role.name} ({role.id})"
        )

        await send_success_embed(
            interaction, f"✅ **{role_type}** role set to {role.mention}"
        )
    except Exception as e:
        logger.error(f"❌ Error in set_role command: {e}")
        await send_error_embed(interaction, "❌ An error occurred while setting the role.")


# ----------------------------------------------------------------------
# Challenge window (start/end date + timezone)
# ----------------------------------------------------------------------


@season_group.command(
    name="setchallengedates",
    description="[ADMIN] Set the challenge start/end dates and timezone",
)
@app_commands.describe(
    start_date="Start date (YYYY-MM-DD)",
    end_date="End date (YYYY-MM-DD)",
    timezone="Timezone the dates are in",
)
async def set_challenge_dates(
    interaction: discord.Interaction,
    start_date: str,
    end_date: str,
    timezone: Literal[
        "US/Eastern", "US/Central", "US/Mountain", "US/Pacific", "UTC"
    ] = "US/Eastern",
):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            await send_error_embed(interaction, "❌ Dates must be in YYYY-MM-DD format.")
            return

        await BotConfigModel.set_challenge_dates(
            start_date, end_date, timezone, updated_by=interaction.user.id
        )

        logger.info(
            f"✅ {interaction.user.name} set challenge dates: "
            f"{start_date} -> {end_date} ({timezone})"
        )

        await send_success_embed(
            interaction,
            f"✅ Challenge window set: **{start_date}** to **{end_date}** ({timezone})",
        )
    except Exception as e:
        logger.error(f"❌ Error in set_challenge_dates command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while setting challenge dates."
        )


# ----------------------------------------------------------------------
# Full configuration overview
# ----------------------------------------------------------------------


@season_group.command(
    name="config",
    description="[ADMIN] Show all current configuration - channels, roles, dates, tiers",
)
async def show_config(interaction: discord.Interaction):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title=f"⚙️ {CURRENT_SEASON} Configuration", color=BRAND_COLOR
        )

        # Channels
        channel_lines = [
            f"**{channel_type}**: "
            + (
                f"<#{BotConfigModel.get_channel_id(channel_type)}>"
                if BotConfigModel.get_channel_id(channel_type)
                else "*not set*"
            )
            for channel_type in VALID_CHANNEL_TYPES
        ]
        embed.add_field(name="📋 Channels", value="\n".join(channel_lines), inline=False)

        # Challenge window - no start date set is just treated as "not started yet"
        status_labels = {
            "not_started": "🔜 Not started yet",
            "active": "✅ Active",
            "ended": "🏁 Ended",
        }
        window = BotConfigModel.get_challenge_window()
        status = challenge_status()
        if window:
            start_raw, end_raw, timezone_name = window
            window_text = f"{start_raw} → {end_raw} ({timezone_name})\n{status_labels[status]}"
        else:
            window_text = f"No dates set yet (`/{CURRENT_SEASON.lower()} setchallengedates`)\n{status_labels[status]}"
        embed.add_field(name="📅 Challenge Window", value=window_text, inline=False)

        # Weekly Victory / Official Finisher thresholds
        finisher_points_override = BotConfigModel.get_official_finisher_points_threshold()
        if finisher_points_override:
            finisher_points_text = f"{finisher_points_override}+ total points (admin-pinned)"
        else:
            highest = await UserModel.get_highest_total_points()
            auto_points = round(highest * OFFICIAL_FINISHER_POINTS_RATIO)
            finisher_points_text = (
                f"{auto_points}+ total points (auto: {int(OFFICIAL_FINISHER_POINTS_RATIO * 100)}% "
                f"of current leader's {highest})"
            )
        weekly_victory_text = (
            f"**Weekly Victory:** {BotConfigModel.get_weekly_victory_threshold()}+ points/week\n"
            f"**Official Finisher:** win {int(OFFICIAL_FINISHER_WEEKS_RATIO * 100)}% of weeks "
            f"**or** reach {finisher_points_text}"
        )
        embed.add_field(
            name="🏁 Weekly Victory", value=weekly_victory_text, inline=False
        )

        # Tier thresholds - resolve the actual bound Discord role, not just the name
        thresholds = BotConfigModel.get_tier_thresholds()
        tier_lines = []
        for tier_name, tier_data in TIERS.items():
            min_points = thresholds.get(tier_name, tier_data["min"])
            role = (
                discord.utils.get(interaction.guild.roles, name=tier_data["role_name"])
                if interaction.guild
                else None
            )
            role_display = (
                role.mention
                if role
                else f"⚠️ *\"{tier_data['role_name']}\" not created in this server yet*"
            )
            tier_lines.append(f"{tier_data['emoji']} {role_display}: {min_points}+ points")
        embed.add_field(name="🎖️ Tiers", value="\n".join(tier_lines), inline=False)

        # Masters / Scalers - resolve the actual bound Discord role
        role_lines = []
        for role_type, fallback_name in (
            ("masters", MASTER_ROLE_NAME),
            ("scalers", SCALER_ROLE_NAME),
        ):
            role_id = BotConfigModel.get_role_id(role_type)
            role = None
            bound_explicitly = False

            if role_id and interaction.guild:
                role = interaction.guild.get_role(role_id)
                bound_explicitly = True
            elif interaction.guild:
                role = discord.utils.get(interaction.guild.roles, name=fallback_name)

            if role:
                note = "" if bound_explicitly else " *(matched by name, not explicitly bound)*"
                role_lines.append(f"**{role_type}**: {role.mention}{note}")
            elif role_id:
                role_lines.append(
                    f"**{role_type}**: ⚠️ *bound role ID no longer exists in this server*"
                )
            else:
                role_lines.append(
                    f"**{role_type}**: ⚠️ *not found - run `/{CURRENT_SEASON.lower()} setrole` "
                    f"or create a role named \"{fallback_name}\"*"
                )
        embed.add_field(name="🥋 Special Roles", value="\n".join(role_lines), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Error in show_config command: {e}")
        await send_error_embed(
            interaction, "❌ An error occurred while showing configuration."
        )


# ----------------------------------------------------------------------
# Championship Raffle draw - the actual Prize Pool drawing (separate from
# ticket earning, which happens automatically all season). One-time,
# high-stakes, so it's confirm-gated and refuses to re-draw a season.
# ----------------------------------------------------------------------


@season_group.command(
    name="raffledraw",
    description="[ADMIN] Run the Championship Raffle Prize Pool draw - ONE TIME ONLY per season",
)
@app_commands.describe(
    confirm="Must be True to actually run the draw - this cannot be undone or re-run"
)
async def raffle_draw(interaction: discord.Interaction, confirm: bool):
    if not await _require_admin(interaction):
        return
    try:
        await interaction.response.defer(ephemeral=True)

        if not confirm:
            await send_error_embed(
                interaction,
                "❌ Set `confirm:True` to actually run the draw. This picks real winners "
                "for real prizes and cannot be undone or re-run once it's done.",
            )
            return

        if await RaffleDrawModel.has_been_drawn():
            await send_error_embed(
                interaction,
                f"❌ The {CURRENT_SEASON} raffle has already been drawn. "
                f"Check `/{CURRENT_SEASON.lower()} rafflewinners` for the results.",
            )
            return

        results = await RaffleDrawModel.run_draw(bot=interaction.client)
        total_winners = sum(len(w) for w in results.values())

        logger.info(f"🎟️ {interaction.user.name} ran the Championship Raffle draw")

        await send_success_embed(
            interaction,
            f"🎉 Draw complete — **{total_winners}** total winners across "
            f"{len(results)} tiers. Results posted to the announcements channel "
            f"and viewable anytime via `/{CURRENT_SEASON.lower()} rafflewinners`.",
        )
    except ValueError as e:
        await send_error_embed(interaction, f"❌ {e}")
    except Exception as e:
        logger.error(f"❌ Error in raffle_draw command: {e}")
        await send_error_embed(interaction, "❌ An error occurred while running the raffle draw.")


async def setup(bot):
    await bot.add_cog(Admin(bot))
