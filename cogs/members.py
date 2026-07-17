import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from database.models import UserModel, DailyActivityModel
from database.bot_config import BotConfigModel
from utils.logger import get_logger
from utils.embeds import (
    create_user_stats_embed,
    create_leaderboard_embed,
)
from utils.helpers import (
    is_challenge_active,
    challenge_status,
    get_tier_emoji,
    get_tier_role_mention,
)
from config.constants import BRAND_COLOR, TIERS
from cogs.season_group import season_group

logger = get_logger(__name__)


class Members(commands.Cog):
    """Member commands for the RunItUp Challenge (slash commands live under season_group)"""

    def __init__(self, bot):
        self.bot = bot
        logger.info("Members cog loaded")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track daily activity on messages"""
        if message.author.bot:
            return

        if not message.guild:
            return

        if not is_challenge_active():
            return

        try:
            await UserModel.get_or_create(message.author.id, message.author.name)
            await DailyActivityModel.track_activity(message.author.id)

            awarded = await DailyActivityModel.award_daily_point(
                message.author.id, bot=self.bot
            )

            if awarded:
                logger.info(f"✅ Awarded daily activity point to {message.author.name}")

        except Exception as e:
            logger.error(f"❌ Error tracking activity for {message.author.name}: {e}")


async def setup(bot):
    await bot.add_cog(Members(bot))


# ----------------------------------------------------------------------
# Live Q2 commands
# ----------------------------------------------------------------------


@season_group.command(name="points", description="Check your points and stats")
async def points(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        user_data = await UserModel.get_or_create(
            interaction.user.id, interaction.user.name
        )

        embed = create_user_stats_embed(
            user_data, discord_user=interaction.user, guild=interaction.guild
        )

        leaderboard_data = await UserModel.get_leaderboard(limit=100)
        rank = next(
            (
                i + 1
                for i, u in enumerate(leaderboard_data)
                if u["user_id"] == interaction.user.id
            ),
            None,
        )

        if rank:
            embed.add_field(
                name="🏅 Rank", value=f"**#{rank}** of {len(leaderboard_data)}", inline=True
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"❌ Error in points command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching your points.", ephemeral=True
        )


@season_group.command(name="leaderboard", description="View the top 10 leaderboard")
async def leaderboard(interaction: discord.Interaction, limit: Optional[int] = 10):
    try:
        await interaction.response.defer()

        status = challenge_status()
        status_messages = {
            "not_started": "📅 The challenge hasn't started yet — check back once it begins!",
            "ended": "🏁 The challenge has ended.",
        }
        if status in status_messages:
            await interaction.followup.send(status_messages[status])
            return

        if limit < 1 or limit > 25:
            limit = 10

        users = await UserModel.get_leaderboard(limit=limit)
        embed = create_leaderboard_embed(users, title=f"🏆 TOP {len(users)} LEADERBOARD")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"❌ Error in leaderboard command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching the leaderboard.", ephemeral=True
        )


@season_group.command(name="mytier", description="Check your current tier and progress")
async def mytier(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        user_data = await UserModel.get_or_create(
            interaction.user.id, interaction.user.name
        )

        current_tier = user_data["tier"]
        points_total = user_data["total_points"]

        thresholds = BotConfigModel.get_tier_thresholds()
        sorted_tiers = sorted(thresholds.items(), key=lambda kv: kv[1])

        embed = discord.Embed(
            title=f"{get_tier_emoji(current_tier)} Your Tier Progress",
            description=f"Tier progress for {interaction.user.mention}",
            color=BRAND_COLOR,
        )

        for idx, (tier_name, min_points) in enumerate(sorted_tiers):
            tier_data = TIERS.get(tier_name, {})
            emoji = tier_data.get("emoji", "⚪")
            role_display = get_tier_role_mention(tier_name, interaction.guild)
            max_points = (
                sorted_tiers[idx + 1][1] - 1 if idx + 1 < len(sorted_tiers) else "∞"
            )

            if tier_name == current_tier:
                status = "**← YOU ARE HERE**"
            elif points_total > min_points:
                status = "✅ Completed"
            else:
                status = f"🔒 Need {min_points - points_total} more points"

            # Discord only resolves mention syntax in embed field VALUES, not
            # names - the role mention has to live in value, not name.
            embed.add_field(
                name=f"{emoji} Tier",
                value=f"{role_display}\n{min_points}-{max_points} points\n{status}",
                inline=False,
            )

        embed.set_footer(text=f"Current Points: {points_total}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"❌ Error in mytier command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while checking your tier.", ephemeral=True
        )
