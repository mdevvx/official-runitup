from typing import Optional, List, Dict, Any
from datetime import date, datetime, timezone, timedelta
from database.supabase_client import get_supabase
from utils.logger import get_logger
from config.constants import TIERS, CURRENT_SEASON, SCALER_ROLE_NAME, MASTER_ROLE_NAME

logger = get_logger(__name__)


async def _post_announcement(bot, embed) -> None:
    """Posts an embed to the configured 'announcements' channel, falling
    back to 'leaderboard' if announcements isn't set up. Never raises -
    announcements are a nice-to-have; a missing/misconfigured channel
    should never block the actual game-state finalization (tickets, roles,
    flags) that already happened by the time this is called."""
    if not bot:
        return
    try:
        from database.bot_config import BotConfigModel

        channel_id = BotConfigModel.get_channel_id(
            "announcements"
        ) or BotConfigModel.get_channel_id("leaderboard")
        if not channel_id:
            return
        channel = bot.get_channel(channel_id)
        if not channel:
            return
        await channel.send(embed=embed)
    except Exception as e:
        logger.error(f"ERROR | _post_announcement | {e}")


class UserModel:
    @staticmethod
    async def get_or_create(user_id: int, username: str) -> Dict[str, Any]:
        """Get user or create if doesn't exist"""
        try:
            supabase = get_supabase()

            # Try to get user
            response = (
                supabase.table("users").select("*").eq("user_id", user_id).execute()
            )

            if response.data:
                user_data = response.data[0]
                user_data["mention"] = f"<@{user_id}>"
                return user_data

            # Create new user
            new_user = {
                "user_id": user_id,
                "username": username,
                "total_points": 0,
                "tier": "OBSERVER",
                "is_scaler": False,
                "referral_count": 0,
            }

            response = supabase.table("users").insert(new_user).execute()
            logger.info(
                f"USER CREATED | ID: {user_id} | Username: {username} | Initial Tier: OBSERVER"
            )
            user_data = response.data[0]
            user_data["mention"] = f"<@{user_id}>"
            return user_data

        except Exception as e:
            logger.error(f"ERROR | get_or_create | User: {user_id} | {e}")
            raise

    @staticmethod
    async def update_points(
        user_id: int,
        points_change: int,
        reason: str,
        bot=None,
        category: str = "consistency",
    ) -> Dict[str, Any]:
        """Update user points and tier, and update Discord roles immediately.
        category tags the points_history row 'consistency' (daily activity/todo/
        calls/value-post sources, the default - auto-tracked, what Weekly
        Victory sums) or 'performance' (admin-awarded wins/referrals/bonuses -
        open-ended, excluded from Weekly Victory, still counts on the season
        and weekly leaderboards)."""
        try:
            supabase = get_supabase()

            # Get current user
            user = await UserModel.get_by_id(user_id)
            old_tier = user["tier"]
            old_points = user["total_points"]
            new_total = old_points + points_change

            # Determine new tier
            new_tier = UserModel.calculate_tier(new_total)

            # Update user
            response = (
                supabase.table("users")
                .update(
                    {
                        "total_points": new_total,
                        "tier": new_tier,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("user_id", user_id)
                .execute()
            )

            # Log points history
            supabase.table("points_history").insert(
                {
                    "user_id": user_id,
                    "points_change": points_change,
                    "reason": reason,
                    "category": category,
                }
            ).execute()

            # Comprehensive logging
            logger.info(
                f"POINTS UPDATE | User: {user_id} | Change: {points_change:+d} | "
                f"Old: {old_points} | New: {new_total} | Reason: {reason}"
            )

            # Send to Discord logging channel
            if bot:
                await UserModel._send_points_log(
                    bot, user_id, points_change, old_points, new_total, reason
                )

            # Log tier changes separately for visibility
            if old_tier != new_tier:
                logger.info(
                    f"TIER CHANGE | User: {user_id} | {old_tier} -> {new_tier} | "
                    f"Points: {new_total}"
                )
                # Send tier change to Discord
                if bot:
                    await UserModel._send_tier_change_log(
                        bot, user_id, old_tier, new_tier, new_total
                    )

            # ALWAYS update Discord roles after points change (to ensure sync)
            if bot:
                role_updated = await UserModel.update_user_role(user_id, new_tier, bot)
                if role_updated and old_tier != new_tier:
                    logger.info(
                        f"ROLE UPDATED | User: {user_id} | New Tier Role: {new_tier}"
                    )

            updated_user = response.data[0]
            updated_user["mention"] = f"<@{user_id}>"
            return updated_user

        except Exception as e:
            logger.error(
                f"ERROR | update_points | User: {user_id} | Points: {points_change:+d} | {e}"
            )
            # Don't raise - we want points to update even if role update fails
            try:
                supabase = get_supabase()
                response = (
                    supabase.table("users").select("*").eq("user_id", user_id).execute()
                )
                if response.data:
                    user_data = response.data[0]
                    user_data["mention"] = f"<@{user_id}>"
                    return user_data
            except:
                pass
            raise

    @staticmethod
    async def _send_points_log(
        bot,
        user_id: int,
        points_change: int,
        old_points: int,
        new_points: int,
        reason: str,
    ):
        """Send points update to Discord logging channel"""
        try:
            from config.settings import LOG_CHANNEL_ID
            import discord

            if not LOG_CHANNEL_ID:
                return

            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if not log_channel:
                return

            # Determine color based on points change
            color = (
                0x00FF00
                if points_change > 0
                else 0xFF0000 if points_change < 0 else 0x808080
            )

            embed = discord.Embed(
                title="Points Update", color=color, timestamp=datetime.utcnow()
            )

            embed.add_field(name="User", value=f"<@{user_id}>", inline=True)
            embed.add_field(
                name="Change", value=f"**{points_change:+d}** points", inline=True
            )
            embed.add_field(
                name="Total", value=f"{old_points} -> **{new_points}**", inline=True
            )
            embed.add_field(name="Reason", value=reason, inline=False)

            await log_channel.send(embed=embed)

        except Exception as e:
            logger.debug(f"Could not send points log to Discord: {e}")

    @staticmethod
    async def _send_tier_change_log(
        bot, user_id: int, old_tier: str, new_tier: str, points: int
    ):
        """Send tier change to Discord logging channel"""
        try:
            from config.settings import LOG_CHANNEL_ID
            from utils.helpers import get_tier_emoji
            import discord

            if not LOG_CHANNEL_ID:
                return

            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if not log_channel:
                return

            old_emoji = get_tier_emoji(old_tier)
            new_emoji = get_tier_emoji(new_tier)

            embed = discord.Embed(
                title="Tier Change",
                description=f"<@{user_id}> has advanced to a new tier!",
                color=0xFFD700,
                timestamp=datetime.utcnow(),
            )

            embed.add_field(
                name="Previous Tier",
                value=f"{old_emoji} {TIERS[old_tier]['role_name']}",
                inline=True,
            )
            embed.add_field(
                name="New Tier",
                value=f"{new_emoji} {TIERS[new_tier]['role_name']}",
                inline=True,
            )
            embed.add_field(
                name="Total Points", value=f"**{points}** points", inline=True
            )

            await log_channel.send(embed=embed)

        except Exception as e:
            logger.debug(f"Could not send tier change log to Discord: {e}")

    @staticmethod
    async def update_user_role(user_id: int, new_tier: str, bot) -> bool:
        """Update user's Discord role based on their tier. Returns True if successful."""
        try:
            from config.settings import GUILD_ID
            import discord

            # Get guild
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                logger.warning(
                    f"ROLE UPDATE FAILED | Guild not found | User: {user_id}"
                )
                return False

            # Get member
            member = guild.get_member(user_id)
            if not member:
                logger.warning(
                    f"ROLE UPDATE FAILED | Member not found in guild | User: {user_id}"
                )
                return False

            # Get all tier roles
            tier_roles = {}
            for tier_name, tier_data in TIERS.items():
                role = discord.utils.get(guild.roles, name=tier_data["role_name"])
                if role:
                    tier_roles[tier_name] = role

            if not tier_roles:
                logger.warning(
                    f"ROLE UPDATE FAILED | No tier roles found in guild | User: {user_id}"
                )
                return False

            # Get the new tier role
            new_tier_role = tier_roles.get(new_tier)
            if not new_tier_role:
                logger.warning(
                    f"ROLE UPDATE FAILED | Role for tier {new_tier} not found | User: {user_id}"
                )
                return False

            # Check current state
            has_correct_role = new_tier_role in member.roles

            # Find any incorrect tier roles they have
            roles_to_remove = [
                role
                for tier, role in tier_roles.items()
                if tier != new_tier and role in member.roles
            ]

            # Only make changes if needed
            if not has_correct_role or roles_to_remove:
                # Remove incorrect tier roles
                if roles_to_remove:
                    await member.remove_roles(
                        *roles_to_remove, reason="Tier update - removing old tiers"
                    )
                    removed_names = [r.name for r in roles_to_remove]
                    logger.info(
                        f"ROLES REMOVED | User: {user_id} ({member.name}) | "
                        f"Roles: {', '.join(removed_names)}"
                    )

                    # Send to Discord log
                    await UserModel._send_role_log(
                        bot, user_id, "removed", removed_names
                    )

                # Add correct tier role if missing
                if not has_correct_role:
                    await member.add_roles(
                        new_tier_role, reason="Tier update - adding correct tier"
                    )
                    logger.info(
                        f"ROLE ADDED | User: {user_id} ({member.name}) | "
                        f"Role: {new_tier_role.name}"
                    )

                    # Send to Discord log
                    await UserModel._send_role_log(
                        bot, user_id, "added", [new_tier_role.name]
                    )

                return True
            else:
                logger.debug(
                    f"ROLE ALREADY CORRECT | User: {member.name} | Role: {new_tier_role.name}"
                )
                return True

        except discord.Forbidden:
            logger.error(
                f"PERMISSION ERROR | Bot lacks permission to update roles | User: {user_id}"
            )
            return False
        except Exception as e:
            logger.error(f"ERROR | update_user_role | User: {user_id} | {e}")
            return False

    @staticmethod
    async def _send_role_log(bot, user_id: int, action: str, role_names: List[str]):
        """Send role update to Discord logging channel"""
        try:
            from config.settings import LOG_CHANNEL_ID
            import discord

            if not LOG_CHANNEL_ID:
                return

            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if not log_channel:
                return

            color = 0x00FF00 if action == "added" else 0xFF9900
            title = "Role Added" if action == "added" else "Role Removed"

            embed = discord.Embed(title=title, color=color, timestamp=datetime.utcnow())

            embed.add_field(name="User", value=f"<@{user_id}>", inline=True)
            embed.add_field(name="Roles", value="\n".join(role_names), inline=True)

            await log_channel.send(embed=embed)

        except Exception as e:
            logger.debug(f"Could not send role log to Discord: {e}")

    @staticmethod
    def calculate_tier(points: int) -> str:
        """Calculate tier based on points, using thresholds overridable via
        /<season> settierpoints (falls back to config.constants.TIERS defaults)"""
        from database.bot_config import BotConfigModel

        thresholds = BotConfigModel.get_tier_thresholds()

        current_tier = "OBSERVER"
        current_min = -1
        for tier_name, min_points in thresholds.items():
            if points >= min_points and min_points > current_min:
                current_tier = tier_name
                current_min = min_points
        return current_tier

    @staticmethod
    async def get_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("users").select("*").eq("user_id", user_id).execute()
            )
            if response.data:
                user_data = response.data[0]
                user_data["mention"] = f"<@{user_id}>"
                return user_data
            return None
        except Exception as e:
            logger.error(f"ERROR | get_by_id | User: {user_id} | {e}")
            raise

    @staticmethod
    async def get_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
        """Get top users by points - only users who have actually earned points,
        so a freshly-reset season doesn't list everyone tied at 0"""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("users")
                .select("*")
                .gt("total_points", 0)
                .order("total_points", desc=True)
                .limit(limit)
                .execute()
            )
            # Add mention to each user
            for user in response.data:
                user["mention"] = f"<@{user['user_id']}>"
            return response.data
        except Exception as e:
            logger.error(f"ERROR | get_leaderboard | {e}")
            raise

    @staticmethod
    async def get_highest_total_points() -> int:
        """Current season's highest total_points across all users - the
        basis for Official Finisher's auto-computed points path (see
        config.constants.OFFICIAL_FINISHER_POINTS_RATIO). 0 if nobody has
        earned any points yet."""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("users")
                .select("total_points")
                .order("total_points", desc=True)
                .limit(1)
                .execute()
            )
            return response.data[0]["total_points"] if response.data else 0
        except Exception as e:
            logger.error(f"ERROR | get_highest_total_points | {e}")
            raise

    @staticmethod
    async def update_streak(user_id: int, activity_date: date) -> int:
        """Increments current_streak if yesterday was also a streak day,
        otherwise resets to 1. Called once per user per day, from
        DailyActivityModel.award_daily_point (the same "did they actually
        engage today" signal the daily point uses). Backs the "everyone on
        a 14-day streak" Golden Ticket event. Returns the new streak."""
        try:
            supabase = get_supabase()
            user = await UserModel.get_by_id(user_id)
            last_date_raw = user.get("last_streak_date") if user else None
            yesterday = (activity_date - timedelta(days=1)).isoformat()

            new_streak = (user.get("current_streak") or 0) + 1 if last_date_raw == yesterday else 1

            supabase.table("users").update(
                {"current_streak": new_streak, "last_streak_date": activity_date.isoformat()}
            ).eq("user_id", user_id).execute()
            return new_streak
        except Exception as e:
            logger.error(f"ERROR | update_streak | User: {user_id} | {e}")
            raise

    @staticmethod
    async def _points_leaderboard_for_range(
        range_start: datetime, range_end: datetime, limit: int
    ) -> List[Dict[str, Any]]:
        """Shared by get_weekly_leaderboard/get_monthly_leaderboard - sums
        ALL points_history rows (both categories) in [range_start,
        range_end) per user, ranks them, and hydrates from `users`. Result
        shape matches get_leaderboard() (total_points overwritten with the
        range's sum, mention added)."""
        try:
            # points_history.created_at is naive UTC (Postgres NOW() on a
            # `timestamp` column) - convert the (possibly non-UTC) challenge
            # window to UTC before filtering so the comparison lines up.
            range_start_utc = range_start.astimezone(timezone.utc).replace(tzinfo=None)
            range_end_utc = range_end.astimezone(timezone.utc).replace(tzinfo=None)

            supabase = get_supabase()
            history_response = (
                supabase.table("points_history")
                .select("user_id, points_change")
                .gte("created_at", range_start_utc.isoformat())
                .lt("created_at", range_end_utc.isoformat())
                .execute()
            )

            totals: Dict[int, float] = {}
            for row in history_response.data:
                totals[row["user_id"]] = (
                    totals.get(row["user_id"], 0) + row["points_change"]
                )

            ranked_ids = sorted(
                (uid for uid, pts in totals.items() if pts > 0),
                key=lambda uid: totals[uid],
                reverse=True,
            )[:limit]

            if not ranked_ids:
                return []

            users_response = (
                supabase.table("users").select("*").in_("user_id", ranked_ids).execute()
            )
            users_by_id = {u["user_id"]: u for u in users_response.data}

            leaderboard = []
            for uid in ranked_ids:
                user = users_by_id.get(uid)
                if not user:
                    continue
                entry = dict(user)
                entry["total_points"] = totals[uid]
                entry["mention"] = f"<@{uid}>"
                leaderboard.append(entry)
            return leaderboard
        except Exception as e:
            logger.error(f"ERROR | _points_leaderboard_for_range | {e}")
            raise

    @staticmethod
    async def get_weekly_leaderboard(
        limit: int = 10, week_range: Optional[tuple] = None
    ) -> List[Dict[str, Any]]:
        """Top users by points earned in a challenge week, summed from
        points_history rather than users.total_points (which is lifetime
        and only resets on a full season relaunch). Defaults to the current
        week (see utils.helpers.get_current_week_range); pass an explicit
        (week_start, week_end, week_number) tuple to score a specific past
        week instead (e.g. for raffle ticket awarding at week-finalization
        time). Returns [] if no week can be resolved."""
        from utils.helpers import get_current_week_range

        if week_range is None:
            week_range = get_current_week_range()
        if not week_range:
            return []
        week_start, week_end, _ = week_range
        return await UserModel._points_leaderboard_for_range(week_start, week_end, limit)

    @staticmethod
    async def get_monthly_leaderboard(
        month_start: datetime, month_end: datetime, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Top users by points earned across a full month's date range
        (first week's start through last week's end) - same semantics as
        get_weekly_leaderboard, just a wider window. Callers resolve
        month_start/month_end themselves (see MonthlyVictoryModel.finalize_month)."""
        return await UserModel._points_leaderboard_for_range(
            month_start, month_end, limit
        )

    @staticmethod
    async def add_referrals(
        user_id: int, count: int, points: int, reason: str, bot=None
    ) -> Dict[str, Any]:
        """Increment referral_count and award the corresponding points in one call"""
        try:
            supabase = get_supabase()

            user = await UserModel.get_by_id(user_id)
            new_referral_count = user.get("referral_count", 0) + count

            supabase.table("users").update(
                {
                    "referral_count": new_referral_count,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ).eq("user_id", user_id).execute()

            logger.info(
                f"REFERRALS ADDED | User: {user_id} | +{count} | New Total: {new_referral_count}"
            )

            updated_user = await UserModel.update_points(
                user_id, points, reason, bot=bot, category="performance"
            )
            updated_user["referral_count"] = new_referral_count
            return updated_user
        except Exception as e:
            logger.error(f"ERROR | add_referrals | User: {user_id} | {e}")
            raise

    @staticmethod
    async def set_scaler(user_id: int, is_scaler: bool = True, bot=None) -> Dict[str, Any]:
        """Set user as scaler, optionally syncing the Discord Scaler role (grants #scalers access)"""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("users")
                .update(
                    {
                        "is_scaler": is_scaler,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("user_id", user_id)
                .execute()
            )

            logger.info(f"SCALER STATUS SET | User: {user_id} | Is Scaler: {is_scaler}")

            if bot:
                await UserModel._sync_role_by_type(bot, user_id, "scalers", is_scaler)

            user_data = response.data[0]
            user_data["mention"] = f"<@{user_id}>"
            return user_data
        except Exception as e:
            logger.error(f"ERROR | set_scaler | User: {user_id} | {e}")
            raise

    @staticmethod
    async def set_master(user_id: int, is_master: bool = True, bot=None) -> Dict[str, Any]:
        """Set the Masters bonus flag (Whop masterclass purchase - not season/points based),
        optionally syncing the Discord Masters role. Grants +15% points on wins/value-drops."""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("users")
                .update(
                    {
                        "is_master": is_master,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("user_id", user_id)
                .execute()
            )

            logger.info(f"MASTER STATUS SET | User: {user_id} | Is Master: {is_master}")

            if bot:
                await UserModel._sync_role_by_type(bot, user_id, "masters", is_master)

            user_data = response.data[0]
            user_data["mention"] = f"<@{user_id}>"
            return user_data
        except Exception as e:
            logger.error(f"ERROR | set_master | User: {user_id} | {e}")
            raise

    @staticmethod
    async def _sync_role_by_type(bot, user_id: int, role_type: str, should_have: bool):
        """Add or remove a single Discord role by role_type ('masters'/'scalers') -
        roles that live outside the tier system, so they're managed independently.
        Resolves the actual role via BotConfigModel.get_role_id (set with
        /<season> setrole) if configured, otherwise falls back to the hardcoded
        MASTER_ROLE_NAME/SCALER_ROLE_NAME lookup by name."""
        try:
            from config.settings import GUILD_ID
            from database.bot_config import BotConfigModel
            import discord

            guild = bot.get_guild(GUILD_ID)
            if not guild:
                return

            member = guild.get_member(user_id)
            if not member:
                return

            role_id = BotConfigModel.get_role_id(role_type)
            if role_id:
                role = guild.get_role(role_id)
            else:
                fallback_names = {
                    "masters": MASTER_ROLE_NAME,
                    "scalers": SCALER_ROLE_NAME,
                }
                role = discord.utils.get(
                    guild.roles, name=fallback_names.get(role_type, role_type)
                )

            if not role:
                logger.warning(
                    f"ROLE SYNC SKIPPED | role_type '{role_type}' not configured/found | "
                    f"User: {user_id}"
                )
                return

            has_role = role in member.roles
            if should_have and not has_role:
                await member.add_roles(role, reason=f"{role_type} unlocked")
                logger.info(f"ROLE ADDED | User: {user_id} | Role: {role.name}")
            elif not should_have and has_role:
                await member.remove_roles(role, reason=f"{role_type} revoked")
                logger.info(f"ROLE REMOVED | User: {user_id} | Role: {role.name}")
        except Exception as e:
            logger.error(
                f"ERROR | _sync_role_by_type | role_type: {role_type} | User: {user_id} | {e}"
            )

    @staticmethod
    async def _sync_named_role(
        bot, user_id: int, role_name: str, should_have: bool, context: str
    ):
        """Add or remove a Discord role looked up by exact name - same
        lookup convention as tier roles (must already exist in the server;
        this never creates one). Used for Weekly Victory / Official
        Finisher badges, which aren't bot_config-bound like masters/scalers."""
        try:
            from config.settings import GUILD_ID
            import discord

            guild = bot.get_guild(GUILD_ID)
            if not guild:
                return

            member = guild.get_member(user_id)
            if not member:
                return

            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                logger.warning(
                    f'ROLE SYNC SKIPPED | "{role_name}" not found in server | '
                    f"User: {user_id} | Context: {context}"
                )
                return

            has_role = role in member.roles
            if should_have and not has_role:
                await member.add_roles(role, reason=context)
                logger.info(f"ROLE ADDED | User: {user_id} | Role: {role.name}")
            elif not should_have and has_role:
                await member.remove_roles(role, reason=context)
                logger.info(f"ROLE REMOVED | User: {user_id} | Role: {role.name}")
        except Exception as e:
            logger.error(
                f"ERROR | _sync_named_role | Role: {role_name} | User: {user_id} | {e}"
            )


class DailyActivityModel:
    @staticmethod
    async def track_activity(
        user_id: int, activity_date: date = None
    ) -> Dict[str, Any]:
        """Track daily activity"""
        try:
            if activity_date is None:
                activity_date = date.today()

            supabase = get_supabase()

            # Check if activity exists
            response = (
                supabase.table("daily_activity")
                .select("*")
                .eq("user_id", user_id)
                .eq("activity_date", activity_date.isoformat())
                .execute()
            )

            if response.data:
                # Update message count
                current = response.data[0]
                new_count = current["message_count"] + 1

                response = (
                    supabase.table("daily_activity")
                    .update({"message_count": new_count})
                    .eq("id", current["id"])
                    .execute()
                )

                return response.data[0]
            else:
                # Create new activity record
                new_activity = {
                    "user_id": user_id,
                    "activity_date": activity_date.isoformat(),
                    "message_count": 1,
                    "points_awarded": 0,
                }

                response = (
                    supabase.table("daily_activity").insert(new_activity).execute()
                )
                logger.debug(
                    f"ACTIVITY TRACKED | User: {user_id} | Date: {activity_date}"
                )
                return response.data[0]

        except Exception as e:
            logger.error(f"ERROR | track_activity | User: {user_id} | {e}")
            raise

    @staticmethod
    async def award_daily_point(
        user_id: int, activity_date: date = None, bot=None
    ) -> bool:
        """Award daily activity point if not already awarded. Also updates
        the user's streak and consumes one "next N" Golden Ticket slot if
        one's armed - both piggyback on this exact signal since it's the
        one clean "did they engage today" event already tracked per user
        per day."""
        try:
            if activity_date is None:
                activity_date = date.today()

            supabase = get_supabase()

            # Get activity record
            response = (
                supabase.table("daily_activity")
                .select("*")
                .eq("user_id", user_id)
                .eq("activity_date", activity_date.isoformat())
                .execute()
            )

            if not response.data:
                return False

            activity = response.data[0]

            # Check if already awarded and has enough messages
            if activity["points_awarded"] == 0 and activity["message_count"] >= 3:
                # Award point
                supabase.table("daily_activity").update({"points_awarded": 1}).eq(
                    "id", activity["id"]
                ).execute()

                await UserModel.update_points(user_id, 1, "Daily activity", bot=bot)
                await UserModel.update_streak(user_id, activity_date)
                await GoldenTicketModel.try_consume_next_n(user_id)
                logger.info(
                    f"DAILY POINT AWARDED | User: {user_id} | Date: {activity_date}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"ERROR | award_daily_point | User: {user_id} | {e}")
            raise


class ValuePostModel:
    @staticmethod
    async def create_or_update(
        message_id: int, user_id: int, channel_id: int
    ) -> Dict[str, Any]:
        """Create or update value post"""
        try:
            supabase = get_supabase()
            post_date = date.today()

            # Check if exists
            response = (
                supabase.table("value_posts")
                .select("*")
                .eq("message_id", message_id)
                .execute()
            )

            if response.data:
                return response.data[0]

            # Create new
            new_post = {
                "user_id": user_id,
                "message_id": message_id,
                "channel_id": channel_id,
                "post_date": post_date.isoformat(),
                "season": CURRENT_SEASON,
                "reaction_counts": {},
                "is_pinned": False,
                "total_points": 0,
            }

            response = supabase.table("value_posts").insert(new_post).execute()
            logger.info(f"VALUE POST CREATED | User: {user_id} | Message: {message_id}")
            return response.data[0]

        except Exception as e:
            logger.error(f"ERROR | create_value_post | Message: {message_id} | {e}")
            raise

    @staticmethod
    async def update_reactions(
        message_id: int, reaction_counts: Dict[str, int], bot=None
    ) -> Dict[str, Any]:
        """Recalculate points from the admin-configured emoji->points map
        (see BotConfigModel.get_value_drop_emojis), applying the Masters +15%
        bonus if the post author has purchased the masterclass."""
        try:
            from config.constants import MAX_POINTS_PER_POST, MASTER_BONUS_MULTIPLIER
            from database.bot_config import BotConfigModel

            supabase = get_supabase()
            emoji_points = BotConfigModel.get_value_drop_emojis()

            # Get current post
            current_response = (
                supabase.table("value_posts")
                .select("*")
                .eq("message_id", message_id)
                .execute()
            )

            if not current_response.data:
                return None

            current_post = current_response.data[0]

            raw_points = sum(
                count * emoji_points.get(emoji, 0)
                for emoji, count in reaction_counts.items()
            )
            capped_points = min(raw_points, MAX_POINTS_PER_POST)

            author = await UserModel.get_by_id(current_post["user_id"])
            is_master = bool(author and author.get("is_master"))
            points = (
                round(capped_points * MASTER_BONUS_MULTIPLIER)
                if is_master
                else capped_points
            )

            old_points = current_post["total_points"]
            points_diff = points - old_points

            # Update post
            response = (
                supabase.table("value_posts")
                .update(
                    {
                        "reaction_counts": reaction_counts,
                        "total_points": points,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("message_id", message_id)
                .execute()
            )

            # Log reaction update
            logger.info(
                f"REACTIONS UPDATED | Message: {message_id} | Counts: {reaction_counts} | "
                f"Points: {old_points}->{points}{' (master bonus)' if is_master else ''}"
            )

            # Update user points if changed
            if points_diff != 0:
                await UserModel.update_points(
                    current_post["user_id"],
                    points_diff,
                    f"Value post reactions updated",
                    bot=bot,
                )

            return response.data[0]

        except Exception as e:
            logger.error(f"ERROR | update_reactions | Message: {message_id} | {e}")
            raise

    @staticmethod
    async def get_user_posts_today(user_id: int) -> int:
        """Get count of user's posts today, in the current season"""
        try:
            supabase = get_supabase()
            today = date.today().isoformat()

            response = (
                supabase.table("value_posts")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("post_date", today)
                .eq("season", CURRENT_SEASON)
                .execute()
            )

            return response.count or 0

        except Exception as e:
            logger.error(f"ERROR | get_user_posts_today | User: {user_id} | {e}")
            raise


class DailyTodoModel:
    @staticmethod
    async def create(message_id: int, user_id: int, channel_id: int) -> Dict[str, Any]:
        """Create daily todo post record"""
        try:
            supabase = get_supabase()
            post_date = date.today()

            new_post = {
                "user_id": user_id,
                "message_id": message_id,
                "channel_id": channel_id,
                "post_date": post_date.isoformat(),
                "season": CURRENT_SEASON,
            }

            response = supabase.table("daily_todos").insert(new_post).execute()
            logger.info(f"TODO POST CREATED | User: {user_id} | Message: {message_id}")
            return response.data[0]

        except Exception as e:
            logger.error(f"ERROR | create_todo_post | Message: {message_id} | {e}")
            raise

    @staticmethod
    async def get_user_posts_today(user_id: int) -> int:
        """Get count of user's todo posts today, in the current season"""
        try:
            supabase = get_supabase()
            today = date.today().isoformat()

            response = (
                supabase.table("daily_todos")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("post_date", today)
                .eq("season", CURRENT_SEASON)
                .execute()
            )

            count = response.count or 0
            logger.debug(f"TODO COUNT TODAY | User: {user_id} | Count: {count}")
            return count

        except Exception as e:
            logger.error(f"ERROR | get_user_todo_posts | User: {user_id} | {e}")
            raise


class CallsPostModel:
    @staticmethod
    async def create(message_id: int, user_id: int, channel_id: int) -> Dict[str, Any]:
        """Create calls post record"""
        try:
            supabase = get_supabase()
            post_date = date.today()

            new_post = {
                "user_id": user_id,
                "message_id": message_id,
                "channel_id": channel_id,
                "post_date": post_date.isoformat(),
                "season": CURRENT_SEASON,
            }

            response = supabase.table("calls_posts").insert(new_post).execute()
            logger.info(f"CALLS POST CREATED | User: {user_id} | Message: {message_id}")
            return response.data[0]

        except Exception as e:
            logger.error(f"ERROR | create_calls_post | Message: {message_id} | {e}")
            raise


class WeeklyVictoryModel:
    """Weekly Victory (consistency badge) + Official Finisher. A week is
    scored only from points_history rows tagged category='consistency' -
    see UserModel.update_points. Thresholds/ratios live in config.constants
    with bot_config overrides (BotConfigModel.get_weekly_victory_threshold /
    get_official_finisher_points_threshold)."""

    @staticmethod
    async def finalize_week(
        week_number: int,
        week_start: datetime,
        week_end: datetime,
        bot=None,
        season: str = CURRENT_SEASON,
    ) -> List[int]:
        """Sums each user's consistency points within [week_start, week_end),
        writes one weekly_victories row per user who met the threshold
        (upsert - a closed week's result never changes once written, so
        re-running this for an already-finalized week is a safe no-op), and
        grants the per-week Discord role. Also awards Championship Raffle
        tickets: Win the Week (consistency threshold, +Golden Ticket Day
        bonus if this week was flagged via /<season> goldenticket day) to
        weekly_victories winners, and Weekly Top 10 / Weekly Champion
        (performance ranking that week - separate track, can stack with Win
        the Week) to the top of that week's full points leaderboard.
        Returns the winning user_ids (Weekly Victory, not raffle placement)."""
        try:
            from database.bot_config import BotConfigModel
            from config.constants import RAFFLE_TICKETS

            threshold = BotConfigModel.get_weekly_victory_threshold()
            is_golden_ticket_week = week_number in BotConfigModel.get_golden_ticket_weeks()

            # points_history.created_at is naive UTC (Postgres NOW() on a
            # `timestamp` column) - convert the challenge window to UTC
            # before filtering so the comparison lines up.
            week_start_utc = week_start.astimezone(timezone.utc).replace(tzinfo=None)
            week_end_utc = week_end.astimezone(timezone.utc).replace(tzinfo=None)

            supabase = get_supabase()
            history_response = (
                supabase.table("points_history")
                .select("user_id, points_change")
                .eq("category", "consistency")
                .gte("created_at", week_start_utc.isoformat())
                .lt("created_at", week_end_utc.isoformat())
                .execute()
            )

            totals: Dict[int, float] = {}
            for row in history_response.data:
                totals[row["user_id"]] = (
                    totals.get(row["user_id"], 0) + row["points_change"]
                )

            winners = [uid for uid, pts in totals.items() if pts >= threshold]

            for uid in winners:
                supabase.table("weekly_victories").upsert(
                    {
                        "user_id": uid,
                        "season": season,
                        "week_number": week_number,
                        "points_earned": round(totals[uid]),
                        "threshold": threshold,
                    },
                    on_conflict="user_id,season,week_number",
                ).execute()

                if bot:
                    await UserModel._sync_named_role(
                        bot,
                        uid,
                        f"{season} — Week {week_number} Victor",
                        True,
                        f"Weekly Victory - Week {week_number}",
                    )

                await RaffleTicketModel.add_tickets_once(
                    uid,
                    RAFFLE_TICKETS["WIN_WEEK"],
                    f"Won Week {week_number}",
                    season=season,
                )

                if is_golden_ticket_week:
                    await RaffleTicketModel.add_tickets_once(
                        uid,
                        RAFFLE_TICKETS["GOLDEN_TICKET_DAY"],
                        f"Golden Ticket Day - Week {week_number}",
                        season=season,
                    )

            # Weekly Top 10 / Weekly Champion - performance ranking (ALL
            # points, not just consistency), a separate track from Weekly
            # Victory above.
            weekly_leaderboard = await UserModel.get_weekly_leaderboard(
                limit=10, week_range=(week_start, week_end, week_number)
            )
            for idx, entry in enumerate(weekly_leaderboard):
                uid = entry["user_id"]
                await RaffleTicketModel.add_tickets_once(
                    uid,
                    RAFFLE_TICKETS["WEEKLY_TOP_10"],
                    f"Week {week_number} Top 10",
                    season=season,
                )
                if idx == 0:
                    await RaffleTicketModel.add_tickets_once(
                        uid,
                        RAFFLE_TICKETS["WEEKLY_CHAMPION"],
                        f"Week {week_number} Champion",
                        season=season,
                    )

            if winners:
                logger.info(
                    f"WEEKLY VICTORY FINALIZED | Season: {season} | Week: {week_number} | "
                    f"Threshold: {threshold} | Winners: {len(winners)}"
                )

            # Announce exactly once per week, whether or not it had winners
            # - re-runs of this (safe/idempotent) function must not re-post.
            if bot and week_number not in BotConfigModel.get_announced_weeks(season):
                from utils.embeds import create_winners_list_embed

                entries = [
                    {"user_id": uid, "detail": f"{round(totals[uid])} pts"}
                    for uid in winners
                ]
                embed = create_winners_list_embed(
                    entries,
                    title=f"🏁 Week {week_number} Victors!",
                    description=(
                        f"Threshold this week: **{threshold}** points."
                        if winners
                        else f"Nobody crossed this week's **{threshold}**-point threshold — "
                        f"everyone's still fully in it for next week. Consistency, not perfection!"
                    ),
                    footer_text=f"{season} Challenge • Weekly Victory",
                )
                await _post_announcement(bot, embed)
                await BotConfigModel.mark_week_announced(week_number, season)

            return winners
        except Exception as e:
            logger.error(f"ERROR | finalize_week | Week: {week_number} | {e}")
            raise

    @staticmethod
    async def get_week_winners(
        week_number: int, season: str = CURRENT_SEASON
    ) -> List[Dict[str, Any]]:
        """All weekly_victories rows for this week, ranked by points earned."""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("weekly_victories")
                .select("*")
                .eq("season", season)
                .eq("week_number", week_number)
                .order("points_earned", desc=True)
                .execute()
            )
            for row in response.data:
                row["mention"] = f"<@{row['user_id']}>"
            return response.data
        except Exception as e:
            logger.error(f"ERROR | get_week_winners | Week: {week_number} | {e}")
            raise

    @staticmethod
    async def get_all_official_finishers(
        season: str = CURRENT_SEASON,
    ) -> List[Dict[str, Any]]:
        """Every user currently flagged is_official_finisher, ranked by
        total_points. season is accepted for API symmetry, but the flag
        itself isn't season-scoped (see users.is_official_finisher)."""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("users")
                .select("*")
                .eq("is_official_finisher", True)
                .order("total_points", desc=True)
                .execute()
            )
            for row in response.data:
                row["mention"] = f"<@{row['user_id']}>"
            return response.data
        except Exception as e:
            logger.error(f"ERROR | get_all_official_finishers | {e}")
            raise

    @staticmethod
    async def get_weeks_won(user_id: int, season: str = CURRENT_SEASON) -> int:
        """Count of weeks this user has won this season."""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("weekly_victories")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("season", season)
                .execute()
            )
            return response.count or 0
        except Exception as e:
            logger.error(f"ERROR | get_weeks_won | User: {user_id} | {e}")
            raise

    @staticmethod
    async def check_and_award_official_finisher(user_id: int, bot=None) -> bool:
        """True only if the user NEWLY became an Official Finisher on this
        call (False if they don't qualify, or already were one - callers
        like check_all_official_finishers rely on this to know who's new,
        not who's currently qualified). Qualifies via either path - weeks
        won >= OFFICIAL_FINISHER_WEEKS_RATIO of the challenge, or
        total_points >= OFFICIAL_FINISHER_POINTS_RATIO of the current
        season leader's total_points (auto-computed every check, no admin
        setup needed - see UserModel.get_highest_total_points; an
        admin-set /<season> setfinisherpoints value overrides this if one
        exists). Grants the badge role, the 500-ticket Championship Raffle
        bonus, and sets the persistent users.is_official_finisher flag the
        first time - the is_official_finisher guard below makes all of that
        naturally one-time, no separate idempotency check needed."""
        import math

        from utils.helpers import get_challenge_week_ranges
        from config.constants import (
            OFFICIAL_FINISHER_WEEKS_RATIO,
            OFFICIAL_FINISHER_POINTS_RATIO,
            RAFFLE_TICKETS,
        )
        from database.bot_config import BotConfigModel

        try:
            user = await UserModel.get_by_id(user_id)
            if not user:
                return False
            if user.get("is_official_finisher"):
                return False

            total_weeks = len(get_challenge_week_ranges())
            if total_weeks == 0:
                return False

            weeks_won = await WeeklyVictoryModel.get_weeks_won(user_id)
            weeks_needed = math.ceil(total_weeks * OFFICIAL_FINISHER_WEEKS_RATIO)
            qualifies = weeks_won >= weeks_needed

            if not qualifies:
                points_threshold = BotConfigModel.get_official_finisher_points_threshold()
                if not points_threshold:
                    highest = await UserModel.get_highest_total_points()
                    points_threshold = round(highest * OFFICIAL_FINISHER_POINTS_RATIO)
                qualifies = bool(points_threshold) and user["total_points"] >= points_threshold

            if not qualifies:
                return False

            supabase = get_supabase()
            supabase.table("users").update({"is_official_finisher": True}).eq(
                "user_id", user_id
            ).execute()

            logger.info(
                f"OFFICIAL FINISHER | User: {user_id} | Weeks won: {weeks_won}/{total_weeks}"
            )

            if bot:
                await UserModel._sync_named_role(
                    bot,
                    user_id,
                    f"{CURRENT_SEASON} — Official Finisher",
                    True,
                    "Official Finisher",
                )

            await RaffleTicketModel.add_tickets(
                user_id, RAFFLE_TICKETS["OFFICIAL_FINISHER"], "Official Finisher"
            )

            return True
        except Exception as e:
            logger.error(
                f"ERROR | check_and_award_official_finisher | User: {user_id} | {e}"
            )
            raise

    @staticmethod
    async def check_all_official_finishers(bot=None) -> List[int]:
        """Re-checks every user who's earned any points for Official
        Finisher status - qualifying via either the weeks-won or the
        total-points path, so it can't be narrowed to just weekly-victory
        winners. Called after finalizing newly-closed weeks."""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("users").select("user_id").gt("total_points", 0).execute()
            )
            user_ids = [row["user_id"] for row in response.data]

            newly_qualified = []
            for uid in user_ids:
                if await WeeklyVictoryModel.check_and_award_official_finisher(
                    uid, bot=bot
                ):
                    newly_qualified.append(uid)

            if bot and newly_qualified:
                from utils.embeds import create_winners_list_embed

                entries = [{"user_id": uid} for uid in newly_qualified]
                embed = create_winners_list_embed(
                    entries,
                    title="🎖️ New Official Finisher(s)!",
                    description="Won 9 of 10 weeks, or hit the season points bar. Badge, role, and 500 raffle tickets, unlocked.",
                    footer_text=f"{CURRENT_SEASON} Challenge • Official Finisher",
                )
                await _post_announcement(bot, embed)

            return newly_qualified
        except Exception as e:
            logger.error(f"ERROR | check_all_official_finishers | {e}")
            raise


class MonthlyVictoryModel:
    """Monthly Victory - win MONTHLY_VICTORY_WEEKS_RATIO of a month's weeks
    (see config.constants.MONTHLY_VICTORY_WEEK_GROUPS). Built entirely from
    weekly_victories rows WeeklyVictoryModel.finalize_week already writes -
    no separate points aggregation needed."""

    @staticmethod
    async def finalize_month(
        month_number: int, bot=None, season: str = CURRENT_SEASON
    ) -> List[int]:
        """Counts each user's weekly_victories rows within this month's week
        range, and for anyone who met MONTHLY_VICTORY_WEEKS_RATIO of that
        range, writes a monthly_victories row (upsert - a finalized month's
        result never changes, so re-running this is a safe no-op) and
        grants the "{season} — Month N Champion" role. Also awards
        Championship Raffle tickets: Win the Month (consistency) to
        monthly_victories winners, and Monthly Top 10 / Monthly Champion
        (performance ranking across the month's full date range - separate
        track, can stack with Win the Month) to the top of that month's
        points leaderboard. Returns the Monthly Victory winning user_ids.
        No-op (returns []) if month_number isn't a configured month group."""
        import math

        from config.constants import (
            MONTHLY_VICTORY_WEEK_GROUPS,
            MONTHLY_VICTORY_WEEKS_RATIO,
            RAFFLE_TICKETS,
        )
        from utils.helpers import get_challenge_week_ranges
        from database.bot_config import BotConfigModel

        week_range = MONTHLY_VICTORY_WEEK_GROUPS.get(month_number)
        if not week_range:
            return []
        first_week, last_week = week_range
        weeks_in_month = last_week - first_week + 1
        weeks_needed = math.ceil(weeks_in_month * MONTHLY_VICTORY_WEEKS_RATIO)

        try:
            supabase = get_supabase()
            response = (
                supabase.table("weekly_victories")
                .select("user_id, week_number")
                .eq("season", season)
                .gte("week_number", first_week)
                .lte("week_number", last_week)
                .execute()
            )

            weeks_won_by_user: Dict[int, int] = {}
            for row in response.data:
                weeks_won_by_user[row["user_id"]] = (
                    weeks_won_by_user.get(row["user_id"], 0) + 1
                )

            winners = [
                uid for uid, count in weeks_won_by_user.items() if count >= weeks_needed
            ]

            for uid in winners:
                supabase.table("monthly_victories").upsert(
                    {
                        "user_id": uid,
                        "season": season,
                        "month_number": month_number,
                        "weeks_won": weeks_won_by_user[uid],
                        "weeks_required": weeks_needed,
                    },
                    on_conflict="user_id,season,month_number",
                ).execute()

                if bot:
                    await UserModel._sync_named_role(
                        bot,
                        uid,
                        f"{season} — Month {month_number} Champion",
                        True,
                        f"Monthly Victory - Month {month_number}",
                    )

                await RaffleTicketModel.add_tickets_once(
                    uid,
                    RAFFLE_TICKETS["WIN_MONTH"],
                    f"Won Month {month_number}",
                    season=season,
                )

            # Monthly Top 10 / Monthly Champion - performance ranking across
            # the month's full date range, a separate track from Monthly
            # Victory above.
            week_dates_by_number = {n: (s, e) for s, e, n in get_challenge_week_ranges()}
            if first_week in week_dates_by_number and last_week in week_dates_by_number:
                month_start = week_dates_by_number[first_week][0]
                month_end = week_dates_by_number[last_week][1]
                monthly_leaderboard = await UserModel.get_monthly_leaderboard(
                    month_start, month_end, limit=10
                )
                for idx, entry in enumerate(monthly_leaderboard):
                    uid = entry["user_id"]
                    await RaffleTicketModel.add_tickets_once(
                        uid,
                        RAFFLE_TICKETS["MONTHLY_TOP_10"],
                        f"Month {month_number} Top 10",
                        season=season,
                    )
                    if idx == 0:
                        await RaffleTicketModel.add_tickets_once(
                            uid,
                            RAFFLE_TICKETS["MONTHLY_CHAMPION"],
                            f"Month {month_number} Champion",
                            season=season,
                        )

            if winners:
                logger.info(
                    f"MONTHLY VICTORY FINALIZED | Season: {season} | Month: {month_number} | "
                    f"Needed: {weeks_needed}/{weeks_in_month} weeks | Winners: {len(winners)}"
                )

            # Announce exactly once per month, whether or not it had
            # winners - re-runs of this (safe/idempotent) function must not
            # re-post.
            if bot and month_number not in BotConfigModel.get_announced_months(season):
                from utils.embeds import create_winners_list_embed

                entries = [
                    {
                        "user_id": uid,
                        "detail": f"{weeks_won_by_user[uid]}/{weeks_in_month} weeks",
                    }
                    for uid in winners
                ]
                embed = create_winners_list_embed(
                    entries,
                    title=f"📆 Month {month_number} Champions!",
                    description=(
                        f"Needed **{weeks_needed} of {weeks_in_month}** weeks won this month."
                        if winners
                        else f"Nobody hit **{weeks_needed} of {weeks_in_month}** weeks this month — "
                        f"still plenty of season left."
                    ),
                    footer_text=f"{season} Challenge • Monthly Victory",
                )
                await _post_announcement(bot, embed)
                await BotConfigModel.mark_month_announced(month_number, season)

            return winners
        except Exception as e:
            logger.error(f"ERROR | finalize_month | Month: {month_number} | {e}")
            raise

    @staticmethod
    async def get_month_winners(
        month_number: int, season: str = CURRENT_SEASON
    ) -> List[Dict[str, Any]]:
        """All monthly_victories rows for this month, ranked by weeks won."""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("monthly_victories")
                .select("*")
                .eq("season", season)
                .eq("month_number", month_number)
                .order("weeks_won", desc=True)
                .execute()
            )
            for row in response.data:
                row["mention"] = f"<@{row['user_id']}>"
            return response.data
        except Exception as e:
            logger.error(f"ERROR | get_month_winners | Month: {month_number} | {e}")
            raise

    @staticmethod
    async def get_months_won(user_id: int, season: str = CURRENT_SEASON) -> int:
        """Count of months this user has won this season."""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("monthly_victories")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("season", season)
                .execute()
            )
            return response.count or 0
        except Exception as e:
            logger.error(f"ERROR | get_months_won | User: {user_id} | {e}")
            raise


class RaffleTicketModel:
    """Championship Raffle tickets (see config.constants.RAFFLE_TICKETS).
    users.raffle_tickets is the running total; raffle_ticket_history is the
    append-only audit ledger, also used to make automatic awards idempotent
    (see add_tickets_once)."""

    @staticmethod
    async def add_tickets(
        user_id: int, tickets: int, reason: str, season: str = CURRENT_SEASON
    ) -> int:
        """Increments users.raffle_tickets and logs the award. Returns the
        new total. Not idempotent by itself - callers driven by a
        re-runnable process (finalize_week/finalize_month) should use
        add_tickets_once instead."""
        try:
            supabase = get_supabase()
            user = await UserModel.get_by_id(user_id)
            if not user:
                return 0
            new_total = user.get("raffle_tickets", 0) + tickets

            supabase.table("users").update({"raffle_tickets": new_total}).eq(
                "user_id", user_id
            ).execute()
            supabase.table("raffle_ticket_history").insert(
                {
                    "user_id": user_id,
                    "season": season,
                    "tickets_change": tickets,
                    "reason": reason,
                }
            ).execute()

            logger.info(
                f"RAFFLE TICKETS | User: {user_id} | +{tickets} | "
                f"New Total: {new_total} | Reason: {reason}"
            )
            return new_total
        except Exception as e:
            logger.error(f"ERROR | add_tickets | User: {user_id} | {e}")
            raise

    @staticmethod
    async def add_tickets_once(
        user_id: int, tickets: int, reason: str, season: str = CURRENT_SEASON
    ) -> bool:
        """Adds tickets only if no raffle_ticket_history row with this exact
        reason already exists for this user - makes automatic ticket awards
        safe to call from idempotent finalize_week/finalize_month re-runs
        (e.g. reason="Won Week 5" only ever fires once per user). Returns
        True if tickets were actually added, False if already awarded."""
        try:
            supabase = get_supabase()
            existing = (
                supabase.table("raffle_ticket_history")
                .select("id")
                .eq("user_id", user_id)
                .eq("reason", reason)
                .execute()
            )
            if existing.data:
                return False

            await RaffleTicketModel.add_tickets(user_id, tickets, reason, season=season)
            return True
        except Exception as e:
            logger.error(
                f"ERROR | add_tickets_once | User: {user_id} | Reason: {reason} | {e}"
            )
            raise

    @staticmethod
    async def get_tickets(user_id: int) -> int:
        """Current raffle ticket total for a user."""
        user = await UserModel.get_by_id(user_id)
        return user.get("raffle_tickets", 0) if user else 0

    @staticmethod
    async def get_ticket_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
        """Top users by raffle_tickets - shows standing ahead of the actual
        draw (see RaffleDrawModel)."""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("users")
                .select("*")
                .gt("raffle_tickets", 0)
                .order("raffle_tickets", desc=True)
                .limit(limit)
                .execute()
            )
            for user in response.data:
                user["mention"] = f"<@{user['user_id']}>"
            return response.data
        except Exception as e:
            logger.error(f"ERROR | get_ticket_leaderboard | {e}")
            raise


class GoldenTicketModel:
    """The four Golden Ticket surprise events from the doc. All are
    moderator-triggered ("no warning, no schedule") - nothing here fires on
    its own; see the /<season> goldenticket* admin commands in
    cogs/admin.py. Values in config.constants.RAFFLE_TICKETS."""

    @staticmethod
    async def flag_golden_ticket_day(updated_by: Optional[int] = None) -> Optional[int]:
        """Flags the CURRENT week as a Golden Ticket Day. Its eventual
        Weekly Victory winners get the GOLDEN_TICKET_DAY bonus on top of
        the normal Win the Week reward, applied when that week finalizes
        (see WeeklyVictoryModel.finalize_week). Returns the flagged week
        number, or None if there's no current week to flag."""
        from utils.helpers import get_current_week_range
        from database.bot_config import BotConfigModel

        week_range = get_current_week_range()
        if not week_range:
            return None
        _, _, week_number = week_range
        await BotConfigModel.flag_golden_ticket_week(week_number, updated_by=updated_by)
        return week_number

    @staticmethod
    async def try_consume_next_n(user_id: int) -> bool:
        """If a "next N people" event is armed (see arm_next_n), consumes
        one slot for this user and grants the bonus. Called from
        DailyActivityModel.award_daily_point - the moment a user completes
        today's habit. Returns True if a slot was consumed."""
        from database.bot_config import BotConfigModel
        from config.constants import RAFFLE_TICKETS

        remaining, token = BotConfigModel.get_golden_ticket_next_n()
        if remaining <= 0 or not token:
            return False

        awarded = await RaffleTicketModel.add_tickets_once(
            user_id,
            RAFFLE_TICKETS["GOLDEN_TICKET_NEXT_N"],
            f"Golden Ticket Next N - {token}",
        )
        if awarded:
            await BotConfigModel.decrement_golden_ticket_next_n()
        return awarded

    @staticmethod
    async def arm_next_n(count: int, updated_by: Optional[int] = None) -> str:
        """Arms the "next N people to complete today's habits" event.
        Returns the token used to dedupe this specific arming in the
        ticket ledger (so re-arming later can reward the same person
        again)."""
        from database.bot_config import BotConfigModel

        token = datetime.utcnow().isoformat()
        await BotConfigModel.arm_golden_ticket_next_n(count, token, updated_by=updated_by)
        return token

    @staticmethod
    async def get_users_who_completed_all_habits_today() -> List[int]:
        """Users with all four trackable daily habits today: activity
        (points already awarded), daily todo, calls post, and a value
        drop post."""
        try:
            supabase = get_supabase()
            today = date.today().isoformat()

            activity_resp = (
                supabase.table("daily_activity")
                .select("user_id")
                .eq("activity_date", today)
                .eq("points_awarded", 1)
                .execute()
            )
            todo_resp = (
                supabase.table("daily_todos")
                .select("user_id")
                .eq("post_date", today)
                .execute()
            )
            calls_resp = (
                supabase.table("calls_posts")
                .select("user_id")
                .eq("post_date", today)
                .execute()
            )
            value_resp = (
                supabase.table("value_posts")
                .select("user_id")
                .eq("post_date", today)
                .execute()
            )

            activity_ids = {r["user_id"] for r in activity_resp.data}
            todo_ids = {r["user_id"] for r in todo_resp.data}
            calls_ids = {r["user_id"] for r in calls_resp.data}
            value_ids = {r["user_id"] for r in value_resp.data}

            return list(activity_ids & todo_ids & calls_ids & value_ids)
        except Exception as e:
            logger.error(f"ERROR | get_users_who_completed_all_habits_today | {e}")
            raise

    @staticmethod
    async def award_all_habits_bonus() -> List[int]:
        """Immediate bonus for everyone who's completed every trackable
        daily habit today. Timestamped reason so re-triggering later in the
        day (or on a different day) can reward people again."""
        from config.constants import RAFFLE_TICKETS

        try:
            user_ids = await GoldenTicketModel.get_users_who_completed_all_habits_today()
            token = datetime.utcnow().isoformat()
            awarded = []
            for uid in user_ids:
                if await RaffleTicketModel.add_tickets_once(
                    uid,
                    RAFFLE_TICKETS["GOLDEN_TICKET_ALL_HABITS"],
                    f"Golden Ticket All Habits - {token}",
                ):
                    awarded.append(uid)
            return awarded
        except Exception as e:
            logger.error(f"ERROR | award_all_habits_bonus | {e}")
            raise

    @staticmethod
    async def award_streak_bonus() -> List[int]:
        """Immediate bonus for everyone currently on a
        GOLDEN_TICKET_STREAK_DAYS-day (or longer) streak. Timestamped
        reason so re-triggering later can reward people again."""
        from config.constants import RAFFLE_TICKETS, GOLDEN_TICKET_STREAK_DAYS

        try:
            supabase = get_supabase()
            response = (
                supabase.table("users")
                .select("user_id")
                .gte("current_streak", GOLDEN_TICKET_STREAK_DAYS)
                .execute()
            )
            token = datetime.utcnow().isoformat()
            awarded = []
            for row in response.data:
                uid = row["user_id"]
                if await RaffleTicketModel.add_tickets_once(
                    uid,
                    RAFFLE_TICKETS["GOLDEN_TICKET_STREAK"],
                    f"Golden Ticket Streak - {token}",
                ):
                    awarded.append(uid)
            return awarded
        except Exception as e:
            logger.error(f"ERROR | award_streak_bonus | {e}")
            raise


class ChampionshipModel:
    """End-of-challenge Grand Championship Leaderboard - fires once the
    challenge window has ended, off the final season leaderboard
    (users.total_points, cumulative across all 74 days). Idempotent per
    user via is_founder/is_grand_champion (mirrors is_official_finisher) +
    RaffleTicketModel's ledger dedup, so safe to call repeatedly (see
    cogs/tasks.py's finalize_weekly_victory_task, which calls this every
    hour once challenge_status() == "ended")."""

    @staticmethod
    async def finalize_challenge_end(bot=None, season: str = CURRENT_SEASON) -> List[int]:
        """Top 25 -> Founder badge/role + tickets. Top 10 -> extra tickets
        (stacks with Top 25). Rank 1 -> Grand Champion badge/role + tickets
        (stacks with both). Returns user_ids newly marked as Founder this
        run."""
        from config.constants import RAFFLE_TICKETS

        try:
            leaderboard = await UserModel.get_leaderboard(limit=25)
            if not leaderboard:
                return []

            supabase = get_supabase()
            newly_founders = []
            newly_grand_champion = None

            for idx, user in enumerate(leaderboard):
                uid = user["user_id"]
                rank = idx + 1

                await RaffleTicketModel.add_tickets_once(
                    uid, RAFFLE_TICKETS["FINAL_TOP_25"], "Final Top 25", season=season
                )
                if not user.get("is_founder"):
                    supabase.table("users").update({"is_founder": True}).eq(
                        "user_id", uid
                    ).execute()
                    if bot:
                        await UserModel._sync_named_role(
                            bot,
                            uid,
                            f"{season} — Founder",
                            True,
                            "Grand Championship - Top 25 Founder",
                        )
                    newly_founders.append(uid)

                if rank <= 10:
                    await RaffleTicketModel.add_tickets_once(
                        uid, RAFFLE_TICKETS["FINAL_TOP_10"], "Final Top 10", season=season
                    )

                if rank == 1:
                    await RaffleTicketModel.add_tickets_once(
                        uid, RAFFLE_TICKETS["GRAND_CHAMPION"], "Grand Champion", season=season
                    )
                    if not user.get("is_grand_champion"):
                        supabase.table("users").update({"is_grand_champion": True}).eq(
                            "user_id", uid
                        ).execute()
                        if bot:
                            await UserModel._sync_named_role(
                                bot,
                                uid,
                                f"{season} — Grand Champion",
                                True,
                                "Grand Champion",
                            )
                        newly_grand_champion = user

            if newly_founders:
                logger.info(
                    f"CHAMPIONSHIP FINALIZED | Season: {season} | "
                    f"New Founders: {len(newly_founders)}"
                )

            if bot and (newly_founders or newly_grand_champion):
                from utils.embeds import create_championship_announcement_embed

                founders_by_id = {u["user_id"]: u for u in leaderboard}
                founder_entries = [founders_by_id[uid] for uid in newly_founders]
                embed = create_championship_announcement_embed(
                    founder_entries, newly_grand_champion
                )
                await _post_announcement(bot, embed)

            return newly_founders
        except Exception as e:
            logger.error(f"ERROR | finalize_challenge_end | {e}")
            raise


class RaffleDrawModel:
    """The actual Championship Raffle Prize Pool draw (Grand Prize / Two /
    Three / Five / Ten Winners - see config.constants.RAFFLE_DRAW_TIERS).
    This is entirely separate from ticket *earning* (RaffleTicketModel) -
    it's the one-time drawing that spends the accumulated ticket pool.
    Admin-triggered only (/<season> raffledraw) - never fires on its own,
    and refuses to re-draw once a season's results exist."""

    @staticmethod
    async def has_been_drawn(season: str = CURRENT_SEASON) -> bool:
        try:
            supabase = get_supabase()
            response = (
                supabase.table("raffle_draw_winners")
                .select("id")
                .eq("season", season)
                .limit(1)
                .execute()
            )
            return bool(response.data)
        except Exception as e:
            logger.error(f"ERROR | has_been_drawn | {e}")
            raise

    @staticmethod
    async def run_draw(bot=None, season: str = CURRENT_SEASON) -> Dict[str, List[int]]:
        """Weighted (by ticket count), no-replacement draw across
        RAFFLE_DRAW_TIERS in order - once picked for a tier, a user is
        removed from the pool for every lower tier, so nobody double-wins.
        Raises ValueError if this season's already been drawn. Returns
        {tier_key: [user_id, ...]}."""
        import random

        from config.constants import RAFFLE_DRAW_TIERS

        if await RaffleDrawModel.has_been_drawn(season):
            raise ValueError(f"Raffle for season {season} has already been drawn.")

        try:
            supabase = get_supabase()
            response = (
                supabase.table("users")
                .select("user_id, raffle_tickets")
                .gt("raffle_tickets", 0)
                .execute()
            )
            pool = [(row["user_id"], row["raffle_tickets"]) for row in response.data]

            results: Dict[str, List[int]] = {}
            for tier_key, (_, winner_count) in RAFFLE_DRAW_TIERS.items():
                winners = []
                for _ in range(min(winner_count, len(pool))):
                    ids = [uid for uid, _ in pool]
                    weights = [tickets for _, tickets in pool]
                    chosen = random.choices(ids, weights=weights, k=1)[0]
                    winners.append(chosen)
                    pool = [p for p in pool if p[0] != chosen]

                for uid in winners:
                    supabase.table("raffle_draw_winners").insert(
                        {"user_id": uid, "season": season, "tier": tier_key}
                    ).execute()

                results[tier_key] = winners

            total_winners = sum(len(w) for w in results.values())
            logger.info(
                f"RAFFLE DRAWN | Season: {season} | Entrants: {len(response.data)} | "
                f"Winners: {total_winners}"
            )

            if bot:
                from utils.embeds import create_raffle_draw_embed

                tier_results = []
                for tier_key, (tier_name, _) in RAFFLE_DRAW_TIERS.items():
                    mentions = [f"<@{uid}>" for uid in results.get(tier_key, [])]
                    tier_results.append((tier_name, mentions))
                embed = create_raffle_draw_embed(tier_results)
                await _post_announcement(bot, embed)

            return results
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"ERROR | run_draw | {e}")
            raise

    @staticmethod
    async def get_draw_results(season: str = CURRENT_SEASON) -> Dict[str, List[Dict[str, Any]]]:
        """Read back a completed draw's results, grouped by tier, in
        RAFFLE_DRAW_TIERS order. {} if nothing's been drawn yet."""
        from config.constants import RAFFLE_DRAW_TIERS

        try:
            supabase = get_supabase()
            response = (
                supabase.table("raffle_draw_winners")
                .select("*")
                .eq("season", season)
                .execute()
            )
            if not response.data:
                return {}

            by_tier: Dict[str, List[Dict[str, Any]]] = {tier: [] for tier in RAFFLE_DRAW_TIERS}
            for row in response.data:
                row["mention"] = f"<@{row['user_id']}>"
                by_tier.setdefault(row["tier"], []).append(row)
            return by_tier
        except Exception as e:
            logger.error(f"ERROR | get_draw_results | {e}")
            raise
