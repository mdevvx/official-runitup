import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from database.models import UserModel, SubmissionModel
from utils.logger import get_logger
from utils.helpers import (
    has_admin_role,
    send_error_embed,
    send_success_embed,
    format_points,
    get_tier_role_mention,
)
from utils.embeds import create_leaderboard_embed
from config.settings import LEADERBOARD_CHANNEL_ID

logger = get_logger(__name__)


class Admin(commands.Cog):
    """Admin commands for managing the challenge"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Admin cog loaded")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions"""
        if not await has_admin_role(interaction):
            await send_error_embed(
                interaction, "❌ You don't have permission to use admin commands."
            )
            return False
        return True

    @app_commands.command(name="addpoints", description="[ADMIN] Add points to a user")
    @app_commands.describe(
        user="The user to add points to",
        points="Number of points to add",
        reason="Reason for adding points",
    )
    async def add_points(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        points: int,
        reason: str,
    ):
        """Add points to a user"""
        try:
            await interaction.response.defer(ephemeral=True)

            if points <= 0:
                await send_error_embed(interaction, "❌ Points must be greater than 0.")
                return

            # Ensure user exists
            await UserModel.get_or_create(user.id, user.name)

            # Add points with bot instance for immediate role update
            updated_user = await UserModel.update_points(
                user.id, points, reason, bot=self.bot
            )

            # Get tier role mention
            tier_role = get_tier_role_mention(updated_user["tier"], interaction.guild)

            # Log action
            logger.info(
                f"✅ {interaction.user.name} added {points} points to {user.name}: {reason}"
            )

            await send_success_embed(
                interaction,
                f"✅ Added **{format_points(points)}** points to {user.mention}\n\n"
                f"**Reason:** {reason}\n"
                f"**New Total:** {updated_user['total_points']} points\n"
                f"**Tier:** {tier_role}\n"
                f"🎖️ Discord role updated automatically!",
            )

        except Exception as e:
            logger.error(f"❌ Error in add_points command: {e}")
            await send_error_embed(
                interaction, "❌ An error occurred while adding points."
            )

    @app_commands.command(
        name="removepoints", description="[ADMIN] Remove points from a user"
    )
    @app_commands.describe(
        user="The user to remove points from",
        points="Number of points to remove",
        reason="Reason for removing points",
    )
    async def remove_points(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        points: int,
        reason: str,
    ):
        """Remove points from a user"""
        try:
            await interaction.response.defer(ephemeral=True)

            if points <= 0:
                await send_error_embed(interaction, "❌ Points must be greater than 0.")
                return

            # Ensure user exists
            user_data = await UserModel.get_or_create(user.id, user.name)

            # Check if user has enough points
            if user_data["total_points"] < points:
                await send_error_embed(
                    interaction,
                    f"❌ {user.mention} only has {user_data['total_points']} points. Cannot remove {points}.",
                )
                return

            # Remove points (negative value) with bot instance for immediate role update
            updated_user = await UserModel.update_points(
                user.id, -points, reason, bot=self.bot
            )

            # Get tier role mention
            tier_role = get_tier_role_mention(updated_user["tier"], interaction.guild)

            # Log action
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

    @app_commands.command(
        name="viewuser", description="[ADMIN] View detailed user stats"
    )
    @app_commands.describe(user="The user to view")
    async def view_user(self, interaction: discord.Interaction, user: discord.Member):
        """View detailed user information"""
        try:
            await interaction.response.defer(ephemeral=True)

            from database.supabase_client import get_supabase
            from utils.embeds import create_user_stats_embed

            # Get user data
            user_data = await UserModel.get_or_create(user.id, user.name)

            # Create base embed with user mention
            embed = create_user_stats_embed(user_data, discord_user=user)

            # Get recent points history
            supabase = get_supabase()
            history_response = (
                supabase.table("points_history")
                .select("*")
                .eq("user_id", user.id)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
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

            # Get submission stats
            submissions_response = (
                supabase.table("submissions")
                .select("status", count="exact")
                .eq("user_id", user.id)
                .execute()
            )

            if submissions_response.count:
                pending = len(
                    [s for s in submissions_response.data if s["status"] == "pending"]
                )
                approved = len(
                    [s for s in submissions_response.data if s["status"] == "approved"]
                )
                rejected = len(
                    [s for s in submissions_response.data if s["status"] == "rejected"]
                )

                embed.add_field(
                    name="📋 Submissions",
                    value=f"✅ Approved: {approved}\n⏳ Pending: {pending}\n❌ Rejected: {rejected}",
                    inline=True,
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"❌ Error in view_user command: {e}")
            await send_error_embed(
                interaction, "❌ An error occurred while viewing user stats."
            )


async def setup(bot):
    await bot.add_cog(Admin(bot))
