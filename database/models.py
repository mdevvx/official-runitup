from typing import Optional, List, Dict, Any
from datetime import date, datetime
from database.supabase_client import get_supabase
from utils.logger import get_logger
from config.constants import TIERS

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
        """Calculate tier based on points"""
        for tier_name, tier_data in TIERS.items():
            if tier_data["min"] <= points <= tier_data["max"]:
                return tier_name
        return "OBSERVER"

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
        """Get top users by points"""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("users")
                .select("*")
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
    async def set_scaler(user_id: int, is_scaler: bool = True) -> Dict[str, Any]:
        """Set user as scaler"""
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
            user_data = response.data[0]
            user_data["mention"] = f"<@{user_id}>"
            return user_data
        except Exception as e:
            logger.error(f"ERROR | set_scaler | User: {user_id} | {e}")
            raise


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
                "fire_count": 0,
                "gem_count": 0,
                "hundred_count": 0,
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
        message_id: int, fire: int, gem: int, hundred: int, bot=None
    ) -> Dict[str, Any]:
        """Update reaction counts and recalculate points"""
        try:
            from config.constants import POINTS, MAX_POINTS_PER_POST

            supabase = get_supabase()

            # Calculate points
            points = (
                (fire * POINTS["FIRE_EMOJI"])
                + (gem * POINTS["GEM_EMOJI"])
                + (hundred * POINTS["HUNDRED_EMOJI"])
            )

            # Cap points
            points = min(points, MAX_POINTS_PER_POST)

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
            old_points = current_post["total_points"]
            points_diff = points - old_points

            # Update post
            response = (
                supabase.table("value_posts")
                .update(
                    {
                        "fire_count": fire,
                        "gem_count": gem,
                        "hundred_count": hundred,
                        "total_points": points,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("message_id", message_id)
                .execute()
            )

            # Log reaction update
            logger.info(
                f"REACTIONS UPDATED | Message: {message_id} | "
                f"Fire:{fire} Gem:{gem} 100:{hundred} | Points: {old_points}->{points}"
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
        """Get count of user's posts today"""
        try:
            supabase = get_supabase()
            today = date.today().isoformat()

            response = (
                supabase.table("value_posts")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("post_date", today)
                .execute()
            )

            return response.count or 0

        except Exception as e:
            logger.error(f"ERROR | get_user_posts_today | User: {user_id} | {e}")
            raise


class SubmissionModel:
    @staticmethod
    async def create(
        user_id: int,
        submission_type: str,
        description: str = None,
        proof_url: str = None,
        amount: float = None,
        referral_type: str = None,
    ) -> Dict[str, Any]:
        """Create new submission"""
        try:
            supabase = get_supabase()

            new_submission = {
                "user_id": user_id,
                "submission_type": submission_type,
                "status": "pending",
                "description": description,
                "proof_url": proof_url,
                "amount": amount,
                "referral_type": referral_type,
            }

            response = supabase.table("submissions").insert(new_submission).execute()
            logger.info(
                f"SUBMISSION CREATED | User: {user_id} | Type: {submission_type}"
            )
            return response.data[0]

        except Exception as e:
            logger.error(f"ERROR | create_submission | User: {user_id} | {e}")
            raise

    @staticmethod
    async def approve(
        submission_id: int, reviewed_by: int, points: int, bot=None
    ) -> Dict[str, Any]:
        """Approve submission and award points"""
        try:
            supabase = get_supabase()

            # Get submission
            response = (
                supabase.table("submissions")
                .select("*")
                .eq("id", submission_id)
                .execute()
            )

            if not response.data:
                raise ValueError(f"Submission {submission_id} not found")

            submission = response.data[0]

            # Update submission
            updated = (
                supabase.table("submissions")
                .update(
                    {
                        "status": "approved",
                        "points_awarded": points,
                        "reviewed_by": reviewed_by,
                        "reviewed_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", submission_id)
                .execute()
            )

            # Award points to user
            await UserModel.update_points(
                submission["user_id"],
                points,
                f"{submission['submission_type']} approved",
                bot=bot,
            )

            logger.info(
                f"SUBMISSION APPROVED | ID: {submission_id} | Points: +{points}"
            )
            return updated.data[0]

        except Exception as e:
            logger.error(f"ERROR | approve_submission | ID: {submission_id} | {e}")
            raise

    @staticmethod
    async def reject(submission_id: int, reviewed_by: int) -> Dict[str, Any]:
        """Reject submission"""
        try:
            supabase = get_supabase()

            response = (
                supabase.table("submissions")
                .update(
                    {
                        "status": "rejected",
                        "reviewed_by": reviewed_by,
                        "reviewed_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", submission_id)
                .execute()
            )

            logger.info(f"SUBMISSION REJECTED | ID: {submission_id}")
            return response.data[0]

        except Exception as e:
            logger.error(f"ERROR | reject_submission | ID: {submission_id} | {e}")
            raise

    @staticmethod
    async def get_pending() -> List[Dict[str, Any]]:
        """Get all pending submissions"""
        try:
            supabase = get_supabase()
            response = (
                supabase.table("submissions")
                .select("*")
                .eq("status", "pending")
                .order("created_at", desc=False)
                .execute()
            )
            return response.data
        except Exception as e:
            logger.error(f"ERROR | get_pending_submissions | {e}")
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
            }

            response = supabase.table("daily_todos").insert(new_post).execute()
            logger.info(f"TODO POST CREATED | User: {user_id} | Message: {message_id}")
            return response.data[0]

        except Exception as e:
            logger.error(f"ERROR | create_todo_post | Message: {message_id} | {e}")
            raise

    @staticmethod
    async def get_user_posts_today(user_id: int) -> int:
        """Get count of user's todo posts today"""
        try:
            supabase = get_supabase()
            today = date.today().isoformat()

            response = (
                supabase.table("daily_todos")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("post_date", today)
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
            }

            response = supabase.table("calls_posts").insert(new_post).execute()
            logger.info(f"CALLS POST CREATED | User: {user_id} | Message: {message_id}")
            return response.data[0]

        except Exception as e:
            logger.error(f"ERROR | create_calls_post | Message: {message_id} | {e}")
            raise
