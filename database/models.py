from typing import Optional, List, Dict, Any
from datetime import date, datetime
from database.supabase_client import get_supabase
from utils.logger import get_logger
from config.constants import TIERS, CURRENT_SEASON, SCALER_ROLE_NAME, MASTER_ROLE_NAME

logger = get_logger(__name__)


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
        user_id: int, points_change: int, reason: str, bot=None
    ) -> Dict[str, Any]:
        """Update user points and tier, and update Discord roles immediately"""
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
                {"user_id": user_id, "points_change": points_change, "reason": reason}
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

            updated_user = await UserModel.update_points(user_id, points, reason, bot=bot)
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
        """Award daily activity point if not already awarded"""
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
