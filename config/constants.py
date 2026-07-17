POINTS = {
    "DAILY_ACTIVITY": 1,
    "DAILY_TODO": 1,  # New: 1 point for posting daily todo
    "CALLS_POST": 1,  # New: 1 point for posting in calls channel
    "REACTION": 0.25,
    "FIRE_EMOJI": 3,
    "GEM_EMOJI": 3,
    "HUNDRED_EMOJI": 5,
    "PINNED": 15,
    "FIRST_SALE": 3,
    "WIN_100": 5,
    "WIN_500": 15,
    "WIN_1K": 30,
    "WIN_5K": 75,
    "CASE_STUDY": 25,
    "WHOP_REFERRAL": 10,
    "DISCORD_REFERRAL": 5,
    "REVIEW_5STAR": 5,  # New: 5-star review, proof posted in reviews channel
    "REVIEW_5STAR_WITH_REASON": 10,  # New: 5-star review + written reason (flat total, not additive)
}

# Current active season/challenge. This is the single knob for launching a
# new season: bump it (e.g. "Q3") and restart the bot - every season-prefixed
# slash command name (/q2addpoints -> /q3addpoints, etc.) and Discord role
# name below regenerates automatically. No per-command renaming needed.
# Previous seasons' Discord roles are left untouched (nothing removes them),
# they're just no longer what the bot actively manages.
CURRENT_SEASON = "Q2"

# Command name prefix derived from CURRENT_SEASON, e.g. "q2" -> /q2addpoints.
SEASON_PREFIX = CURRENT_SEASON.lower()

# Tier thresholds. These are only the DEFAULTS - the actual live minimums are
# read through UserModel.calculate_tier() via BotConfigModel.get_tier_thresholds(),
# which falls back to the "min" values here until an admin overrides one via
# /<season> settierpoints. role_name/emoji are not overridable (only points are).
TIERS = {
    "OBSERVER": {"min": 0, "max": 49, "role_name": f"{CURRENT_SEASON} — Challenger", "emoji": "🟤"},
    "BUILDER": {"min": 50, "max": 149, "role_name": f"{CURRENT_SEASON} — Builder", "emoji": "🟢"},
    "OPERATOR": {"min": 150, "max": 299, "role_name": f"{CURRENT_SEASON} — Operator", "emoji": "🔵"},
    "ELITE": {
        "min": 300,
        "max": float("inf"),
        "role_name": f"{CURRENT_SEASON} — Elite",
        "emoji": "🟣",
    },
}

# Scaler role: fully manual, not tied to points at all. Grant/revoke it the
# same way you would any other Discord role (or see UserModel.set_scaler if a
# command is ever wanted for it later) - grants access to the private
# #scalers channel (permissions wired manually in Discord).
SCALER_ROLE_NAME = f"{CURRENT_SEASON} — Scaler"

# Masters role: NOT tied to points/season. Granted manually via /<season>setmaster
# to members who bought the masterclass product on Whop. Grants a +15% point
# bonus on wins and value-drop posts (see UserModel.update_points /
# ValuePostModel.update_reactions).
MASTER_ROLE_NAME = "Masters 🥋"
MASTER_BONUS_MULTIPLIER = 1.15

# Limits - These values can be overridden by settings.py
MAX_VALUE_POSTS_PER_DAY = 2
MAX_POINTS_PER_POST = 30
MAX_TODO_POSTS_PER_DAY = 1  # New: 1 daily todo post per day

BRAND_COLOR = 0x719DCB
