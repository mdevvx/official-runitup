import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

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

    WEBHOOK_NAME = "Wins Relay"

    def __init__(self, bot):
        self.bot = bot
        self._webhooks: dict[int, discord.Webhook] = {}
        logger.info("WinsRelay cog loaded")

    async def _get_webhook(
        self, channel: discord.TextChannel, force_refresh: bool = False
    ) -> Optional[discord.Webhook]:
        """Get the relay's webhook for a channel, cached per channel so we
        don't re-resolve it on every message.

        Prefers a URL registered via /relaywebhookseturl: Discord's list-
        webhooks endpoint never includes a webhook's token (only the
        response from *creating* one does), so a webhook found via
        channel.webhooks() can never actually send - it'll fail with
        "This webhook does not have a token associated with it". Building
        from the URL instead carries the token straight through.

        Falls back to list-or-create when no URL is registered, but note
        that path only works for channels without aggressive webhook
        auto-moderation - some servers run a "webhook protection" bot that
        deletes any webhook a bot creates within milliseconds, which is
        exactly why the URL-registration path exists.

        force_refresh=True skips the cache and re-resolves - used when the
        cached webhook turned out to be gone/invalid (the cache is
        in-memory only, so it has no way to notice that on its own)."""
        if not force_refresh:
            cached = self._webhooks.get(channel.id)
            if cached:
                return cached

        from database.bot_config import BotConfigModel

        stored_url = BotConfigModel.get_webhook_url(channel.id)
        if stored_url:
            try:
                webhook = discord.Webhook.from_url(stored_url, client=self.bot)
            except ValueError:
                logger.error(
                    f"WINS RELAY FAILED | Registered webhook URL for #{channel.name} "
                    f"({channel.id}) is malformed - re-register with /relaywebhookseturl."
                )
                return None
            self._webhooks[channel.id] = webhook
            return webhook

        try:
            existing = await channel.webhooks()
            webhook = next((w for w in existing if w.name == self.WEBHOOK_NAME), None)
            if webhook is None:
                webhook = await channel.create_webhook(name=self.WEBHOOK_NAME)
        except discord.Forbidden:
            logger.error(
                f"WINS RELAY FAILED | Missing 'Manage Webhooks' permission in "
                f"#{channel.name} ({channel.id})"
            )
            return None

        self._webhooks[channel.id] = webhook
        return webhook

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
        """Relay a win message to the given destination channel via a
        webhook impersonating the original author (their display name +
        avatar), so it reads as a native post rather than a bot embed.
        Returns True on success. Does not add any confirmation reaction
        itself - callers do that, since what the reaction *means* depends
        on which destination/pipeline is calling (live relay vs. one-time
        backfill)."""
        try:
            destination = self.bot.get_channel(destination_channel_id)

            if not destination:
                logger.error(
                    f"WINS RELAY FAILED | Destination channel {destination_channel_id} "
                    "not found. Check the channel ID and that the bot is in that server."
                )
                return False

            # Forward any rich embeds from the original (link previews, etc.)
            embeds = [e for e in message.embeds if e.type in ("rich", "article", "link")]

            # Up to 2 attempts: if the cached webhook was deleted on
            # Discord's side (e.g. someone cleaned it up manually), the
            # in-memory cache has no way to know - retry once with a freshly
            # created webhook before giving up.
            for attempt in range(2):
                webhook = await self._get_webhook(
                    destination, force_refresh=(attempt == 1)
                )
                if not webhook:
                    return False

                # Re-download and re-upload attachments rather than linking
                # the original CDN URLs - Discord attachment URLs are signed
                # and expire, so old backfilled links would eventually
                # break. Built fresh each attempt since discord.File streams
                # are single-use.
                files = []
                for attachment in message.attachments:
                    try:
                        files.append(await attachment.to_file())
                    except (discord.HTTPException, discord.NotFound):
                        pass  # Source attachment no longer available - skip it

                try:
                    await webhook.send(
                        content=message.content or None,
                        username=message.author.display_name,
                        avatar_url=message.author.display_avatar.url,
                        files=files,
                        embeds=embeds,
                        # Cross-server mentions don't resolve to anyone
                        # meaningful in RunItUp and could accidentally ping
                        # the wrong person - suppress all of them.
                        allowed_mentions=discord.AllowedMentions.none(),
                        wait=True,
                    )
                except discord.NotFound:
                    self._webhooks.pop(destination.id, None)
                    if attempt == 0:
                        logger.warning(
                            f"WINS RELAY | Cached webhook for #{destination.name} "
                            "no longer exists on Discord - recreating and "
                            "retrying once."
                        )
                        continue
                    raise

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
        force: bool = False,
    ) -> tuple[int, int, int]:
        """One-time migration: walk Dialed #wins history oldest-first and
        copy everything not already marked 📥 into destination_channel_id.
        Deliberately ignores the live relay's 🏆 marker - this is meant to
        copy the *full* history into a (possibly different) channel, not
        just what the live automation hasn't already handled elsewhere.

        force=True re-copies everything regardless of the 📥 marker. Needed
        because the marker only tracks "did we send this," not "does a copy
        still exist at the destination" - if the destination copies get
        deleted (e.g. to redo the formatting), the source messages are
        still marked as done and would otherwise be skipped forever.

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
            if not force and self._already_backfilled(message):
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
    force="Re-copy everything, even posts already marked as backfilled (use after deleting a prior attempt)",
)
async def relay_wins_backfill(
    interaction: discord.Interaction,
    destination: discord.TextChannel,
    limit: Optional[int] = None,
    force: bool = False,
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
            destination_channel_id=destination.id, limit=limit, force=force
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


@app_commands.command(
    name="relaywebhookseturl",
    description="[ADMIN] Register a manually-created webhook URL for a relay destination channel",
)
@app_commands.describe(
    channel="The channel this webhook posts into",
    url="The webhook's URL, from Channel Settings → Integrations → Webhooks → Copy Webhook URL",
)
async def relay_webhook_set_url(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    url: str,
):
    if not await has_admin_role(interaction):
        await send_error_embed(
            interaction, "❌ You don't have permission to use admin commands."
        )
        return

    try:
        discord.Webhook.from_url(url, client=interaction.client)
    except ValueError:
        await send_error_embed(
            interaction, "❌ That doesn't look like a valid Discord webhook URL."
        )
        return

    from database.bot_config import BotConfigModel

    await BotConfigModel.set_webhook_url(channel.id, url, updated_by=interaction.user.id)

    cog = interaction.client.get_cog("WinsRelay")
    if cog:
        # Drop any cached webhook for this channel so the new URL takes
        # effect immediately instead of waiting for a NotFound to evict it.
        cog._webhooks.pop(channel.id, None)

    await interaction.response.send_message(
        f"✅ Registered a webhook for {channel.mention}. The relay will use it from now on.",
        ephemeral=True,
    )


async def setup(bot):
    await bot.add_cog(WinsRelay(bot))
    # Standalone top-level commands, deliberately not under /<season> -
    # this relay is permanent cross-server infra, not a per-season
    # challenge mechanic, so it shouldn't get renamed every time
    # CURRENT_SEASON changes.
    bot.tree.add_command(relay_wins_backfill)
    bot.tree.add_command(relay_webhook_set_url)
