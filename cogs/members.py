import discord
from discord import app_commands
from discord.ext import commands
from typing import Literal, Optional

from database.models import (
    UserModel,
    DailyActivityModel,
    WeeklyVictoryModel,
    MonthlyVictoryModel,
    RaffleTicketModel,
    RaffleDrawModel,
)
from database.bot_config import BotConfigModel
from utils.logger import get_logger
from utils.embeds import (
    create_user_stats_embed,
    create_leaderboard_embed,
    create_winners_list_embed,
    create_raffle_draw_embed,
)
from utils.helpers import (
    is_challenge_active,
    challenge_status,
    get_current_week_range,
    get_challenge_week_ranges,
    get_current_month_range,
    get_closed_week_ranges,
    get_tier_emoji,
    get_tier_role_mention,
)
from config.constants import (
    BRAND_COLOR,
    CURRENT_SEASON,
    SEASON_PREFIX,
    TIERS,
    MONTHLY_VICTORY_WEEK_GROUPS,
    RAFFLE_DRAW_TIERS,
)
from cogs.season_group import season_group

logger = get_logger(__name__)


class Members(commands.Cog):
    """Member commands for the RunItUp Challenge (slash commands live under season_group)"""

    def __init__(self, bot):
        self.bot = bot
        logger.info("Members cog loaded")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track daily activity on messages"""
        if message.author.bot:
            return

        if not message.guild:
            return

        if not is_challenge_active():
            return

        try:
            await UserModel.get_or_create(message.author.id, message.author.name)
            await DailyActivityModel.track_activity(message.author.id)

            awarded = await DailyActivityModel.award_daily_point(
                message.author.id, bot=self.bot
            )

            if awarded:
                logger.info(f"✅ Awarded daily activity point to {message.author.name}")

        except Exception as e:
            logger.error(f"❌ Error tracking activity for {message.author.name}: {e}")


async def setup(bot):
    await bot.add_cog(Members(bot))


# ----------------------------------------------------------------------
# Live Q2 commands
# ----------------------------------------------------------------------


@season_group.command(name="points", description="Check your points and stats")
async def points(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        user_data = await UserModel.get_or_create(
            interaction.user.id, interaction.user.name
        )

        weeks_won = await WeeklyVictoryModel.get_weeks_won(interaction.user.id)
        total_weeks = len(get_challenge_week_ranges())
        months_won = await MonthlyVictoryModel.get_months_won(interaction.user.id)
        total_months = len(MONTHLY_VICTORY_WEEK_GROUPS)

        embed = create_user_stats_embed(
            user_data,
            discord_user=interaction.user,
            guild=interaction.guild,
            weeks_won=weeks_won,
            total_weeks=total_weeks or None,
            months_won=months_won,
            total_months=total_months or None,
        )

        leaderboard_data = await UserModel.get_leaderboard(limit=100)
        rank = next(
            (
                i + 1
                for i, u in enumerate(leaderboard_data)
                if u["user_id"] == interaction.user.id
            ),
            None,
        )

        if rank:
            embed.add_field(
                name="🏅 Rank", value=f"**#{rank}** of {len(leaderboard_data)}", inline=True
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"❌ Error in points command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching your points.", ephemeral=True
        )


@season_group.command(name="leaderboard", description="View the leaderboard")
@app_commands.describe(
    limit="Number of users to show (max 25)",
    scope="Season-long ranking (default), this week's points, or this month's points",
)
async def leaderboard(
    interaction: discord.Interaction,
    limit: Optional[int] = 10,
    scope: Optional[Literal["season", "week", "month"]] = "season",
):
    try:
        await interaction.response.defer()

        status = challenge_status()
        status_messages = {
            "not_started": "📅 The challenge hasn't started yet — check back once it begins!",
            "ended": "🏁 The challenge has ended.",
        }
        if status in status_messages:
            await interaction.followup.send(status_messages[status])
            return

        if limit < 1 or limit > 25:
            limit = 10

        if scope == "week":
            week_range = get_current_week_range()
            if not week_range:
                await interaction.followup.send(
                    "📅 The weekly leaderboard isn't available yet — check back once the challenge is underway."
                )
                return
            _, _, week_number = week_range

            users = await UserModel.get_weekly_leaderboard(limit=limit)
            embed = create_leaderboard_embed(
                users,
                title=f"📅 WEEK {week_number} LEADERBOARD",
                description=f"Top performers this week in the {CURRENT_SEASON} Challenge",
                footer_text=f"{CURRENT_SEASON} Challenge • Week {week_number}",
            )
        elif scope == "month":
            month_range = get_current_month_range()
            if not month_range:
                await interaction.followup.send(
                    "📅 There's no active Monthly Victory month right now "
                    "(some weeks, like the last leftover ones, don't belong to a month)."
                )
                return
            month_start, month_end, month_number = month_range

            users = await UserModel.get_monthly_leaderboard(month_start, month_end, limit=limit)
            embed = create_leaderboard_embed(
                users,
                title=f"🗓️ MONTH {month_number} LEADERBOARD",
                description=f"Top performers this month in the {CURRENT_SEASON} Challenge",
                footer_text=f"{CURRENT_SEASON} Challenge • Month {month_number}",
            )
        else:
            users = await UserModel.get_leaderboard(limit=limit)
            embed = create_leaderboard_embed(users, title=f"🏆 TOP {len(users)} LEADERBOARD")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"❌ Error in leaderboard command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching the leaderboard.", ephemeral=True
        )


@season_group.command(name="mytier", description="Check your current tier and progress")
async def mytier(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        user_data = await UserModel.get_or_create(
            interaction.user.id, interaction.user.name
        )

        current_tier = user_data["tier"]
        points_total = user_data["total_points"]

        thresholds = BotConfigModel.get_tier_thresholds()
        sorted_tiers = sorted(thresholds.items(), key=lambda kv: kv[1])

        embed = discord.Embed(
            title=f"{get_tier_emoji(current_tier)} Your Tier Progress",
            description=f"Tier progress for {interaction.user.mention}",
            color=BRAND_COLOR,
        )

        for idx, (tier_name, min_points) in enumerate(sorted_tiers):
            tier_data = TIERS.get(tier_name, {})
            emoji = tier_data.get("emoji", "⚪")
            role_display = get_tier_role_mention(tier_name, interaction.guild)
            max_points = (
                sorted_tiers[idx + 1][1] - 1 if idx + 1 < len(sorted_tiers) else "∞"
            )

            if tier_name == current_tier:
                status = "**← YOU ARE HERE**"
            elif points_total > min_points:
                status = "✅ Completed"
            else:
                status = f"🔒 Need {min_points - points_total} more points"

            # Discord only resolves mention syntax in embed field VALUES, not
            # names - the role mention has to live in value, not name.
            embed.add_field(
                name=f"{emoji} Tier",
                value=f"{role_display}\n{min_points}-{max_points} points\n{status}",
                inline=False,
            )

        embed.set_footer(text=f"Current Points: {points_total}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"❌ Error in mytier command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while checking your tier.", ephemeral=True
        )


@season_group.command(
    name="weeklywinners", description="See who won a given week (defaults to the most recent)"
)
@app_commands.describe(week_number="Which week to check (defaults to the most recently closed week)")
async def weekly_winners(interaction: discord.Interaction, week_number: Optional[int] = None):
    try:
        await interaction.response.defer()

        if week_number is None:
            closed_weeks = get_closed_week_ranges()
            if not closed_weeks:
                await interaction.followup.send(
                    "📅 No week has closed yet — check back once the first week ends."
                )
                return
            week_number = max(wn for _, _, wn in closed_weeks)

        winners = await WeeklyVictoryModel.get_week_winners(week_number)
        entries = [
            {
                "user_id": w["user_id"],
                "mention": w["mention"],
                "detail": f"{w['points_earned']} pts",
            }
            for w in winners
        ]
        embed = create_winners_list_embed(
            entries,
            title=f"🏁 Week {week_number} Victors",
            footer_text=f"{CURRENT_SEASON} Challenge • Weekly Victory",
        )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"❌ Error in weekly_winners command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching weekly winners.", ephemeral=True
        )


@season_group.command(
    name="monthlywinners", description="See who won a given month (defaults to the most recent)"
)
@app_commands.describe(month_number="Which month to check (defaults to the most recently closed month)")
async def monthly_winners(interaction: discord.Interaction, month_number: Optional[int] = None):
    try:
        await interaction.response.defer()

        if month_number is None:
            closed_week_numbers = {wn for _, _, wn in get_closed_week_ranges()}
            candidate_months = [
                m
                for m, (_, last_week) in MONTHLY_VICTORY_WEEK_GROUPS.items()
                if last_week in closed_week_numbers
            ]
            if not candidate_months:
                await interaction.followup.send(
                    "📅 No month has closed yet — check back once Month 1 (Week 4) ends."
                )
                return
            month_number = max(candidate_months)

        winners = await MonthlyVictoryModel.get_month_winners(month_number)
        group = MONTHLY_VICTORY_WEEK_GROUPS.get(month_number)
        weeks_in_month = (group[1] - group[0] + 1) if group else None

        entries = [
            {
                "user_id": w["user_id"],
                "mention": w["mention"],
                "detail": f"{w['weeks_won']}/{weeks_in_month or w['weeks_required']} weeks",
            }
            for w in winners
        ]
        embed = create_winners_list_embed(
            entries,
            title=f"📆 Month {month_number} Champions",
            footer_text=f"{CURRENT_SEASON} Challenge • Monthly Victory",
        )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"❌ Error in monthly_winners command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching monthly winners.", ephemeral=True
        )


@season_group.command(
    name="finishers", description="See everyone who's earned Official Finisher status"
)
async def finishers(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        finisher_list = await WeeklyVictoryModel.get_all_official_finishers()
        entries = [
            {
                "user_id": f["user_id"],
                "mention": f["mention"],
                "detail": f"{f['total_points']} pts",
            }
            for f in finisher_list
        ]
        embed = create_winners_list_embed(
            entries,
            title="🎖️ Official Finishers",
            description="Won 9 of 10 weeks, or hit the season points bar.",
            footer_text=f"{CURRENT_SEASON} Challenge • Official Finisher",
        )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"❌ Error in finishers command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching Official Finishers.", ephemeral=True
        )


@season_group.command(
    name="finalstandings", description="Top 25 season standings (locked once the challenge ends)"
)
async def final_standings(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        status = challenge_status()
        leaderboard = await UserModel.get_leaderboard(limit=25)

        if status == "ended":
            title = "🏆 FINAL STANDINGS — LOCKED"
            description = "The challenge has ended — this is the final Grand Championship ranking."
        else:
            title = "📊 Current Standings (Live)"
            description = "The challenge is still in progress — this ranking will keep changing until it ends."

        embed = create_leaderboard_embed(leaderboard, title=title, description=description)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"❌ Error in final_standings command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching final standings.", ephemeral=True
        )


@season_group.command(
    name="rafflepool", description="See the current Championship Raffle ticket standings"
)
@app_commands.describe(limit="Number of users to show (max 25)")
async def raffle_pool(interaction: discord.Interaction, limit: Optional[int] = 10):
    try:
        await interaction.response.defer()

        if limit < 1 or limit > 25:
            limit = 10

        top_tickets = await RaffleTicketModel.get_ticket_leaderboard(limit=limit)
        entries = [
            {
                "user_id": u["user_id"],
                "mention": u["mention"],
                "detail": f"{u['raffle_tickets']} tickets",
            }
            for u in top_tickets
        ]
        embed = create_winners_list_embed(
            entries,
            title="🎟️ Championship Raffle — Ticket Standings",
            description="More tickets = better odds when the draw happens — leaderboard rank doesn't matter here.",
            footer_text=f"{CURRENT_SEASON} Challenge • Championship Raffle",
            empty_text="Nobody's earned any raffle tickets yet.",
        )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"❌ Error in raffle_pool command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching the raffle standings.", ephemeral=True
        )


@season_group.command(
    name="rafflewinners", description="See the Championship Raffle draw results (once drawn)"
)
async def raffle_winners(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        results = await RaffleDrawModel.get_draw_results()
        if not results:
            await interaction.followup.send(
                "🎟️ The Championship Raffle hasn't been drawn yet — check back at the Finale!"
            )
            return

        tier_results = []
        for tier_key, (tier_name, _) in RAFFLE_DRAW_TIERS.items():
            mentions = [row["mention"] for row in results.get(tier_key, [])]
            tier_results.append((tier_name, mentions))

        embed = create_raffle_draw_embed(tier_results)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"❌ Error in raffle_winners command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching raffle results.", ephemeral=True
        )


# Groups member commands for /q2 help - built from live command
# descriptions (see below), so this only needs to be touched when a NEW
# member command is added; nothing here goes stale on its own the way a
# hand-written static embed would.
_HELP_CATEGORIES = {
    "📊 Your Stats": ["points", "mytier"],
    "🏆 Leaderboards": ["leaderboard", "finalstandings"],
    "🏁 Weekly & Monthly Winners": ["weeklywinners", "monthlywinners", "finishers"],
    "🎟️ Championship Raffle": ["rafflepool", "rafflewinners"],
}


@season_group.command(name="help", description="See what commands you can use")
async def help_command(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        # Member commands only - skip the admin-only goldenticket subgroup,
        # anything tagged [ADMIN], and this command itself, so this never
        # needs a manual allowlist to stay member-only as new commands get
        # added.
        member_commands = {
            cmd.name: cmd
            for cmd in season_group.commands
            if not isinstance(cmd, app_commands.Group)
            and "[ADMIN]" not in cmd.description
            and cmd.name != "help"
        }

        embed = discord.Embed(
            title="📖 RunItUp Commands",
            description=f"Everything you can run under `/{SEASON_PREFIX}` — none of this needs mod permissions.",
            color=BRAND_COLOR,
        )

        categorized = set()
        for category, names in _HELP_CATEGORIES.items():
            lines = []
            for name in names:
                cmd = member_commands.get(name)
                if not cmd:
                    continue
                categorized.add(name)
                lines.append(f"**`/{SEASON_PREFIX} {cmd.name}`** — {cmd.description}")
            if lines:
                embed.add_field(name=category, value="\n".join(lines), inline=False)

        # Anything not in _HELP_CATEGORIES yet still shows up here, so a
        # newly-added member command is never silently missing from /help.
        leftover = [cmd for name, cmd in member_commands.items() if name not in categorized]
        if leftover:
            lines = [
                f"**`/{SEASON_PREFIX} {cmd.name}`** — {cmd.description}"
                for cmd in sorted(leftover, key=lambda c: c.name)
            ]
            embed.add_field(name="🔧 Other", value="\n".join(lines), inline=False)

        embed.set_footer(text=f"{CURRENT_SEASON} Challenge")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"❌ Error in help command: {e}")
        await interaction.followup.send(
            "❌ An error occurred while fetching the command list.", ephemeral=True
        )
