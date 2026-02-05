# Fix Windows console encoding FIRST - before any other imports
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import discord
from discord.ext import commands
import asyncio
from pathlib import Path

from config.settings import DISCORD_TOKEN, GUILD_ID
from database.supabase_client import supabase_client
from utils.logger import setup_logger, get_logger

# Setup logger
setup_logger()
logger = get_logger(__name__)


class RunItUpBot(commands.Bot):
    """Main bot class"""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        intents.members = True
        intents.reactions = True

        super().__init__(
            command_prefix="!",  # Prefix for text commands (not used much)
            intents=intents,
            help_command=None,
        )

        self.initial_extensions = [
            "cogs.members",
            "cogs.submissions",
            "cogs.admin",
            "cogs.leaderboard",
            "cogs.tasks",
        ]

    async def setup_hook(self):
        """Setup hook called when bot is starting"""
        logger.info("🔧 Running setup hook...")

        # Initialize Supabase
        try:
            supabase_client.initialize()
            logger.info("✅ Supabase client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase: {e}")
            sys.exit(1)

        # Load cogs
        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"✅ Loaded extension: {extension}")
            except Exception as e:
                logger.error(f"❌ Failed to load extension {extension}: {e}")

        # Sync commands to guild for faster updates during development
        try:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"✅ Commands synced to guild {GUILD_ID}")
        except Exception as e:
            logger.error(f"❌ Failed to sync commands: {e}")

    async def on_ready(self):
        """Called when bot is ready"""
        logger.info("=" * 50)
        logger.info(f"✅ Bot is ready!")
        logger.info(f"📛 Logged in as: {self.user.name} ({self.user.id})")
        logger.info(f"🔗 Connected to {len(self.guilds)} guild(s)")
        logger.info(f"👥 Serving {len(self.users)} users")
        logger.info("=" * 50)

        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="RunItUp Q1 Challenge 🔥"
            )
        )

    async def on_command_error(self, ctx, error):
        """Global error handler"""
        if isinstance(error, commands.CommandNotFound):
            return

        logger.error(f"❌ Command error: {error}")

    async def on_application_command_error(
        self, interaction: discord.Interaction, error
    ):
        """Global slash command error handler"""
        logger.error(f"❌ Slash command error: {error}")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ An error occurred while processing your command. Please try again.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "❌ An error occurred while processing your command. Please try again.",
                    ephemeral=True,
                )
        except:
            pass


async def main():
    """Main function to run the bot"""
    bot = RunItUpBot()

    try:
        logger.info("🚀 Starting RunItUp Challenge Bot...")
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("⚠️ Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        await bot.close()
        logger.info("👋 Bot shut down successfully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
