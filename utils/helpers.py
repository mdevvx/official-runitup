from datetime import datetime, timedelta
from typing import List, Optional, Tuple
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


def get_challenge_week_ranges() -> List[Tuple[datetime, datetime, int]]:
    """Returns every full, uniform 7-day (week_start, week_end, week_number)
    block in the challenge - e.g. a 74-day challenge is exactly 10 weeks
    (Day 1-70). Any trailing remainder (Day 71-74) is NOT a week at all -
    no Weekly Victory checkpoint on it, it just still counts toward the
    season leaderboard/total points on the way to the final-day finale.
    week_number is 1-based. [] if dates aren't configured or the challenge
    is under a week long."""
    window = _resolve_challenge_window()
    if not window:
        return []
    start, end, _ = window

    total_days = (end - start).days + 1  # inclusive day count (Day 1..Day 74)
    total_weeks = total_days // 7  # floor - trailing remainder days get no week

    ranges = []
    for week_number in range(1, total_weeks + 1):
        week_start = start + timedelta(days=(week_number - 1) * 7)
        week_end = week_start + timedelta(days=7)
        ranges.append((week_start, week_end, week_number))
    return ranges


def get_current_week_range() -> Optional[Tuple[datetime, datetime, int]]:
    """Returns (week_start, week_end, week_number) for 'now'. None if dates
    aren't configured, or 'now' falls outside every week block (challenge
    hasn't started yet or has already ended) - callers should treat that
    like "no week to show"."""
    window = _resolve_challenge_window()
    if not window:
        return None
    _, _, now = window

    for week_start, week_end, week_number in get_challenge_week_ranges():
        if week_start <= now < week_end:
            return week_start, week_end, week_number
    return None


def get_closed_week_ranges() -> List[Tuple[datetime, datetime, int]]:
    """Week blocks that have fully ended as of 'now' - used to finalize
    Weekly Victory once a week's points are final and won't change anymore
    (see WeeklyVictoryModel.finalize_week)."""
    window = _resolve_challenge_window()
    if not window:
        return []
    _, _, now = window
    return [
        (week_start, week_end, week_number)
        for week_start, week_end, week_number in get_challenge_week_ranges()
        if now >= week_end
    ]


def get_current_month_range() -> Optional[Tuple[datetime, datetime, int]]:
    """Returns (month_start, month_end, month_number) for 'now', if 'now'
    falls within a configured Monthly Victory month group (see
    config.constants.MONTHLY_VICTORY_WEEK_GROUPS). None if no month is
    currently active - e.g. Weeks 9-10 belong to no month by design, same
    as before/after the challenge - or dates aren't configured."""
    from config.constants import MONTHLY_VICTORY_WEEK_GROUPS

    current_week = get_current_week_range()
    if not current_week:
        return None
    _, _, current_week_number = current_week

    week_dates_by_number = {n: (s, e) for s, e, n in get_challenge_week_ranges()}

    for month_number, (first_week, last_week) in MONTHLY_VICTORY_WEEK_GROUPS.items():
        if first_week <= current_week_number <= last_week:
            if first_week not in week_dates_by_number or last_week not in week_dates_by_number:
                return None
            month_start = week_dates_by_number[first_week][0]
            month_end = week_dates_by_number[last_week][1]
            return month_start, month_end, month_number
    return None


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
