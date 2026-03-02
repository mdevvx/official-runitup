import discord
from discord.ext import commands
from datetime import datetime, timezone
from config.constants import BRAND_COLOR

from utils.logger import get_logger
from config.settings import (
    DIALED_GUILD_ID,
    DIALED_WINS_CHANNEL_ID,
    RUNITUP_WINS_CHANNEL_ID,
)

logger = get_logger(__name__)


class WinsRelay(commands.Cog):
    """Cross-server wins relay: Dialed #wins → RunItUp #wins"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ WinsRelay cog loaded")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for new posts in Dialed #wins and relay to RunItUp #wins"""

        # Ignore bots
        if message.author.bot:
            return

        # Only trigger on the Dialed server's wins channel
        if message.guild is None:
            return
        if message.guild.id != DIALED_GUILD_ID:
            return
        if message.channel.id != DIALED_WINS_CHANNEL_ID:
            return

        # Only relay direct messages, not replies
        if message.reference is not None:
            return

        await self._relay_win(message)

    async def _relay_win(self, message: discord.Message):
        """Relay a win message to RunItUp #wins"""
        try:
            # Get the destination channel in RunItUp
            destination = self.bot.get_channel(RUNITUP_WINS_CHANNEL_ID)

            if not destination:
                logger.error(
                    "WINS RELAY FAILED | RunItUp #wins channel not found. "
                    "Check RUNITUP_WINS_CHANNEL_ID and that the bot is in the RunItUp server."
                )
                return

            # Build the relay embed
            embed = discord.Embed(
                description=message.content or "",
                color=BRAND_COLOR,
            )

            # embed.set_author(
            #     name=f"{message.author.display_name} • from Dialed",
            #     icon_url=(
            #         message.author.display_avatar.url
            #         if message.author.display_avatar
            #         else None
            #     ),
            # )

            # embed.set_footer(
            #     text=f"🔗 Dialed Win  •  #{message.channel.name}",
            # )
            embed.set_author(
                name=f"{message.author.display_name} (@{message.author.name})",
                icon_url=(
                    message.author.display_avatar.url
                    if message.author.display_avatar
                    else None
                ),
            )

            embed.set_footer(
                text=f"🔗 Dialed Win  •  #{message.channel.name}",
            )

            # Attach the first image inline if present
            image_attached = False
            other_attachments = []

            for attachment in message.attachments:
                if (
                    not image_attached
                    and attachment.content_type
                    and attachment.content_type.startswith("image/")
                ):
                    embed.set_image(url=attachment.url)
                    image_attached = True
                else:
                    other_attachments.append(attachment.url)

            # Add extra attachment links if any
            if other_attachments:
                embed.add_field(
                    name="📎 Additional Attachments",
                    value="\n".join(other_attachments),
                    inline=False,
                )

            # Forward any embeds from the original message (e.g. link previews)
            original_embeds = message.embeds  # up to 10

            # Send the relay embed
            await destination.send(embed=embed)

            # Re-send any rich embeds from the original (link previews, etc.)
            for original_embed in original_embeds:
                # Skip empty embeds
                if original_embed.type in ("rich", "article", "link"):
                    try:
                        await destination.send(embed=original_embed)
                    except Exception:
                        pass  # Don't fail the whole relay over a preview

            logger.info(
                f"WINS RELAY SUCCESS | Author: {message.author} ({message.author.id}) | "
                f"Message: {message.id} | Destination: {destination.guild.name} #{destination.name}"
            )

            # React to the original message to confirm relay
            try:
                await message.add_reaction("🏆")
            except discord.Forbidden:
                pass  # Bot may lack reaction perms in Dialed — not critical

        except discord.Forbidden:
            logger.error(
                f"WINS RELAY FAILED | Missing permissions to post in RunItUp #wins | "
                f"Message: {message.id}"
            )
        except Exception as e:
            logger.error(f"WINS RELAY ERROR | Message: {message.id} | {e}")


async def setup(bot):
    await bot.add_cog(WinsRelay(bot))
