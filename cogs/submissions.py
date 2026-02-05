import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from database.models import SubmissionModel, UserModel
from utils.logger import get_logger
from utils.helpers import is_challenge_active, send_error_embed, send_success_embed
from utils.validators import validate_url, validate_amount, sanitize_input
from utils.embeds import create_submission_embed
from config.settings import SUBMISSIONS_CHANNEL_ID, MAX_REFERRALS
from config.constants import SUBMISSION_TYPES, REFERRAL_TYPES, POINTS

logger = get_logger(__name__)


class Submissions(commands.Cog):
    """Handle win and referral submissions"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Submissions cog loaded")

    @app_commands.command(name="submitwin", description="Submit a win for review")
    @app_commands.describe(
        amount="Revenue amount (e.g., 100, 500, 1000)",
        description="Brief description of the win",
        proof_url="Screenshot/proof URL (optional)",
    )
    async def submit_win(
        self,
        interaction: discord.Interaction,
        amount: str,
        description: str,
        proof_url: Optional[str] = None,
    ):
        """Submit a win for review"""
        try:
            await interaction.response.defer(ephemeral=True)

            # # Check if challenge is active
            # if not is_challenge_active():
            #     await send_error_embed(
            #         interaction, "❌ The challenge is not currently active!"
            #     )
            #     return

            # Validate amount
            parsed_amount = validate_amount(amount)
            if parsed_amount is None:
                await send_error_embed(
                    interaction,
                    "❌ Invalid amount format. Please use numbers only (e.g., 100, 500, 1000)",
                )
                return

            # Validate proof URL if provided
            if proof_url and not validate_url(proof_url):
                await send_error_embed(
                    interaction,
                    "❌ Invalid URL format. Please provide a valid URL or leave it empty.",
                )
                return

            # Sanitize description
            clean_description = sanitize_input(description, max_length=500)

            # Ensure user exists
            await UserModel.get_or_create(interaction.user.id, interaction.user.name)

            # Create submission
            submission = await SubmissionModel.create(
                user_id=interaction.user.id,
                submission_type=SUBMISSION_TYPES["WIN"],
                description=clean_description,
                proof_url=proof_url,
                amount=parsed_amount,
            )

            # Send to submissions channel
            submissions_channel = self.bot.get_channel(SUBMISSIONS_CHANNEL_ID)
            if submissions_channel:
                embed = create_submission_embed(submission, interaction.user)

                # Create view with approve/reject buttons
                view = SubmissionView(submission["id"], self.bot)
                await submissions_channel.send(embed=embed, view=view)

            # Confirm to user
            await send_success_embed(
                interaction,
                f"✅ Win submitted for review!\n\n"
                f"**Amount:** ${parsed_amount:.2f}\n"
                f"**Submission ID:** `{submission['id']}`\n\n"
                f"A moderator will review your submission shortly.",
            )

        except Exception as e:
            logger.error(f"❌ Error in submit_win command: {e}")
            await send_error_embed(
                interaction,
                "❌ An error occurred while submitting your win. Please try again.",
            )

    @app_commands.command(
        name="submitreferral", description="Submit a referral for review"
    )
    @app_commands.describe(
        referral_type="Type of referral (whop or discord)",
        username="Username of the person referred",
        proof_url="Proof URL (optional)",
    )
    @app_commands.choices(
        referral_type=[
            app_commands.Choice(name="WHOP Referral", value="whop"),
            app_commands.Choice(name="Discord Referral", value="discord"),
        ]
    )
    async def submit_referral(
        self,
        interaction: discord.Interaction,
        referral_type: str,
        username: str,
        proof_url: Optional[str] = None,
    ):
        """Submit a referral for review"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Check if challenge is active
            # if not is_challenge_active():
            #     await send_error_embed(
            #         interaction, "❌ The challenge is not currently active!"
            #     )
            #     return

            # Get user data
            user_data = await UserModel.get_or_create(
                interaction.user.id, interaction.user.name
            )

            # Check referral limit
            if user_data["referral_count"] >= MAX_REFERRALS:
                await send_error_embed(
                    interaction,
                    f"❌ You've reached the maximum of {MAX_REFERRALS} referrals!",
                )
                return

            # Validate proof URL if provided
            if proof_url and not validate_url(proof_url):
                await send_error_embed(
                    interaction,
                    "❌ Invalid URL format. Please provide a valid URL or leave it empty.",
                )
                return

            # Sanitize username
            clean_username = sanitize_input(username, max_length=100)

            # Create submission
            submission = await SubmissionModel.create(
                user_id=interaction.user.id,
                submission_type=SUBMISSION_TYPES["REFERRAL"],
                description=f"Referred: {clean_username}",
                proof_url=proof_url,
                referral_type=referral_type,
            )

            # Send to submissions channel
            submissions_channel = self.bot.get_channel(SUBMISSIONS_CHANNEL_ID)
            if submissions_channel:
                embed = create_submission_embed(submission, interaction.user)
                view = SubmissionView(submission["id"], self.bot)
                await submissions_channel.send(embed=embed, view=view)

            # Confirm to user
            referral_points = (
                POINTS["WHOP_REFERRAL"]
                if referral_type == "whop"
                else POINTS["DISCORD_REFERRAL"]
            )

            await send_success_embed(
                interaction,
                f"✅ Referral submitted for review!\n\n"
                f"**Type:** {referral_type.upper()}\n"
                f"**Username:** {clean_username}\n"
                f"**Potential Points:** +{referral_points}\n"
                f"**Submission ID:** `{submission['id']}`\n\n"
                f"Referrals remaining: {MAX_REFERRALS - user_data['referral_count'] - 1}/{MAX_REFERRALS}",
            )

        except Exception as e:
            logger.error(f"❌ Error in submit_referral command: {e}")
            await send_error_embed(
                interaction,
                "❌ An error occurred while submitting your referral. Please try again.",
            )

    @app_commands.command(
        name="applyscaler", description="Apply for Scaler status ($1K+/day verified)"
    )
    @app_commands.describe(
        description="Describe your revenue (e.g., 'Consistent $1.5K/day for 2 weeks')",
        proof_url="Screenshot/proof of revenue",
    )
    async def apply_scaler(
        self, interaction: discord.Interaction, description: str, proof_url: str
    ):
        """Apply for Scaler status"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Check if challenge is active
            # if not is_challenge_active():
            #     await send_error_embed(
            #         interaction, "❌ The challenge is not currently active!"
            #     )
            #     return

            # Check if already a scaler
            user_data = await UserModel.get_or_create(
                interaction.user.id, interaction.user.name
            )

            if user_data["is_scaler"]:
                await send_error_embed(
                    interaction, "❌ You're already verified as a Scaler!"
                )
                return

            # Validate proof URL
            if not validate_url(proof_url):
                await send_error_embed(
                    interaction,
                    "❌ Invalid URL format. Please provide a valid proof URL.",
                )
                return

            # Sanitize description
            clean_description = sanitize_input(description, max_length=500)

            # Create submission
            submission = await SubmissionModel.create(
                user_id=interaction.user.id,
                submission_type=SUBMISSION_TYPES["SCALER"],
                description=clean_description,
                proof_url=proof_url,
            )

            # Send to submissions channel
            submissions_channel = self.bot.get_channel(SUBMISSIONS_CHANNEL_ID)
            if submissions_channel:
                embed = create_submission_embed(submission, interaction.user)
                embed.color = discord.Color.purple()
                embed.title = "⚙️ Scaler Application"

                view = ScalerApplicationView(submission["id"], self.bot)
                await submissions_channel.send(embed=embed, view=view)

            # Confirm to user
            await send_success_embed(
                interaction,
                f"✅ Scaler application submitted!\n\n"
                f"**Submission ID:** `{submission['id']}`\n\n"
                f"A moderator will review your application and proof shortly. "
                f"Once approved, you'll gain access to the Scalers chat!",
            )

        except Exception as e:
            logger.error(f"❌ Error in apply_scaler command: {e}")
            await send_error_embed(
                interaction,
                "❌ An error occurred while submitting your application. Please try again.",
            )


class SubmissionView(discord.ui.View):
    """View for win/referral submission approval"""

    def __init__(self, submission_id: int, bot):
        super().__init__(timeout=None)
        self.submission_id = submission_id
        self.bot = bot

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        custom_id="approve_submission",
    )
    async def approve_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Approve submission"""
        try:
            from utils.helpers import has_admin_role
            from database.supabase_client import get_supabase

            # Check permissions
            if not await has_admin_role(interaction):
                await send_error_embed(
                    interaction, "❌ You don't have permission to approve submissions."
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Get submission
            supabase = get_supabase()
            response = (
                supabase.table("submissions")
                .select("*")
                .eq("id", self.submission_id)
                .execute()
            )

            if not response.data:
                await send_error_embed(interaction, "❌ Submission not found.")
                return

            submission = response.data[0]

            # Check if already processed
            if submission["status"] != "pending":
                await send_error_embed(
                    interaction,
                    f"❌ This submission was already {submission['status']}.",
                )
                return

            # Calculate points based on type
            points = 0
            if submission["submission_type"] == "win":
                amount = submission["amount"]
                if amount >= 5000:
                    points = POINTS["WIN_5K"]
                elif amount >= 1000:
                    points = POINTS["WIN_1K"]
                elif amount >= 500:
                    points = POINTS["WIN_500"]
                elif amount >= 100:
                    points = POINTS["WIN_100"]
                else:
                    points = POINTS["FIRST_SALE"]

            elif submission["submission_type"] == "referral":
                if submission["referral_type"] == "whop":
                    points = POINTS["WHOP_REFERRAL"]
                else:
                    points = POINTS["DISCORD_REFERRAL"]

                # Increment referral count
                user = await UserModel.get_by_id(submission["user_id"])
                supabase.table("users").update(
                    {"referral_count": user["referral_count"] + 1}
                ).eq("user_id", submission["user_id"]).execute()

            # Approve submission
            await SubmissionModel.approve(
                self.submission_id, interaction.user.id, points
            )

            # Update embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "✅ " + embed.title
            embed.add_field(
                name="Status",
                value=f"Approved by {interaction.user.mention}\nPoints Awarded: +{points}",
                inline=False,
            )

            # Disable buttons
            for item in self.children:
                item.disabled = True

            await interaction.message.edit(embed=embed, view=self)

            # Notify user
            user = await self.bot.fetch_user(submission["user_id"])
            try:
                await user.send(
                    f"✅ Your submission has been approved!\n\n"
                    f"**Type:** {submission['submission_type']}\n"
                    f"**Points Awarded:** +{points}\n"
                    f"**Submission ID:** `{self.submission_id}`"
                )
            except:
                pass

            await send_success_embed(
                interaction, f"✅ Submission approved! Awarded {points} points."
            )

        except Exception as e:
            logger.error(f"❌ Error approving submission: {e}")
            await send_error_embed(
                interaction, "❌ An error occurred while approving the submission."
            )

    @discord.ui.button(
        label="Reject", style=discord.ButtonStyle.danger, custom_id="reject_submission"
    )
    async def reject_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Reject submission"""
        try:
            from utils.helpers import has_admin_role
            from database.supabase_client import get_supabase

            # Check permissions
            if not await has_admin_role(interaction):
                await send_error_embed(
                    interaction, "❌ You don't have permission to reject submissions."
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Get submission
            supabase = get_supabase()
            response = (
                supabase.table("submissions")
                .select("*")
                .eq("id", self.submission_id)
                .execute()
            )

            if not response.data:
                await send_error_embed(interaction, "❌ Submission not found.")
                return

            submission = response.data[0]

            # Check if already processed
            if submission["status"] != "pending":
                await send_error_embed(
                    interaction,
                    f"❌ This submission was already {submission['status']}.",
                )
                return

            # Reject submission
            await SubmissionModel.reject(self.submission_id, interaction.user.id)

            # Update embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = "❌ " + embed.title
            embed.add_field(
                name="Status",
                value=f"Rejected by {interaction.user.mention}",
                inline=False,
            )

            # Disable buttons
            for item in self.children:
                item.disabled = True

            await interaction.message.edit(embed=embed, view=self)

            # Notify user
            user = await self.bot.fetch_user(submission["user_id"])
            try:
                await user.send(
                    f"❌ Your submission was not approved.\n\n"
                    f"**Type:** {submission['submission_type']}\n"
                    f"**Submission ID:** `{self.submission_id}`\n\n"
                    f"Please ensure your proof is clear and meets the requirements."
                )
            except:
                pass

            await send_success_embed(interaction, "✅ Submission rejected.")

        except Exception as e:
            logger.error(f"❌ Error rejecting submission: {e}")
            await send_error_embed(
                interaction, "❌ An error occurred while rejecting the submission."
            )


class ScalerApplicationView(discord.ui.View):
    """View for Scaler application approval"""

    def __init__(self, submission_id: int, bot):
        super().__init__(timeout=None)
        self.submission_id = submission_id
        self.bot = bot

    @discord.ui.button(
        label="Approve Scaler",
        style=discord.ButtonStyle.success,
        custom_id="approve_scaler",
    )
    async def approve_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Approve Scaler application"""
        try:
            from utils.helpers import has_admin_role
            from database.supabase_client import get_supabase
            from config.constants import TIERS

            # Check permissions
            if not await has_admin_role(interaction):
                await send_error_embed(
                    interaction,
                    "❌ You don't have permission to approve Scaler applications.",
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Get submission
            supabase = get_supabase()
            response = (
                supabase.table("submissions")
                .select("*")
                .eq("id", self.submission_id)
                .execute()
            )

            if not response.data:
                await send_error_embed(interaction, "❌ Submission not found.")
                return

            submission = response.data[0]

            # Check if already processed
            if submission["status"] != "pending":
                await send_error_embed(
                    interaction,
                    f"❌ This application was already {submission['status']}.",
                )
                return

            # Approve submission (no points for scaler status)
            await SubmissionModel.approve(self.submission_id, interaction.user.id, 0)

            # Set user as scaler
            await UserModel.set_scaler(submission["user_id"], True)

            # Assign Scaler role
            guild = interaction.guild
            user = guild.get_member(submission["user_id"])

            if user:
                scaler_role = discord.utils.get(guild.roles, name="Scaler")
                if scaler_role:
                    await user.add_roles(scaler_role)

            # Update embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "✅ Scaler Application Approved"
            embed.add_field(
                name="Status",
                value=f"Approved by {interaction.user.mention}\n⚙️ Scaler role granted",
                inline=False,
            )

            # Disable buttons
            for item in self.children:
                item.disabled = True

            await interaction.message.edit(embed=embed, view=self)

            # Notify user
            try:
                user_obj = await self.bot.fetch_user(submission["user_id"])
                await user_obj.send(
                    f"🎉 Congratulations! Your Scaler application has been approved!\n\n"
                    f"You now have access to the exclusive **Scalers Chat** and are recognized as a verified $1K+/day operator.\n\n"
                    f"Keep scaling! ⚙️"
                )
            except:
                pass

            await send_success_embed(
                interaction,
                "✅ Scaler application approved! User has been granted Scaler status.",
            )

        except Exception as e:
            logger.error(f"❌ Error approving Scaler application: {e}")
            await send_error_embed(
                interaction, "❌ An error occurred while approving the application."
            )

    @discord.ui.button(
        label="Reject", style=discord.ButtonStyle.danger, custom_id="reject_scaler"
    )
    async def reject_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Reject Scaler application"""
        try:
            from utils.helpers import has_admin_role
            from database.supabase_client import get_supabase

            # Check permissions
            if not await has_admin_role(interaction):
                await send_error_embed(
                    interaction,
                    "❌ You don't have permission to reject Scaler applications.",
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Get submission
            supabase = get_supabase()
            response = (
                supabase.table("submissions")
                .select("*")
                .eq("id", self.submission_id)
                .execute()
            )

            if not response.data:
                await send_error_embed(interaction, "❌ Submission not found.")
                return

            submission = response.data[0]

            # Check if already processed
            if submission["status"] != "pending":
                await send_error_embed(
                    interaction,
                    f"❌ This application was already {submission['status']}.",
                )
                return

            # Reject submission
            await SubmissionModel.reject(self.submission_id, interaction.user.id)

            # Update embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = "❌ Scaler Application Rejected"
            embed.add_field(
                name="Status",
                value=f"Rejected by {interaction.user.mention}",
                inline=False,
            )

            # Disable buttons
            for item in self.children:
                item.disabled = True

            await interaction.message.edit(embed=embed, view=self)

            # Notify user
            try:
                user = await self.bot.fetch_user(submission["user_id"])
                await user.send(
                    f"❌ Your Scaler application was not approved.\n\n"
                    f"Please ensure:\n"
                    f"• You have consistent $1K+/day revenue\n"
                    f"• Your proof clearly shows this revenue\n"
                    f"• Screenshots are clear and not cropped excessively\n\n"
                    f"You can reapply once you meet the requirements."
                )
            except:
                pass

            await send_success_embed(interaction, "✅ Scaler application rejected.")

        except Exception as e:
            logger.error(f"❌ Error rejecting Scaler application: {e}")
            await send_error_embed(
                interaction, "❌ An error occurred while rejecting the application."
            )


async def setup(bot):
    await bot.add_cog(Submissions(bot))
