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
        name="setpoints", description="[ADMIN] Set a user's total points"
    )
    @app_commands.describe(
        user="The user to set points for",
        points="New total points",
        reason="Reason for setting points",
    )
    async def set_points(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        points: int,
        reason: str,
    ):
        """Set user's total points"""
        try:
            await interaction.response.defer(ephemeral=True)

            if points < 0:
                await send_error_embed(interaction, "❌ Points cannot be negative.")
                return

            # Get current points
            user_data = await UserModel.get_or_create(user.id, user.name)
            current_points = user_data["total_points"]

            # Calculate difference
            points_diff = points - current_points

            # Update points with bot instance for immediate role update
            updated_user = await UserModel.update_points(
                user.id, points_diff, f"Points set by admin: {reason}", bot=self.bot
            )

            # Get tier role mention
            tier_role = get_tier_role_mention(updated_user["tier"], interaction.guild)

            # Log action
            logger.info(
                f"✅ {interaction.user.name} set {user.name}'s points to {points}: {reason}"
            )

            await send_success_embed(
                interaction,
                f"✅ Set {user.mention}'s points to **{points}**\n\n"
                f"**Reason:** {reason}\n"
                f"**Previous Total:** {current_points} points\n"
                f"**Change:** {format_points(points_diff)}\n"
                f"**Tier:** {tier_role}\n"
                f"🎖️ Discord role updated automatically!",
            )

        except Exception as e:
            logger.error(f"❌ Error in set_points command: {e}")
            await send_error_embed(
                interaction, "❌ An error occurred while setting points."
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

    @app_commands.command(
        name="updateleaderboard", description="[ADMIN] Manually update the leaderboard"
    )
    async def update_leaderboard(self, interaction: discord.Interaction):
        """Manually update leaderboard"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Get leaderboard
            users = await UserModel.get_leaderboard(limit=10)

            # Create embed
            embed = create_leaderboard_embed(users)

            # Get leaderboard channel
            leaderboard_channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)

            if not leaderboard_channel:
                await send_error_embed(
                    interaction,
                    "❌ Leaderboard channel not found. Check configuration.",
                )
                return

            # Delete old messages and send new
            async for message in leaderboard_channel.history(limit=10):
                if message.author == self.bot.user:
                    await message.delete()

            await leaderboard_channel.send(embed=embed)

            logger.info(f"✅ Leaderboard updated by {interaction.user.name}")

            await send_success_embed(interaction, "✅ Leaderboard has been updated!")

        except Exception as e:
            logger.error(f"❌ Error in update_leaderboard command: {e}")
            await send_error_embed(
                interaction, "❌ An error occurred while updating the leaderboard."
            )

    @app_commands.command(
        name="pendingsubmissions", description="[ADMIN] View all pending submissions"
    )
    async def pending_submissions(self, interaction: discord.Interaction):
        """View pending submissions"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Get pending submissions
            submissions = await SubmissionModel.get_pending()

            if not submissions:
                await send_success_embed(interaction, "✅ No pending submissions!")
                return

            embed = discord.Embed(
                title="🔥 Pending Submissions",
                description=f"Total pending: **{len(submissions)}**",
                color=discord.Color.orange(),
            )

            for submission in submissions[:10]:  # Show first 10
                user = await self.bot.fetch_user(submission["user_id"])

                value = f"**User:** {user.mention}\n"
                value += f"**Type:** {submission['submission_type']}\n"
                if submission.get("amount"):
                    value += f"**Amount:** ${submission['amount']:.2f}\n"
                if submission.get("referral_type"):
                    value += f"**Referral Type:** {submission['referral_type']}\n"
                value += f"**ID:** `{submission['id']}`"

                embed.add_field(
                    name=f"Submission {submission['id']}", value=value, inline=False
                )

            if len(submissions) > 10:
                embed.set_footer(text=f"Showing 10 of {len(submissions)} submissions")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"❌ Error in pending_submissions command: {e}")
            await send_error_embed(
                interaction, "❌ An error occurred while fetching pending submissions."
            )


async def setup(bot):
    await bot.add_cog(Admin(bot))
