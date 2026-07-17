from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
import discord
from config.constants import BRAND_COLOR


def _resolve_challenge_window():
    """Returns (start, end, now) as tz-aware datetimes from the DB-backed
    window set via /<season> setchallengedates, or None if never configured.
    No .env fallback - dates are command-only, never hardcoded."""
    from database.bot_config import BotConfigModel

    window = BotConfigModel.get_challenge_window()
    if not window:
        return None

    start_raw, end_raw, timezone_name = window
    tz = ZoneInfo(timezone_name)
    start = datetime.strptime(start_raw, "%Y-%m-%d").replace(tzinfo=tz)
    end = datetime.strptime(end_raw, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=tz
    )
    return start, end, datetime.now(tz)


def is_challenge_active() -> bool:
    """Check if challenge is currently active, per the window set via
    /<season> setchallengedates."""
    window = _resolve_challenge_window()
    if not window:
        return False
    start, end, now = window
    return start <= now <= end


def challenge_status() -> str:
    """Returns 'not_started', 'active', or 'ended' - lets commands (e.g. the
    leaderboard) show a helpful message instead of stale/empty data. No dates
    configured at all is treated the same as 'not started yet'."""
    window = _resolve_challenge_window()
    if not window:
        return "not_started"
    start, end, now = window
    if now < start:
        return "not_started"
    if now > end:
        return "ended"
    return "active"


def format_points(points: int) -> str:
    """Format points with sign"""
    if points > 0:
        return f"+{points}"
    return str(points)


def truncate_text(text: str, max_length: int = 1024) -> str:
    """Truncate text to max length"""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


async def has_admin_role(interaction: discord.Interaction) -> bool:
    """Check if user has admin or mod role"""
    from config.settings import ADMIN_ROLE_ID, MOD_ROLE_ID

    if not interaction.user.guild_permissions.administrator:
        user_role_ids = [role.id for role in interaction.user.roles]
        if ADMIN_ROLE_ID not in user_role_ids and MOD_ROLE_ID not in user_role_ids:
            return False
    return True


def get_tier_emoji(tier: str) -> str:
    """Get emoji for tier"""
    from config.constants import TIERS

    return TIERS.get(tier, {}).get("emoji", "⚪")


def get_tier_role_mention(tier: str, guild: discord.Guild = None) -> str:
    """Get role mention for tier if available, otherwise return role name"""
    from config.constants import TIERS

    tier_data = TIERS.get(tier, {})
    role_name = tier_data.get("role_name", tier)

    # If guild is provided, try to find and mention the role
    if guild:
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            return role.mention

    return role_name


async def send_error_embed(interaction: discord.Interaction, message: str):
    """Send error embed"""
    embed = discord.Embed(title="❌ Error", description=message, color=BRAND_COLOR)

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def send_success_embed(interaction: discord.Interaction, message: str):
    """Send success embed"""
    embed = discord.Embed(title="✅ Success", description=message, color=BRAND_COLOR)

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)
