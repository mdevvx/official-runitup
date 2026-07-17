import discord
from datetime import datetime, timezone
from typing import List, Dict, Any
from config.constants import BRAND_COLOR
from config.settings import LEADERBOARD_IMAGE_URL, MAX_REFERRALS
from utils.helpers import get_tier_emoji, get_tier_role_mention


def create_leaderboard_embed(
    users: List[Dict[str, Any]], title: str = "🏆 LEADERBOARD"
) -> discord.Embed:
    """Create leaderboard embed"""
    embed = discord.Embed(
        title=title,
        description="Top performers in the RunItUp Q2 Challenge",
        color=BRAND_COLOR,
        timestamp=datetime.now(timezone.utc),
    )

    if not users:
        embed.add_field(
            name="No Data", value="No users on the leaderboard yet!", inline=False
        )
        return embed

    leaderboard_text = ""
    medals = ["🥇", "🥈", "🥉"]

    for idx, user in enumerate(users):
        rank = idx + 1
        medal = medals[idx] if idx < 3 else f"`#{rank}`"
        tier_emoji = get_tier_emoji(user["tier"])
        scaler_badge = " ⚙️" if user.get("is_scaler") else ""
        master_badge = " 🥋" if user.get("is_master") else ""

        # Use mention field that's added in models.py
        user_mention = user.get("mention", f"<@{user['user_id']}>")

        leaderboard_text += (
            f"{medal} **{user_mention}** {tier_emoji}{scaler_badge}{master_badge}\n"
        )
        leaderboard_text += f"    └ {user['total_points']} points\n\n"

    embed.description = leaderboard_text
    # Add leaderboard image
    embed.set_image(url=LEADERBOARD_IMAGE_URL)
    embed.set_footer(text="RunItUp Q2 Challenge • Updated")

    return embed


def create_user_stats_embed(
    user_data: Dict[str, Any],
    discord_user: discord.User = None,
    guild: discord.Guild = None,
) -> discord.Embed:
    """Create user stats embed with user mention"""
    tier_emoji = get_tier_emoji(user_data["tier"])

    # Get user mention - prefer from discord_user, fallback to mention field or construct
    if discord_user:
        user_mention = discord_user.mention
        display_name = discord_user.display_name
        guild = guild or getattr(discord_user, "guild", None)
    else:
        user_mention = user_data.get("mention", f"<@{user_data['user_id']}>")
        display_name = user_data["username"]

    embed = discord.Embed(
        title=f"{tier_emoji} {display_name}'s Stats",
        description=f"Stats for {user_mention}",
        color=BRAND_COLOR,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="📊 Total Points",
        value=f"**{user_data['total_points']}** points",
        inline=True,
    )

    # Resolve the actual Discord role mention if it exists in this guild,
    # falling back to the plain role name text otherwise
    tier_role_display = get_tier_role_mention(user_data["tier"], guild)
    embed.add_field(name="🎖️ Tier", value=f"{tier_emoji} {tier_role_display}", inline=True)

    if user_data.get("is_scaler"):
        embed.add_field(name="⚙️ Status", value="**Scaler** (Verified)", inline=True)

    if user_data.get("is_master"):
        embed.add_field(name="🥋 Bonus", value="**Masters** (+15%)", inline=True)

    embed.add_field(
        name="🤝 Referrals",
        value=f"{user_data.get('referral_count', 0)}/{MAX_REFERRALS}",
        inline=True,
    )

    embed.set_footer(text="RunItUp Q2 Challenge")

    return embed


