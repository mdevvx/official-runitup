import discord
from discord.ext import commands
from typing import Optional

from database.models import ValuePostModel, UserModel
from utils.logger import get_logger
from config.settings import VALUE_DROPS_CHANNEL_ID
from config.constants import POINTS, MAX_VALUE_POSTS_PER_DAY

logger = get_logger(__name__)


class Leaderboard(commands.Cog):
    """Handle reaction tracking for value posts"""

    def __init__(self, bot):
        self.bot = bot
        self.tracked_emojis = ["🔥", "💎", "💯"]

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Leaderboard cog loaded")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track new value posts"""
        # Ignore bots
        if message.author.bot:
            return

        # Only track in value-drops channel
        if message.channel.id != VALUE_DROPS_CHANNEL_ID:
            return

        try:
            # Check daily post limit
            posts_today = await ValuePostModel.get_user_posts_today(message.author.id)

            if posts_today >= MAX_VALUE_POSTS_PER_DAY:
                # Delete the message
                await message.delete()

                # Send visible notification in the channel (will auto-delete)
                warning_msg = await message.channel.send(
                    f"⚠️ {message.author.mention} You've reached the maximum of **{MAX_VALUE_POSTS_PER_DAY} value posts per day**. "
                    f"Your message was removed. Please try again tomorrow!"
                )

                # Also try to DM them
                try:
                    await message.author.send(
                        f"⚠️ You've reached the maximum of {MAX_VALUE_POSTS_PER_DAY} value posts per day.\n\n"
                        f"Your message in <#{VALUE_DROPS_CHANNEL_ID}> was removed. "
                        f"Please try again tomorrow!"
                    )
                except:
                    pass  # If DM fails, at least they saw the channel message

                logger.info(
                    f"⚠️ Blocked {message.author.name} from posting (daily limit reached)"
                )

                # Delete warning message after 10 seconds to keep channel clean
                await warning_msg.delete(delay=10)
                return

            # Ensure user exists
            await UserModel.get_or_create(message.author.id, message.author.name)

            # Create value post record
            await ValuePostModel.create_or_update(
                message.id, message.author.id, message.channel.id
            )

            logger.info(f"✅ Tracking new value post from {message.author.name}")

        except Exception as e:
            logger.error(f"❌ Error tracking value post: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reaction additions"""
        await self._handle_reaction_change(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Handle reaction removals"""
        await self._handle_reaction_change(payload)

    async def _handle_reaction_change(self, payload: discord.RawReactionActionEvent):
        """Process reaction changes"""
        try:
            # Only track specific emojis
            emoji_str = str(payload.emoji)
            if emoji_str not in self.tracked_emojis:
                return

            # Only track in value-drops channel
            if payload.channel_id != VALUE_DROPS_CHANNEL_ID:
                return

            # Get the message
            channel = self.bot.get_channel(payload.channel_id)
            if not channel:
                return

            message = await channel.fetch_message(payload.message_id)

            # Don't track reactions on bot's own messages
            if message.author.bot:
                return

            # Count all tracked emoji reactions
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

            # Update value post with bot instance for role updates
            await ValuePostModel.update_reactions(
                message.id, fire_count, gem_count, hundred_count, bot=self.bot
            )

            logger.debug(
                f"✅ Updated reactions for message {message.id}: 🔥{fire_count} 💎{gem_count} 💯{hundred_count}"
            )

        except discord.NotFound:
            logger.warning(f"⚠️ Message {payload.message_id} not found")
        except Exception as e:
            logger.error(f"❌ Error handling reaction change: {e}")

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """Handle message deletions"""
        try:
            from database.supabase_client import get_supabase

            # Check if it was a tracked value post
            supabase = get_supabase()
            response = (
                supabase.table("value_posts")
                .select("*")
                .eq("message_id", payload.message_id)
                .execute()
            )

            if response.data:
                post = response.data[0]

                # Remove points from user if they had any (with bot instance)
                if post["total_points"] > 0:
                    await UserModel.update_points(
                        post["user_id"],
                        -post["total_points"],
                        "Value post deleted",
                        bot=self.bot,
                    )

                # Delete the post record
                supabase.table("value_posts").delete().eq(
                    "message_id", payload.message_id
                ).execute()

                logger.info(f"✅ Removed deleted value post and adjusted points")

        except Exception as e:
            logger.error(f"❌ Error handling message deletion: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_pins_update(
        self, channel: discord.TextChannel, last_pin: Optional[discord.datetime]
    ):
        """Handle pin updates"""
        if channel.id != VALUE_DROPS_CHANNEL_ID:
            return

        try:
            from database.supabase_client import get_supabase

            # Get all pinned messages
            pinned_messages = await channel.pins()
            pinned_ids = [msg.id for msg in pinned_messages]

            supabase = get_supabase()

            # Get all value posts in this channel
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

                # If pin status changed
                if was_pinned != is_pinned:
                    # Update database
                    supabase.table("value_posts").update({"is_pinned": is_pinned}).eq(
                        "message_id", message_id
                    ).execute()

                    # Award or remove pin points (with bot instance)
                    points_change = POINTS["PINNED"] if is_pinned else -POINTS["PINNED"]

                    await UserModel.update_points(
                        post["user_id"],
                        points_change,
                        "Post pinned" if is_pinned else "Post unpinned",
                        bot=self.bot,
                    )

                    # Recalculate total post points
                    new_total = post["total_points"] + points_change
                    supabase.table("value_posts").update(
                        {"total_points": new_total}
                    ).eq("message_id", message_id).execute()

                    logger.info(
                        f"✅ {'Pinned' if is_pinned else 'Unpinned'} post {message_id}: {points_change:+d} points"
                    )

        except Exception as e:
            logger.error(f"❌ Error handling pin update: {e}")


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
