import discord
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from config.constants import BRAND_COLOR
from config.settings import LEADERBOARD_IMAGE_URL, MAX_REFERRALS
from utils.helpers import get_tier_emoji, get_tier_role_mention


def create_leaderboard_embed(
    users: List[Dict[str, Any]],
    title: str = "🏆 LEADERBOARD",
    description: str = "Top performers in the RunItUp Q2 Challenge",
    footer_text: str = "RunItUp Q2 Challenge • Updated",
) -> discord.Embed:
    """Create leaderboard embed. Generic over whatever ranked {user, total_points}
    list it's handed - description/footer_text let callers (e.g. the weekly
    leaderboard) relabel it without duplicating the rendering logic."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=BRAND_COLOR,
        timestamp=datetime.now(timezone.utc),
    )

    if not users:
        embed.add_field(
            name="No Data", value="No users on the leaderboard yet!", inline=False
        )
        return embed

    leaderboard_text = f"{description}\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for idx, user in enumerate(users):
        rank = idx + 1
        medal = medals[idx] if idx < 3 else f"`#{rank}`"
        tier_emoji = get_tier_emoji(user["tier"])
        scaler_badge = " ⚙️" if user.get("is_scaler") else ""
        master_badge = " 🥋" if user.get("is_master") else ""
        finisher_badge = " 🏅" if user.get("is_official_finisher") else ""
        founder_badge = " 🏛️" if user.get("is_founder") else ""
        champion_badge = " 👑" if user.get("is_grand_champion") else ""

        # Use mention field that's added in models.py
        user_mention = user.get("mention", f"<@{user['user_id']}>")

        leaderboard_text += (
            f"{medal} **{user_mention}** {tier_emoji}{scaler_badge}{master_badge}"
            f"{finisher_badge}{founder_badge}{champion_badge}\n"
        )
        leaderboard_text += f"    └ {user['total_points']} points\n\n"

    embed.description = leaderboard_text
    # Add leaderboard image
    embed.set_image(url=LEADERBOARD_IMAGE_URL)
    embed.set_footer(text=footer_text)

    return embed


def create_user_stats_embed(
    user_data: Dict[str, Any],
    discord_user: discord.User = None,
    guild: discord.Guild = None,
    weeks_won: Optional[int] = None,
    total_weeks: Optional[int] = None,
    months_won: Optional[int] = None,
    total_months: Optional[int] = None,
) -> discord.Embed:
    """Create user stats embed with user mention"""
    tier_emoji = get_tier_emoji(user_data["tier"])

    # Get user mention - prefer from discord_user, fallback to mention field or construct
    if discord_user:
        user_mention = discord_user.mention
        display_name = discord_user.display_name
        guild = guild or getattr(discord_user, "guild", None)
    else:
        user_mention = user_data.get("mention", f"<@{user_data['user_id']}>")
        display_name = user_data["username"]

    embed = discord.Embed(
        title=f"{tier_emoji} {display_name}'s Stats",
        description=f"Stats for {user_mention}",
        color=BRAND_COLOR,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="📊 Total Points",
        value=f"**{user_data['total_points']}** points",
        inline=True,
    )

    # Resolve the actual Discord role mention if it exists in this guild,
    # falling back to the plain role name text otherwise
    tier_role_display = get_tier_role_mention(user_data["tier"], guild)
    embed.add_field(name="🎖️ Tier", value=f"{tier_emoji} {tier_role_display}", inline=True)

    if user_data.get("is_scaler"):
        embed.add_field(name="⚙️ Status", value="**Scaler** (Verified)", inline=True)

    if user_data.get("is_master"):
        embed.add_field(name="🥋 Bonus", value="**Masters** (+15%)", inline=True)

    if user_data.get("is_official_finisher"):
        embed.add_field(name="🏆 Badge", value="**Official Finisher**", inline=True)

    if weeks_won is not None:
        weeks_text = f"{weeks_won}/{total_weeks}" if total_weeks else str(weeks_won)
        embed.add_field(name="🏁 Weeks Won", value=weeks_text, inline=True)

    if months_won is not None:
        months_text = f"{months_won}/{total_months}" if total_months else str(months_won)
        embed.add_field(name="📆 Months Won", value=months_text, inline=True)

    if user_data.get("raffle_tickets"):
        embed.add_field(
            name="🎟️ Raffle Tickets",
            value=f"{user_data['raffle_tickets']}",
            inline=True,
        )

    embed.add_field(
        name="🤝 Referrals",
        value=f"{user_data.get('referral_count', 0)}/{MAX_REFERRALS}",
        inline=True,
    )

    embed.set_footer(text="RunItUp Q2 Challenge")

    return embed


def create_winners_list_embed(
    entries: List[Dict[str, Any]],
    title: str,
    description: str = "",
    footer_text: Optional[str] = None,
    empty_text: str = "Nobody's qualified yet — check back soon!",
) -> discord.Embed:
    """Generic mention + detail list - each entry is {"user_id", "mention",
    "detail"} where "detail" is a caller-formatted string (e.g. "225 pts" or
    "3/4 weeks"). Used for weekly/monthly winners, Official Finishers, and
    reused as-is for the matching auto-announcements so the on-demand
    command and the auto-post look identical."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=BRAND_COLOR,
        timestamp=datetime.now(timezone.utc),
    )

    if not entries:
        embed.add_field(name="No Winners Yet", value=empty_text, inline=False)
        return embed

    # Discord hard-caps embed description at 4096 chars - a lenient week
    # (or /q2 finishers deep into the season) could realistically produce
    # more winners than that fits. Stop adding lines before the budget runs
    # out rather than risk the whole send failing, and say how many were
    # left off instead of silently truncating mid-mention.
    prefix = f"{description}\n\n" if description else ""
    budget = 4096 - len(prefix) - 60  # headroom for the "+N more" trailer
    lines = []
    used = 0
    shown = 0
    for entry in entries:
        mention = entry.get("mention", f"<@{entry['user_id']}>")
        detail = entry.get("detail")
        line = f"🏅 **{mention}**" + (f" — {detail}" if detail else "")
        if used + len(line) + 1 > budget:
            break
        lines.append(line)
        used += len(line) + 1
        shown += 1

    body = "\n".join(lines)
    if shown < len(entries):
        body += f"\n\n*+{len(entries) - shown} more not shown*"

    embed.description = prefix + body

    if footer_text:
        embed.set_footer(text=footer_text)

    return embed


def create_championship_announcement_embed(
    founders: List[Dict[str, Any]],
    grand_champion: Optional[Dict[str, Any]],
    title: str = "🏆 Grand Championship Results",
) -> discord.Embed:
    """The end-of-challenge results embed - Top 25 Founders + the single
    Grand Champion, since they're announced together at the finale."""
    embed = discord.Embed(
        title=title,
        description="Locked the moment the challenge ended — pure lifetime points, no drama, no voting.",
        color=BRAND_COLOR,
        timestamp=datetime.now(timezone.utc),
    )

    if grand_champion:
        mention = grand_champion.get("mention", f"<@{grand_champion['user_id']}>")
        embed.add_field(
            name="👑 Grand Champion",
            value=f"**{mention}** — {grand_champion.get('total_points', '?')} points",
            inline=False,
        )

    if founders:
        lines = []
        for founder in founders:
            mention = founder.get("mention", f"<@{founder['user_id']}>")
            lines.append(f"🏛️ {mention}")
        embed.add_field(
            name=f"Top 25 Founders ({len(founders)})",
            value="\n".join(lines)[:1024],
            inline=False,
        )
    else:
        embed.add_field(name="Top 25 Founders", value="None yet.", inline=False)

    embed.set_footer(text="RunItUp Q2 Challenge • Championship Finale")
    return embed


def create_raffle_draw_embed(
    tier_results: List[tuple],
    title: str = "🎟️ Championship Raffle — Draw Results",
) -> discord.Embed:
    """tier_results: [(tier_display_name, [mention, ...]), ...] in draw
    order (highest tier first)."""
    embed = discord.Embed(
        title=title,
        description="Every ticket earned all season went into this drawing. Congratulations! 🎉",
        color=BRAND_COLOR,
        timestamp=datetime.now(timezone.utc),
    )

    if not tier_results or not any(winners for _, winners in tier_results):
        embed.add_field(
            name="No Tickets Yet",
            value="Nobody had earned any raffle tickets when this draw ran.",
            inline=False,
        )
        return embed

    for tier_name, winners in tier_results:
        value = "\n".join(winners) if winners else "*(no eligible entries left)*"
        embed.add_field(name=tier_name, value=value[:1024], inline=False)

    embed.set_footer(text="RunItUp Q2 Challenge • Championship Raffle")
    return embed


