import discord
from datetime import datetime
from typing import List, Dict, Any
from config.constants import TIERS
from utils.helpers import get_tier_emoji


def create_leaderboard_embed(
    users: List[Dict[str, Any]], title: str = "🏆 LEADERBOARD"
) -> discord.Embed:
    """Create leaderboard embed"""
    embed = discord.Embed(
        title=title,
        description="Top performers in the RunItUp Q1 Challenge",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow(),
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

        leaderboard_text += (
            f"{medal} **{user['username']}** {tier_emoji}{scaler_badge}\n"
        )
        leaderboard_text += f"    └ {user['total_points']} points\n\n"

    embed.description = leaderboard_text
    embed.set_footer(text="RunItUp Q1 Challenge • Updated")

    return embed


def create_user_stats_embed(user_data: Dict[str, Any]) -> discord.Embed:
    """Create user stats embed"""
    tier_emoji = get_tier_emoji(user_data["tier"])
    tier_name = TIERS[user_data["tier"]]["role_name"]

    embed = discord.Embed(
        title=f"{tier_emoji} {user_data['username']}'s Stats",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow(),
    )

    embed.add_field(
        name="📊 Total Points",
        value=f"**{user_data['total_points']}** points",
        inline=True,
    )

    embed.add_field(name="🎖️ Tier", value=f"{tier_emoji} **{tier_name}**", inline=True)

    if user_data.get("is_scaler"):
        embed.add_field(name="⚙️ Status", value="**Scaler** (Verified)", inline=True)

    embed.add_field(
        name="🤝 Referrals",
        value=f"{user_data.get('referral_count', 0)}/10",
        inline=True,
    )

    embed.set_footer(text="RunItUp Q1 Challenge")

    return embed


def create_submission_embed(
    submission: Dict[str, Any], user: discord.User
) -> discord.Embed:
    """Create submission review embed"""
    embed = discord.Embed(
        title=f"📥 New {submission['submission_type'].title()} Submission",
        color=discord.Color.orange(),
        timestamp=datetime.utcnow(),
    )

    embed.add_field(name="User", value=user.mention, inline=True)
    embed.add_field(name="Type", value=submission["submission_type"], inline=True)
    embed.add_field(name="ID", value=f"`{submission['id']}`", inline=True)

    if submission.get("description"):
        embed.add_field(
            name="Description", value=submission["description"][:1024], inline=False
        )

    if submission.get("amount"):
        embed.add_field(
            name="Amount", value=f"${submission['amount']:.2f}", inline=True
        )

    if submission.get("referral_type"):
        embed.add_field(
            name="Referral Type", value=submission["referral_type"].upper(), inline=True
        )

    if submission.get("proof_url"):
        embed.add_field(
            name="Proof", value=f"[View Proof]({submission['proof_url']})", inline=False
        )

    embed.set_footer(text=f"Submission ID: {submission['id']}")

    return embed
