from datetime import datetime
from typing import Optional
import discord
from config.settings import CHALLENGE_START_DATE, CHALLENGE_END_DATE


def is_challenge_active() -> bool:
    """Check if challenge is currently active"""
    now = datetime.now()
    return CHALLENGE_START_DATE <= now <= CHALLENGE_END_DATE


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
    embed = discord.Embed(
        title="❌ Error", description=message, color=discord.Color.red()
    )

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def send_success_embed(interaction: discord.Interaction, message: str):
    """Send success embed"""
    embed = discord.Embed(
        title="✅ Success", description=message, color=discord.Color.green()
    )

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)
