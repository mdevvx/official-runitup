import discord
from discord.ext import commands, tasks
from datetime import datetime, time

from database.models import UserModel, WeeklyVictoryModel, MonthlyVictoryModel, ChampionshipModel
from database.bot_config import BotConfigModel
from utils.logger import get_logger
from utils.embeds import create_leaderboard_embed
from utils.helpers import get_current_week_range, get_closed_week_ranges, challenge_status
from config.settings import GUILD_ID
from config.constants import CURRENT_SEASON, TIERS, MONTHLY_VICTORY_WEEK_GROUPS

logger = get_logger(__name__)


class Tasks(commands.Cog):
    """Background tasks for automation"""

    def __init__(self, bot):
        self.bot = bot
        self.update_leaderboard_task.start()
        self.update_tier_roles_task.start()
        self.finalize_weekly_victory_task.start()
        self.backup_data_task.start()
        logger.info("Tasks cog loaded")

    def cog_unload(self):
        """Stop tasks when cog is unloaded"""
        self.update_leaderboard_task.cancel()
        self.update_tier_roles_task.cancel()
        self.finalize_weekly_victory_task.cancel()
        self.backup_data_task.cancel()

    @tasks.loop(hours=6)
    async def update_leaderboard_task(self):
        """Update leaderboard every 6 hours"""
        try:
            logger.info("🔄 Starting leaderboard update task...")

            # Get leaderboard channel
            leaderboard_channel_id = BotConfigModel.get_channel_id("leaderboard")
            leaderboard_channel = (
                self.bot.get_channel(leaderboard_channel_id)
                if leaderboard_channel_id
                else None
            )

            if not leaderboard_channel:
                logger.error("❌ Leaderboard channel not found")
                return

            # Delete old leaderboard messages
            async for message in leaderboard_channel.history(limit=10):
                if message.author == self.bot.user:
                    await message.delete()

            status = challenge_status()
            if status == "not_started":
                await leaderboard_channel.send(
                    "📅 The challenge hasn't started yet — check back once it begins!"
                )
                logger.info("ℹ️ Leaderboard task skipped - challenge not started")
                return

            # Season (lifetime) leaderboard - always shown once the challenge
            # has started (still relevant after "ended", so no skip there)
            users = await UserModel.get_leaderboard(limit=10)
            embeds = [create_leaderboard_embed(users)]

            # Weekly leaderboard - only while there's a current week to show
            # (see get_current_week_range; None once the challenge has ended)
            week_range = get_current_week_range()
            if week_range:
                _, _, week_number = week_range
                weekly_users = await UserModel.get_weekly_leaderboard(limit=10)
                embeds.append(
                    create_leaderboard_embed(
                        weekly_users,
                        title=f"📅 WEEK {week_number} LEADERBOARD",
                        description=f"Top performers this week in the {CURRENT_SEASON} Challenge",
                        footer_text=f"{CURRENT_SEASON} Challenge • Week {week_number}",
                    )
                )

            # Send new leaderboard (season + week embeds in one message)
            await leaderboard_channel.send(embeds=embeds)

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

    @tasks.loop(hours=1)
    async def finalize_weekly_victory_task(self):
        """Finalize Weekly Victory for any week that's fully closed (points
        won't change anymore), finalize Monthly Victory for any month whose
        last constituent week just finalized, re-check Official Finisher
        status, then finalize the Grand Championship Leaderboard once the
        challenge has fully ended. Re-running any of this for an
        already-finalized week/month/challenge is a safe no-op (see
        WeeklyVictoryModel.finalize_week / MonthlyVictoryModel.finalize_month /
        ChampionshipModel.finalize_challenge_end), so this just catches up
        on whatever closed since the last run - including if the bot was
        offline when a week ended."""
        try:
            closed_weeks = get_closed_week_ranges()
            if not closed_weeks:
                return

            logger.info(f"🔄 Checking {len(closed_weeks)} closed week(s) for Weekly Victory...")

            closed_week_numbers = set()
            for week_start, week_end, week_number in closed_weeks:
                await WeeklyVictoryModel.finalize_week(
                    week_number, week_start, week_end, bot=self.bot
                )
                closed_week_numbers.add(week_number)

            for month_number, (_, last_week) in MONTHLY_VICTORY_WEEK_GROUPS.items():
                if last_week in closed_week_numbers:
                    await MonthlyVictoryModel.finalize_month(month_number, bot=self.bot)

            newly_qualified = await WeeklyVictoryModel.check_all_official_finishers(
                bot=self.bot
            )
            if newly_qualified:
                logger.info(f"✅ {len(newly_qualified)} new Official Finisher(s)")

            if challenge_status() == "ended":
                newly_founders = await ChampionshipModel.finalize_challenge_end(
                    bot=self.bot
                )
                if newly_founders:
                    logger.info(f"🏆 {len(newly_founders)} new Founder(s) (Grand Championship)")

        except Exception as e:
            logger.error(f"❌ Error in finalize_weekly_victory_task: {e}")

    @finalize_weekly_victory_task.before_loop
    async def before_finalize_weekly_victory(self):
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
