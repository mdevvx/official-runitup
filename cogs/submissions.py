import discord
from discord.ext import commands

from utils.logger import get_logger

logger = get_logger(__name__)


class Submissions(commands.Cog):
    """Handle submission views (commands removed)"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("✅ Submissions cog loaded")


async def setup(bot):
    await bot.add_cog(Submissions(bot))
