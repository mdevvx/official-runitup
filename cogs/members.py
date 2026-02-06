import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from datetime import datetime

from database.models import UserModel, DailyActivityModel
from utils.logger import get_logger
from utils.embeds import (
    create_user_stats_embed,
    create_leaderboard_embed,
)
from utils.helpers import is_challenge_active

logger = get_logger(__name__)


class Members(commands.Cog):
    """Member commands for the RunItUp Challenge"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Members cog loaded")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track daily activity on messages"""
        # Ignore bot messages
        if message.author.bot:
            return

        # Ignore DMs
        if not message.guild:
            return

        # Only track during challenge
        if not is_challenge_active():
            return

        try:
            # Ensure user exists
            await UserModel.get_or_create(message.author.id, message.author.name)

            # Track activity
            await DailyActivityModel.track_activity(message.author.id)

            # Try to award daily point (will only award once per day) with bot instance
            awarded = await DailyActivityModel.award_daily_point(
                message.author.id, bot=self.bot
            )

            if awarded:
                logger.info(f"✅ Awarded daily activity point to {message.author.name}")

        except Exception as e:
            logger.error(f"❌ Error tracking activity for {message.author.name}: {e}")

    @app_commands.command(name="points", description="Check your points and stats")
    async def points(self, interaction: discord.Interaction):
        """Check user's points"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Get or create user
            user_data = await UserModel.get_or_create(
                interaction.user.id, interaction.user.name
            )

            # Create embed with user mention
            embed = create_user_stats_embed(user_data, discord_user=interaction.user)

            # Get rank
            leaderboard = await UserModel.get_leaderboard(limit=100)
            rank = next(
                (
                    i + 1
                    for i, u in enumerate(leaderboard)
                    if u["user_id"] == interaction.user.id
                ),
                None,
            )

            if rank:
                embed.add_field(
                    name="🏅 Rank",
                    value=f"**#{rank}** of {len(leaderboard)}",
                    inline=True,
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"❌ Error in points command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while fetching your points.", ephemeral=True
            )

    @app_commands.command(name="leaderboard", description="View the top 10 leaderboard")
    async def leaderboard(
        self, interaction: discord.Interaction, limit: Optional[int] = 10
    ):
        """Show leaderboard"""
        try:
            await interaction.response.defer()

            # Validate limit
            if limit < 1 or limit > 25:
                limit = 10

            # Get leaderboard
            users = await UserModel.get_leaderboard(limit=limit)

            # Create embed
            embed = create_leaderboard_embed(
                users, title=f"🏆 TOP {len(users)} LEADERBOARD"
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"❌ Error in leaderboard command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while fetching the leaderboard.", ephemeral=True
            )

    @app_commands.command(
        name="mytier", description="Check your current tier and progress"
    )
    async def mytier(self, interaction: discord.Interaction):
        """Show user's tier and progress"""
        try:
            await interaction.response.defer(ephemeral=True)

            from config.constants import TIERS
            from utils.helpers import get_tier_emoji

            # Get user data
            user_data = await UserModel.get_or_create(
                interaction.user.id, interaction.user.name
            )

            current_tier = user_data["tier"]
            points = user_data["total_points"]

            # Create embed with user mention
            embed = discord.Embed(
                title=f"{get_tier_emoji(current_tier)} Your Tier Progress",
                description=f"Tier progress for {interaction.user.mention}",
                color=discord.Color.blue(),
            )

            # Show all tiers with progress
            for tier_name, tier_data in TIERS.items():
                emoji = tier_data["emoji"]
                min_points = tier_data["min"]
                max_points = (
                    tier_data["max"] if tier_data["max"] != float("inf") else "∞"
                )

                if tier_name == current_tier:
                    status = "**← YOU ARE HERE**"
                elif points > tier_data["min"]:
                    status = "✅ Completed"
                else:
                    status = f"🔒 Need {tier_data['min'] - points} more points"

                embed.add_field(
                    name=f"{emoji} {tier_data['role_name']}",
                    value=f"{min_points}-{max_points} points\n{status}",
                    inline=False,
                )

            embed.set_footer(text=f"Current Points: {points}")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"❌ Error in mytier command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while checking your tier.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Members(bot))
