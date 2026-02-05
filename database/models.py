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
                return response.data[0]

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
            logger.info(f"✅ Created new user: {username} ({user_id})")
            return response.data[0]

        except Exception as e:
            logger.error(f"❌ Error in get_or_create for user {user_id}: {e}")
            raise

    @staticmethod
    async def update_points(
        user_id: int, points_change: int, reason: str
    ) -> Dict[str, Any]:
        """Update user points and tier"""
        try:
            supabase = get_supabase()

            # Get current user
            user = await UserModel.get_by_id(user_id)
            new_total = user["total_points"] + points_change

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

            logger.info(
                f"✅ Updated points for user {user_id}: {points_change:+d} ({reason})"
            )
            return response.data[0]

        except Exception as e:
            logger.error(f"❌ Error updating points for user {user_id}: {e}")
            raise

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
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"❌ Error getting user {user_id}: {e}")
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
            return response.data
        except Exception as e:
            logger.error(f"❌ Error getting leaderboard: {e}")
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

            logger.info(f"✅ Set scaler status for user {user_id}: {is_scaler}")
            return response.data[0]
        except Exception as e:
            logger.error(f"❌ Error setting scaler for user {user_id}: {e}")
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
                return response.data[0]

        except Exception as e:
            logger.error(f"❌ Error tracking activity for user {user_id}: {e}")
            raise

    @staticmethod
    async def award_daily_point(user_id: int, activity_date: date = None) -> bool:
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

                await UserModel.update_points(user_id, 1, "Daily activity")
                return True

            return False

        except Exception as e:
            logger.error(f"❌ Error awarding daily point for user {user_id}: {e}")
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
            return response.data[0]

        except Exception as e:
            logger.error(f"❌ Error creating value post {message_id}: {e}")
            raise

    @staticmethod
    async def update_reactions(
        message_id: int, fire: int, gem: int, hundred: int
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

            # Update user points if changed
            if points_diff != 0:
                await UserModel.update_points(
                    current_post["user_id"],
                    points_diff,
                    f"Value post reactions updated",
                )

            return response.data[0]

        except Exception as e:
            logger.error(f"❌ Error updating reactions for post {message_id}: {e}")
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
            logger.error(f"❌ Error getting user posts for {user_id}: {e}")
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
            logger.info(f"✅ Created submission for user {user_id}: {submission_type}")
            return response.data[0]

        except Exception as e:
            logger.error(f"❌ Error creating submission: {e}")
            raise

    @staticmethod
    async def approve(
        submission_id: int, reviewed_by: int, points: int
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
            )

            logger.info(f"✅ Approved submission {submission_id}: +{points} points")
            return updated.data[0]

        except Exception as e:
            logger.error(f"❌ Error approving submission {submission_id}: {e}")
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

            logger.info(f"✅ Rejected submission {submission_id}")
            return response.data[0]

        except Exception as e:
            logger.error(f"❌ Error rejecting submission {submission_id}: {e}")
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
            logger.error(f"❌ Error getting pending submissions: {e}")
            raise
