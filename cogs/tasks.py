import discord
from discord.ext import commands, tasks
from datetime import datetime, time

from database.models import UserModel
from utils.logger import get_logger
from utils.embeds import create_leaderboard_embed
from config.settings import LEADERBOARD_CHANNEL_ID, GUILD_ID
from config.constants import TIERS

logger = get_logger(__name__)


class Tasks(commands.Cog):
    """Background tasks for automation"""

    def __init__(self, bot):
        self.bot = bot
        self.update_leaderboard_task.start()
        self.update_tier_roles_task.start()
        self.backup_data_task.start()

    def cog_unload(self):
        """Stop tasks when cog is unloaded"""
        self.update_leaderboard_task.cancel()
        self.update_tier_roles_task.cancel()
        self.backup_data_task.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Tasks cog loaded")

    @tasks.loop(hours=6)
    async def update_leaderboard_task(self):
        """Update leaderboard every 6 hours"""
        try:
            logger.info("🔄 Starting leaderboard update task...")

            # Get leaderboard
            users = await UserModel.get_leaderboard(limit=10)

            # Create embed
            embed = create_leaderboard_embed(users)

            # Get leaderboard channel
            leaderboard_channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)

            if not leaderboard_channel:
                logger.error("❌ Leaderboard channel not found")
                return

            # Delete old leaderboard messages
            async for message in leaderboard_channel.history(limit=10):
                if message.author == self.bot.user:
                    await message.delete()

            # Send new leaderboard
            await leaderboard_channel.send(embed=embed)

            logger.info("✅ Leaderboard updated successfully")

        except Exception as e:
            logger.error(f"❌ Error in update_leaderboard_task: {e}")

    @update_leaderboard_task.before_loop
    async def before_update_leaderboard(self):
        """Wait until bot is ready"""
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def update_tier_roles_task(self):
        """Update tier roles for all users every hour"""
        try:
            logger.info("🔄 Starting tier role update task...")

            from database.supabase_client import get_supabase

            # Get guild
            guild = self.bot.get_guild(GUILD_ID)
            if not guild:
                logger.error("❌ Guild not found")
                return

            # Get all tier roles
            tier_roles = {}
            for tier_name, tier_data in TIERS.items():
                role = discord.utils.get(guild.roles, name=tier_data["role_name"])
                if role:
                    tier_roles[tier_name] = role

            if not tier_roles:
                logger.warning("⚠️ No tier roles found in guild")
                return

            # Get all users with points
            supabase = get_supabase()
            response = supabase.table("users").select("*").execute()

            updated_count = 0

            for user_data in response.data:
                try:
                    member = guild.get_member(user_data["user_id"])
                    if not member:
                        continue

                    current_tier = user_data["tier"]
                    current_tier_role = tier_roles.get(current_tier)

                    if not current_tier_role:
                        continue

                    # Check if member has the correct tier role
                    has_correct_role = current_tier_role in member.roles

                    # Remove all other tier roles
                    roles_to_remove = [
                        role
                        for tier, role in tier_roles.items()
                        if tier != current_tier and role in member.roles
                    ]

                    if roles_to_remove or not has_correct_role:
                        # Remove incorrect tier roles
                        if roles_to_remove:
                            await member.remove_roles(
                                *roles_to_remove, reason="Tier update"
                            )

                        # Add correct tier role
                        if not has_correct_role:
                            await member.add_roles(
                                current_tier_role, reason="Tier update"
                            )

                        updated_count += 1
                        logger.debug(f"✅ Updated tier roles for {member.name}")

                except Exception as e:
                    logger.error(
                        f"❌ Error updating roles for user {user_data['user_id']}: {e}"
                    )
                    continue

            if updated_count > 0:
                logger.info(f"✅ Updated tier roles for {updated_count} users")
            else:
                logger.info("✅ All tier roles are up to date")

        except Exception as e:
            logger.error(f"❌ Error in update_tier_roles_task: {e}")

    @update_tier_roles_task.before_loop
    async def before_update_tier_roles(self):
        """Wait until bot is ready"""
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(hour=3, minute=0))  # Run at 3 AM daily
    async def backup_data_task(self):
        """Daily data backup and cleanup"""
        try:
            logger.info("🔄 Starting daily backup task...")

            from database.supabase_client import get_supabase
            from datetime import date, timedelta

            supabase = get_supabase()

            # Clean up old daily activity records (older than 30 days)
            cutoff_date = (date.today() - timedelta(days=30)).isoformat()

            result = (
                supabase.table("daily_activity")
                .delete()
                .lt("activity_date", cutoff_date)
                .execute()
            )

            if result.data:
                logger.info(f"✅ Cleaned up {len(result.data)} old activity records")

            # Log database stats
            users_count = (
                supabase.table("users").select("*", count="exact").execute().count
            )
            submissions_count = (
                supabase.table("submissions").select("*", count="exact").execute().count
            )

            logger.info(
                f"📊 Database stats: {users_count} users, {submissions_count} submissions"
            )

        except Exception as e:
            logger.error(f"❌ Error in backup_data_task: {e}")

    @backup_data_task.before_loop
    async def before_backup_data(self):
        """Wait until bot is ready"""
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Tasks(bot))
