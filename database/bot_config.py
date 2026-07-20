import json
from typing import Any, Optional

from database.supabase_client import get_supabase
from utils.logger import get_logger

logger = get_logger(__name__)

# Falls back to the matching env var (config.settings) if a key has never been
# set via a slash command yet, so nothing breaks before the admin runs /q2setchannel.
_CHANNEL_ENV_FALLBACK = {
    "value_drops": "VALUE_DROPS_CHANNEL_ID",
    "daily_todo": "DAILY_TODO_CHANNEL_ID",
    "calls": "CALLS_CHANNEL_ID",
    "scalers": None,
    "leaderboard": "LEADERBOARD_CHANNEL_ID",
    "log": "LOG_CHANNEL_ID",
    "announcements": "ANNOUNCEMENTS_CHANNEL_ID",
    "wins": "WINS_CHANNEL_ID",
    "reviews": None,
}

VALID_CHANNEL_TYPES = list(_CHANNEL_ENV_FALLBACK.keys())


class BotConfigModel:
    """DB-backed key/value config (channel IDs, value-drop emoji points, scaler threshold),
    cached in memory so hot paths (on_message, reactions) never hit the DB."""

    _cache: dict[str, str] = {}
    _loaded = False

    @classmethod
    async def load_cache(cls):
        """Load all config rows into memory. Call once from bot startup."""
        try:
            supabase = get_supabase()
            response = supabase.table("bot_config").select("*").execute()
            cls._cache = {row["key"]: row["value"] for row in response.data}
            cls._loaded = True
            logger.info(f"✅ Loaded {len(cls._cache)} bot_config entries")
        except Exception as e:
            logger.error(f"ERROR | BotConfigModel.load_cache | {e}")
            cls._cache = {}

    @classmethod
    def get(cls, key: str, default: Optional[str] = None) -> Optional[str]:
        return cls._cache.get(key, default)

    @classmethod
    async def set(cls, key: str, value: str, updated_by: Optional[int] = None):
        try:
            supabase = get_supabase()
            supabase.table("bot_config").upsert(
                {"key": key, "value": value, "updated_by": updated_by}
            ).execute()
            cls._cache[key] = value
            logger.info(f"BOT CONFIG SET | {key} = {value} | By: {updated_by}")
        except Exception as e:
            logger.error(f"ERROR | BotConfigModel.set | {key} | {e}")
            raise

    @classmethod
    def get_channel_id(cls, channel_type: str) -> Optional[int]:
        """Look up a configured channel ID, falling back to the legacy env var."""
        raw = cls._cache.get(f"channel.{channel_type}")
        if raw:
            return int(raw)

        env_var_name = _CHANNEL_ENV_FALLBACK.get(channel_type)
        if not env_var_name:
            return None

        import os

        env_value = os.getenv(env_var_name)
        return int(env_value) if env_value else None

    @classmethod
    async def set_channel_id(cls, channel_type: str, channel_id: int, updated_by: Optional[int] = None):
        await cls.set(f"channel.{channel_type}", str(channel_id), updated_by)

    @classmethod
    def get_value_drop_emojis(cls) -> dict[str, float]:
        """Returns {emoji: points} map used to score value-drop reactions.
        Fixed at these defaults - no admin command to change them."""
        raw = cls._cache.get("value_drop_emojis")
        if not raw:
            return {"🔥": 3, "💎": 3, "💯": 5}
        return json.loads(raw)

    @classmethod
    def get_tier_thresholds(cls) -> dict[str, int]:
        """Returns {tier_name: min_points} for the 4 tiers, overridable via
        /<season> settierpoints. Falls back to config.constants.TIERS defaults
        for any tier that's never been overridden."""
        from config.constants import TIERS

        defaults = {name: data["min"] for name, data in TIERS.items()}
        raw = cls._cache.get("tier_thresholds")
        if not raw:
            return defaults
        overrides = json.loads(raw)
        defaults.update(overrides)
        return defaults

    @classmethod
    async def set_tier_threshold(
        cls, tier_name: str, min_points: int, updated_by: Optional[int] = None
    ):
        thresholds = cls.get_tier_thresholds()
        thresholds[tier_name] = min_points
        await cls.set("tier_thresholds", json.dumps(thresholds), updated_by)

    @classmethod
    def get_role_id(cls, role_type: str) -> Optional[int]:
        """Look up a configured role ID (e.g. 'masters', 'scalers'), set via
        /<season> setrole. None if never configured - caller falls back to the
        hardcoded MASTER_ROLE_NAME/SCALER_ROLE_NAME name lookup."""
        raw = cls._cache.get(f"role.{role_type}")
        return int(raw) if raw else None

    @classmethod
    async def set_role_id(cls, role_type: str, role_id: int, updated_by: Optional[int] = None):
        await cls.set(f"role.{role_type}", str(role_id), updated_by)

    @classmethod
    def get_challenge_window(cls):
        """Returns (start_date: str, end_date: str, timezone: str) as set via
        /<season>setchallengedates, or None if never configured."""
        start_raw = cls._cache.get("challenge_start_date")
        end_raw = cls._cache.get("challenge_end_date")
        if not start_raw or not end_raw:
            return None
        timezone = cls._cache.get("challenge_timezone", "UTC")
        return start_raw, end_raw, timezone

    @classmethod
    async def set_challenge_dates(
        cls,
        start_date: str,
        end_date: str,
        timezone: str,
        updated_by: Optional[int] = None,
    ):
        await cls.set("challenge_start_date", start_date, updated_by)
        await cls.set("challenge_end_date", end_date, updated_by)
        await cls.set("challenge_timezone", timezone, updated_by)

    @classmethod
    def get_weekly_victory_threshold(cls) -> int:
        """Points needed to win a week - defaults to the auto-computed
        WEEKLY_VICTORY_THRESHOLD_DEFAULT, overridable via
        /<season> setweeklyvictorythreshold."""
        from config.constants import WEEKLY_VICTORY_THRESHOLD_DEFAULT

        raw = cls._cache.get("weekly_victory_threshold")
        return int(raw) if raw else WEEKLY_VICTORY_THRESHOLD_DEFAULT

    @classmethod
    async def set_weekly_victory_threshold(
        cls, points: int, updated_by: Optional[int] = None
    ):
        await cls.set("weekly_victory_threshold", str(points), updated_by)

    @classmethod
    def get_official_finisher_points_threshold(cls) -> Optional[int]:
        """Total season points needed for the alternate Official Finisher
        path (the doc's '~80-85% of all available points'). None until an
        admin sets one via /<season> setfinisherpoints - there's no safe
        automatic ceiling since wins/referrals are open-ended. The
        weeks-won path (OFFICIAL_FINISHER_WEEKS_RATIO) works without this."""
        raw = cls._cache.get("official_finisher_points_threshold")
        return int(raw) if raw else None

    @classmethod
    async def set_official_finisher_points_threshold(
        cls, points: int, updated_by: Optional[int] = None
    ):
        await cls.set("official_finisher_points_threshold", str(points), updated_by)

    @classmethod
    def get_golden_ticket_weeks(cls) -> list:
        """Week numbers flagged as a Golden Ticket Day (see /<season>
        goldenticket day) - anyone who wins one of these weeks gets the
        GOLDEN_TICKET_DAY bonus on top of the normal Win the Week reward,
        applied when that week finalizes (see WeeklyVictoryModel.finalize_week)."""
        raw = cls._cache.get("golden_ticket_weeks")
        return json.loads(raw) if raw else []

    @classmethod
    async def flag_golden_ticket_week(cls, week_number: int, updated_by: Optional[int] = None):
        weeks = cls.get_golden_ticket_weeks()
        if week_number not in weeks:
            weeks.append(week_number)
            await cls.set("golden_ticket_weeks", json.dumps(weeks), updated_by)

    @classmethod
    def get_golden_ticket_next_n(cls) -> tuple:
        """Returns (remaining, token) for an armed "next N people" Golden
        Ticket event (see /<season> goldenticket next25) - remaining counts
        down as people complete today's first habit action; token makes
        each arming's ticket-history reason unique so the same person can
        benefit from a later re-arming. (0, None) if nothing is armed."""
        remaining_raw = cls._cache.get("golden_ticket_next_n_remaining")
        token = cls._cache.get("golden_ticket_next_n_token")
        remaining = int(remaining_raw) if remaining_raw else 0
        return remaining, token

    @classmethod
    async def arm_golden_ticket_next_n(
        cls, count: int, token: str, updated_by: Optional[int] = None
    ):
        await cls.set("golden_ticket_next_n_remaining", str(count), updated_by)
        await cls.set("golden_ticket_next_n_token", token, updated_by)

    @classmethod
    async def decrement_golden_ticket_next_n(cls):
        remaining, _ = cls.get_golden_ticket_next_n()
        if remaining > 0:
            await cls.set("golden_ticket_next_n_remaining", str(remaining - 1))

    @classmethod
    def get_announced_weeks(cls, season: str) -> list:
        """Week numbers already auto-announced this season - lets
        finalize_week (re-run hourly, safe to repeat) post its winners
        announcement exactly once, whether or not the week had any
        winners."""
        raw = cls._cache.get(f"announced_weeks_{season}")
        return json.loads(raw) if raw else []

    @classmethod
    async def mark_week_announced(cls, week_number: int, season: str):
        weeks = cls.get_announced_weeks(season)
        if week_number not in weeks:
            weeks.append(week_number)
            await cls.set(f"announced_weeks_{season}", json.dumps(weeks))

    @classmethod
    def get_announced_months(cls, season: str) -> list:
        """Same as get_announced_weeks, for Monthly Victory."""
        raw = cls._cache.get(f"announced_months_{season}")
        return json.loads(raw) if raw else []

    @classmethod
    async def mark_month_announced(cls, month_number: int, season: str):
        months = cls.get_announced_months(season)
        if month_number not in months:
            months.append(month_number)
            await cls.set(f"announced_months_{season}", json.dumps(months))
