import discord
from discord.ext import commands
from typing import Optional

from database.models import ValuePostModel, UserModel, DailyTodoModel, CallsPostModel
from utils.logger import get_logger
from utils.helpers import is_challenge_active
from config.settings import (
    VALUE_DROPS_CHANNEL_ID,
    DAILY_TODO_CHANNEL_ID,
    CALLS_CHANNEL_ID,
)
from config.constants import POINTS, MAX_VALUE_POSTS_PER_DAY, MAX_TODO_POSTS_PER_DAY

logger = get_logger(__name__)


class Leaderboard(commands.Cog):
    """Handle reaction tracking for value posts and daily todos"""

    def __init__(self, bot):
        self.bot = bot
        self.tracked_emojis = ["🔥", "💎", "💯"]
        self.success_emoji = "✅"

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Leaderboard cog loaded")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track new value posts and daily todos"""
        if message.author.bot:
            return

        if message.channel.id == VALUE_DROPS_CHANNEL_ID:
            await self._handle_value_drop(message)
            return

        if message.channel.id == DAILY_TODO_CHANNEL_ID:
            await self._handle_daily_todo(message)
            return

        if message.channel.id == CALLS_CHANNEL_ID:
            await self._handle_calls_post(message)
            return

    async def _send_violation_log(
        self, user: discord.User, violation_type: str, limit: int, current: int
    ):
        """Send violation to Discord logging channel"""
        try:
            from config.settings import LOG_CHANNEL_ID

            if not LOG_CHANNEL_ID:
                return

            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if not log_channel:
                return

            embed = discord.Embed(
                title="Posting Limit Violation",
                description=f"{user.mention} attempted to exceed posting limits",
                color=0xFF6B6B,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(
                name="User",
                value=f"{user.mention}\n`{user.name}` (ID: {user.id})",
                inline=False,
            )
            embed.add_field(name="Violation Type", value=violation_type, inline=True)
            embed.add_field(name="Limit", value=f"{limit} per day", inline=True)
            embed.add_field(name="Attempts Today", value=str(current), inline=True)
            embed.set_thumbnail(
                url=user.display_avatar.url if user.display_avatar else None
            )
            await log_channel.send(embed=embed)

        except Exception as e:
            logger.debug(f"Could not send violation log to Discord: {e}")

    async def _send_post_log(
        self, user: discord.User, post_type: str, message_id: int, points: int
    ):
        """Send post creation to Discord logging channel"""
        try:
            from config.settings import LOG_CHANNEL_ID

            if not LOG_CHANNEL_ID:
                return

            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if not log_channel:
                return

            color = 0x5865F2 if post_type == "Daily Todo" else 0x57F287

            embed = discord.Embed(
                title=f"{post_type} Posted",
                color=color,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Points Earned", value=f"+{points}", inline=True)
            embed.add_field(name="Message ID", value=f"`{message_id}`", inline=True)
            await log_channel.send(embed=embed)

        except Exception as e:
            logger.debug(f"Could not send post log to Discord: {e}")

    async def _send_deletion_log(
        self, user_id: int, post_type: str, message_id: int, points_removed: int
    ):
        """Send post deletion to Discord logging channel"""
        try:
            from config.settings import LOG_CHANNEL_ID

            if not LOG_CHANNEL_ID:
                return

            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if not log_channel:
                return

            embed = discord.Embed(
                title="Post Deleted",
                description=f"A {post_type.lower()} was deleted",
                color=0xED4245,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="User", value=f"<@{user_id}>", inline=True)
            embed.add_field(name="Type", value=post_type, inline=True)
            embed.add_field(
                name="Points Removed", value=f"-{points_removed}", inline=True
            )
            embed.add_field(name="Message ID", value=f"`{message_id}`", inline=False)
            await log_channel.send(embed=embed)

        except Exception as e:
            logger.debug(f"Could not send deletion log to Discord: {e}")

    async def _handle_daily_todo(self, message: discord.Message):
        """Handle daily todo posts with reaction confirmation"""
        try:
            # ✅ FIX: Ignore messages after challenge ends (prevents spam flag)
            if not is_challenge_active():
                return

            posts_today = await DailyTodoModel.get_user_posts_today(message.author.id)

            if posts_today >= MAX_TODO_POSTS_PER_DAY:
                await message.delete()

                warning_msg = await message.channel.send(
                    f"Warning {message.author.mention}: You've reached the maximum of "
                    f"**{MAX_TODO_POSTS_PER_DAY} daily todo post per day**. "
                    f"Please try again tomorrow!"
                )

                logger.warning(
                    f"TODO LIMIT REACHED | User: {message.author.id} ({message.author.name}) | "
                    f"Posts Today: {posts_today} | Limit: {MAX_TODO_POSTS_PER_DAY}"
                )

                await self._send_violation_log(
                    message.author,
                    "Daily Todo",
                    MAX_TODO_POSTS_PER_DAY,
                    posts_today + 1,
                )

                await warning_msg.delete(delay=10)
                return

            await UserModel.get_or_create(message.author.id, message.author.name)
            await DailyTodoModel.create(
                message.id, message.author.id, message.channel.id
            )
            await UserModel.update_points(
                message.author.id,
                POINTS["DAILY_TODO"],
                "Daily todo posted",
                bot=self.bot,
            )
            await self._send_post_log(
                message.author, "Daily Todo", message.id, POINTS["DAILY_TODO"]
            )

            try:
                await message.add_reaction(self.success_emoji)
                logger.info(
                    f"TODO POST SUCCESS | User: {message.author.id} ({message.author.name}) | "
                    f"Points: +{POINTS['DAILY_TODO']} | Reaction Added"
                )
            except discord.Forbidden:
                logger.warning(
                    f"REACTION FAILED | Bot lacks permission | "
                    f"User: {message.author.id} | Message: {message.id}"
                )
            except Exception as e:
                logger.error(
                    f"ERROR | Failed to add reaction | User: {message.author.id} | {e}"
                )

        except Exception as e:
            logger.error(f"ERROR | handle_daily_todo | User: {message.author.id} | {e}")

    async def _handle_calls_post(self, message: discord.Message):
        """Handle calls channel posts with automatic points and reaction"""
        try:
            # ✅ FIX: Ignore messages after challenge ends (prevents spam flag)
            if not is_challenge_active():
                return

            await UserModel.get_or_create(message.author.id, message.author.name)
            await CallsPostModel.create(
                message.id, message.author.id, message.channel.id
            )
            await UserModel.update_points(
                message.author.id,
                POINTS["CALLS_POST"],
                "Posted in calls channel",
                bot=self.bot,
            )
            await self._send_post_log(
                message.author, "Calls Post", message.id, POINTS["CALLS_POST"]
            )

            try:
                await message.add_reaction(self.success_emoji)
                logger.info(
                    f"CALLS POST SUCCESS | User: {message.author.id} ({message.author.name}) | "
                    f"Points: +{POINTS['CALLS_POST']} | Reaction Added"
                )
            except discord.Forbidden:
                logger.warning(
                    f"REACTION FAILED | Bot lacks permission | "
                    f"User: {message.author.id} | Message: {message.id}"
                )
            except Exception as e:
                logger.error(
                    f"ERROR | Failed to add reaction | User: {message.author.id} | {e}"
                )

        except Exception as e:
            logger.error(f"ERROR | handle_calls_post | User: {message.author.id} | {e}")

    async def _handle_value_drop(self, message: discord.Message):
        """Handle value drop posts"""
        try:
            # ✅ FIX: Ignore messages after challenge ends (prevents spam flag)
            if not is_challenge_active():
                return

            posts_today = await ValuePostModel.get_user_posts_today(message.author.id)

            if posts_today >= MAX_VALUE_POSTS_PER_DAY:
                await message.delete()

                warning_msg = await message.channel.send(
                    f"Warning {message.author.mention}: You've reached the maximum of "
                    f"**{MAX_VALUE_POSTS_PER_DAY} value posts per day**. "
                    f"Please try again tomorrow!"
                )

                logger.warning(
                    f"VALUE POST LIMIT REACHED | User: {message.author.id} ({message.author.name}) | "
                    f"Posts Today: {posts_today} | Limit: {MAX_VALUE_POSTS_PER_DAY}"
                )

                await self._send_violation_log(
                    message.author,
                    "Value Drop",
                    MAX_VALUE_POSTS_PER_DAY,
                    posts_today + 1,
                )

                await warning_msg.delete(delay=10)
                return

            await UserModel.get_or_create(message.author.id, message.author.name)
            await ValuePostModel.create_or_update(
                message.id, message.author.id, message.channel.id
            )

            logger.info(
                f"VALUE POST TRACKED | User: {message.author.id} ({message.author.name}) | "
                f"Message: {message.id}"
            )

            await self._send_post_log(message.author, "Value Drop", message.id, 0)

        except Exception as e:
            logger.error(f"ERROR | handle_value_drop | User: {message.author.id} | {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction_change(payload, "added")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction_change(payload, "removed")

    async def _handle_reaction_change(
        self, payload: discord.RawReactionActionEvent, action: str = "changed"
    ):
        """Process reaction changes"""
        try:
            emoji_str = str(payload.emoji)
            if emoji_str not in self.tracked_emojis:
                return

            if payload.channel_id != VALUE_DROPS_CHANNEL_ID:
                return

            channel = self.bot.get_channel(payload.channel_id)
            if not channel:
                return

            message = await channel.fetch_message(payload.message_id)
            if message.author.bot:
                return

            fire_count = 0
            gem_count = 0
            hundred_count = 0

            for reaction in message.reactions:
                emoji = str(reaction.emoji)
                if emoji == "🔥":
                    fire_count = reaction.count
                elif emoji == "💎":
                    gem_count = reaction.count
                elif emoji == "💯":
                    hundred_count = reaction.count

            logger.debug(
                f"REACTION {action.upper()} | Message: {message.id} | Emoji: {emoji_str} | "
                f"Current: Fire:{fire_count} Gem:{gem_count} 100:{hundred_count}"
            )

            await ValuePostModel.update_reactions(
                message.id, fire_count, gem_count, hundred_count, bot=self.bot
            )

        except discord.NotFound:
            logger.warning(
                f"REACTION UPDATE FAILED | Message {payload.message_id} not found"
            )
        except Exception as e:
            logger.error(
                f"ERROR | handle_reaction_change | Message: {payload.message_id} | {e}"
            )

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """Handle message deletions"""
        try:
            from database.supabase_client import get_supabase

            supabase = get_supabase()

            value_response = (
                supabase.table("value_posts")
                .select("*")
                .eq("message_id", payload.message_id)
                .execute()
            )

            if value_response.data:
                post = value_response.data[0]
                if post["total_points"] > 0:
                    await UserModel.update_points(
                        post["user_id"],
                        -post["total_points"],
                        "Value post deleted",
                        bot=self.bot,
                    )
                    logger.info(
                        f"VALUE POST DELETED | User: {post['user_id']} | "
                        f"Message: {payload.message_id} | Points Removed: -{post['total_points']}"
                    )
                    await self._send_deletion_log(
                        post["user_id"],
                        "Value Post",
                        payload.message_id,
                        post["total_points"],
                    )
                supabase.table("value_posts").delete().eq(
                    "message_id", payload.message_id
                ).execute()
                return

            todo_response = (
                supabase.table("daily_todos")
                .select("*")
                .eq("message_id", payload.message_id)
                .execute()
            )

            if todo_response.data:
                post = todo_response.data[0]
                await UserModel.update_points(
                    post["user_id"],
                    -POINTS["DAILY_TODO"],
                    "Daily todo deleted",
                    bot=self.bot,
                )
                logger.info(
                    f"TODO POST DELETED | User: {post['user_id']} | "
                    f"Message: {payload.message_id} | Points Removed: -{POINTS['DAILY_TODO']}"
                )
                await self._send_deletion_log(
                    post["user_id"],
                    "Daily Todo",
                    payload.message_id,
                    POINTS["DAILY_TODO"],
                )
                supabase.table("daily_todos").delete().eq(
                    "message_id", payload.message_id
                ).execute()
                return

            calls_response = (
                supabase.table("calls_posts")
                .select("*")
                .eq("message_id", payload.message_id)
                .execute()
            )

            if calls_response.data:
                post = calls_response.data[0]
                await UserModel.update_points(
                    post["user_id"],
                    -POINTS["CALLS_POST"],
                    "Calls post deleted",
                    bot=self.bot,
                )
                logger.info(
                    f"CALLS POST DELETED | User: {post['user_id']} | "
                    f"Message: {payload.message_id} | Points Removed: -{POINTS['CALLS_POST']}"
                )
                await self._send_deletion_log(
                    post["user_id"],
                    "Calls Post",
                    payload.message_id,
                    POINTS["CALLS_POST"],
                )
                supabase.table("calls_posts").delete().eq(
                    "message_id", payload.message_id
                ).execute()

        except Exception as e:
            logger.error(
                f"ERROR | handle_message_deletion | Message: {payload.message_id} | {e}"
            )

    @commands.Cog.listener()
    async def on_guild_channel_pins_update(
        self, channel: discord.TextChannel, last_pin: Optional[discord.datetime]
    ):
        if channel.id != VALUE_DROPS_CHANNEL_ID:
            return

        try:
            from database.supabase_client import get_supabase
            from config.settings import LOG_CHANNEL_ID

            pinned_messages = await channel.pins()
            pinned_ids = [msg.id for msg in pinned_messages]

            supabase = get_supabase()
            response = (
                supabase.table("value_posts")
                .select("*")
                .eq("channel_id", channel.id)
                .execute()
            )

            for post in response.data:
                message_id = post["message_id"]
                was_pinned = post["is_pinned"]
                is_pinned = message_id in pinned_ids

                if was_pinned != is_pinned:
                    supabase.table("value_posts").update({"is_pinned": is_pinned}).eq(
                        "message_id", message_id
                    ).execute()

                    points_change = POINTS["PINNED"] if is_pinned else -POINTS["PINNED"]
                    await UserModel.update_points(
                        post["user_id"],
                        points_change,
                        "Post pinned" if is_pinned else "Post unpinned",
                        bot=self.bot,
                    )

                    new_total = post["total_points"] + points_change
                    supabase.table("value_posts").update(
                        {"total_points": new_total}
                    ).eq("message_id", message_id).execute()

                    logger.info(
                        f"POST {'PINNED' if is_pinned else 'UNPINNED'} | "
                        f"User: {post['user_id']} | Message: {message_id} | "
                        f"Points Change: {points_change:+d}"
                    )

                    if LOG_CHANNEL_ID:
                        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
                        if log_channel:
                            embed = discord.Embed(
                                title=f"Post {'Pinned' if is_pinned else 'Unpinned'}",
                                color=0xFEE75C if is_pinned else 0x747F8D,
                                timestamp=discord.utils.utcnow(),
                            )
                            embed.add_field(
                                name="User", value=f"<@{post['user_id']}>", inline=True
                            )
                            embed.add_field(
                                name="Points Change",
                                value=f"{points_change:+d}",
                                inline=True,
                            )
                            embed.add_field(
                                name="New Total", value=str(new_total), inline=True
                            )
                            embed.add_field(
                                name="Message ID", value=f"`{message_id}`", inline=False
                            )
                            await log_channel.send(embed=embed)

        except Exception as e:
            logger.error(f"ERROR | handle_pin_update | Channel: {channel.id} | {e}")


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
