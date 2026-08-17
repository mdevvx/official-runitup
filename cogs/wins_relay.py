import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from config.constants import BRAND_COLOR

from utils.logger import get_logger
from utils.helpers import has_admin_role, send_error_embed
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
        logger.info("WinsRelay cog loaded")

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

        if await self._relay_win(message, RUNITUP_WINS_CHANNEL_ID):
            # Confirms to the live automation's destination specifically -
            # not reused by the backfill command, which targets a
            # different channel and tracks its own progress separately
            # (see _already_backfilled / the 📥 reaction below).
            try:
                await message.add_reaction("🏆")
            except discord.Forbidden:
                pass  # Bot may lack reaction perms in Dialed — not critical

    async def _relay_win(
        self, message: discord.Message, destination_channel_id: int
    ) -> bool:
        """Relay a win message to the given destination channel. Returns
        True on success. Does not add any confirmation reaction itself -
        callers do that, since what the reaction *means* depends on which
        destination/pipeline is calling (live relay vs. one-time backfill)."""
        try:
            destination = self.bot.get_channel(destination_channel_id)

            if not destination:
                logger.error(
                    f"WINS RELAY FAILED | Destination channel {destination_channel_id} "
                    "not found. Check the channel ID and that the bot is in that server."
                )
                return False

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
            return True

        except discord.Forbidden:
            logger.error(
                f"WINS RELAY FAILED | Missing permissions to post in destination channel | "
                f"Message: {message.id}"
            )
            return False
        except Exception as e:
            logger.error(f"WINS RELAY ERROR | Message: {message.id} | {e}")
            return False

    BACKFILL_MARK = "📥"

    @classmethod
    def _already_backfilled(cls, message: discord.Message) -> bool:
        """True if a previous /relaywinsbackfill run already copied this
        message - it stamps a 📥 reaction on success. Kept separate from the
        live relay's 🏆 marker on purpose: 🏆 means "sent to the live
        automation's channel", 📥 means "sent to the backfill's channel" -
        they can be different channels, so one marker can't stand in for
        the other. This is what makes re-running the backfill idempotent."""
        for reaction in message.reactions:
            if str(reaction.emoji) == cls.BACKFILL_MARK and reaction.me:
                return True
        return False

    async def backfill(
        self,
        destination_channel_id: int,
        limit: Optional[int] = None,
        delay_seconds: float = 1.0,
    ) -> tuple[int, int, int]:
        """One-time migration: walk Dialed #wins history oldest-first and
        copy everything not already marked 📥 into destination_channel_id.
        Deliberately ignores the live relay's 🏆 marker - this is meant to
        copy the *full* history into a (possibly different) channel, not
        just what the live automation hasn't already handled elsewhere.
        Returns (relayed, skipped, failed)."""
        source = self.bot.get_channel(DIALED_WINS_CHANNEL_ID)
        if not source:
            raise RuntimeError(
                "Dialed wins channel not found - check DIALED_WINS_CHANNEL_ID "
                "and that the bot is still in the Dialed server."
            )

        relayed = skipped = failed = 0

        async for message in source.history(limit=limit, oldest_first=True):
            if message.author.bot:
                continue
            if message.reference is not None:
                continue
            if self._already_backfilled(message):
                skipped += 1
                continue

            success = await self._relay_win(message, destination_channel_id)
            if success:
                relayed += 1
                try:
                    await message.add_reaction(self.BACKFILL_MARK)
                except discord.Forbidden:
                    pass  # Bot may lack reaction perms in Dialed — not critical
            else:
                failed += 1

            total = relayed + skipped + failed
            if total % 25 == 0:
                # Large channels can take longer than the 15-minute Discord
                # interaction token lifetime - the command's final followup
                # may fail even though the run itself succeeded, so progress
                # goes to the log too, not just the eventual Discord reply.
                logger.info(
                    f"WINS BACKFILL PROGRESS | {total} scanned | "
                    f"{relayed} relayed | {skipped} skipped | {failed} failed"
                )

            # Stay well clear of rate limits - each win can send several messages
            await asyncio.sleep(delay_seconds)

        logger.info(
            f"WINS BACKFILL COMPLETE | {relayed} relayed | {skipped} skipped | {failed} failed"
        )
        return relayed, skipped, failed


@app_commands.command(
    name="relaywinsbackfill",
    description="[ADMIN] One-time: copy Dialed #wins history into a chosen RunItUp channel",
)
@app_commands.describe(
    destination="RunItUp channel to copy the history into (e.g. #ecom-wins)",
    limit="Max messages to scan, oldest first (leave blank for the full channel)",
)
async def relay_wins_backfill(
    interaction: discord.Interaction,
    destination: discord.TextChannel,
    limit: Optional[int] = None,
):
    if not await has_admin_role(interaction):
        await send_error_embed(
            interaction, "❌ You don't have permission to use admin commands."
        )
        return

    cog = interaction.client.get_cog("WinsRelay")
    if not cog:
        await send_error_embed(interaction, "❌ WinsRelay cog isn't loaded.")
        return

    await interaction.response.defer(ephemeral=True)

    try:
        relayed, skipped, failed = await cog.backfill(
            destination_channel_id=destination.id, limit=limit
        )
    except Exception as e:
        logger.error(f"WINS BACKFILL FAILED | {e}")
        try:
            await interaction.followup.send(f"❌ Backfill failed: {e}", ephemeral=True)
        except discord.HTTPException:
            pass  # Interaction token may have expired on a long-running attempt
        return

    try:
        await interaction.followup.send(
            f"✅ Backfill into {destination.mention} complete.\n"
            f"• Relayed: **{relayed}**\n"
            f"• Already backfilled (skipped): **{skipped}**\n"
            f"• Failed: **{failed}**",
            ephemeral=True,
        )
    except discord.HTTPException:
        # Discord interaction tokens expire after ~15 minutes - on a large
        # channel the backfill itself still completed fine (see the
        # WINS BACKFILL COMPLETE log line), just this final reply didn't land.
        logger.warning(
            "WINS BACKFILL | Completed but the interaction reply failed "
            "(token likely expired) - see WINS BACKFILL COMPLETE above for final counts."
        )


async def setup(bot):
    await bot.add_cog(WinsRelay(bot))
    # Standalone top-level command, deliberately not under /<season> -
    # this relay is permanent cross-server infra, not a per-season
    # challenge mechanic, so it shouldn't get renamed every time
    # CURRENT_SEASON changes.
    bot.tree.add_command(relay_wins_backfill)
