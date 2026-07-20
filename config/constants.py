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

# ----------------------------------------------------------------------
# Weekly Victory / Official Finisher
# ----------------------------------------------------------------------
# Weekly Victory rewards *consistency*, not performance - a member wins the
# week by earning >=51% of what's realistically achievable that week from
# the auto-tracked daily habits: daily activity, daily todo, one
# calls-channel post/day (not code-capped, but that's the realistic
# ceiling), and capped value-drop posts. Deliberately excludes open-ended
# performance/event points (wins, referrals, case studies, reviews) - those
# aren't capped per week, and already drive the season/weekly leaderboard
# separately (see points_history.category and UserModel.update_points).
_WEEKLY_VICTORY_MAX_POINTS = 7 * (
    POINTS["DAILY_ACTIVITY"]
    + POINTS["DAILY_TODO"] * MAX_TODO_POSTS_PER_DAY
    + POINTS["CALLS_POST"]
    + MAX_VALUE_POSTS_PER_DAY * MAX_POINTS_PER_POST
)
# Default Weekly Victory threshold - overridable via
# /<season> setweeklyvictorythreshold (see BotConfigModel.get_weekly_victory_threshold)
# without touching code, same pattern as tier thresholds.
WEEKLY_VICTORY_THRESHOLD_DEFAULT = round(_WEEKLY_VICTORY_MAX_POINTS * 0.51)

# Official Finisher, path 1: win at least this fraction of the challenge's
# weeks (doc: "9 of 10 weeks"). Computed automatically from the configured
# challenge window - no setup needed.
OFFICIAL_FINISHER_WEEKS_RATIO = 0.9

# Official Finisher, path 2 (doc: "~80-85% of all available challenge
# points"): there's no fixed ceiling to take a percentage of once open-ended
# performance points (wins, referrals) are in play, so instead of a fixed
# number this is computed live as this fraction of whatever the current
# season leader's total_points is (see
# UserModel.get_highest_total_points / WeeklyVictoryModel.check_and_award_official_finisher) -
# fully automatic, no admin setup needed. /<season> setfinisherpoints can
# still pin a fixed number instead, if ever wanted.
OFFICIAL_FINISHER_POINTS_RATIO = 0.825  # midpoint of the doc's 80-85% range

# Monthly Victory (doc: "win 3 of the 4 weeks, or 4 of 5 if needed"). The
# reward table only ever names a "Month One Milestone" (Week 4) and "Month
# Two Milestone" (Week 8) - no third month is defined, so Weeks 9-10 (this
# season's leftover after two 4-week months) intentionally belong to no
# month. {month_number: (first_week_number, last_week_number)}, both
# inclusive - update this if the challenge dates/week count ever change.
MONTHLY_VICTORY_WEEK_GROUPS = {
    1: (1, 4),
    2: (5, 8),
}
# ceil(4 * 0.75) = 3, ceil(5 * 0.75) = 4 - reproduces both cases the doc
# states ("3 of 4" / "4 of 5") from one ratio, applied to however many
# weeks are actually in a given month group.
MONTHLY_VICTORY_WEEKS_RATIO = 0.75

# Championship Raffle ticket values - straight from the doc's "Championship
# Raffle" section. Weekly Top 10 / Weekly Champion / Monthly Top 10 /
# Monthly Champion are performance (leaderboard ranking that week/month),
# separate from and stacking with Win the Week / Win the Month
# (consistency - crossing the Weekly/Monthly Victory threshold) - the doc
# is explicit these can both apply to the same person. FINAL_TOP_25 /
# FINAL_TOP_10 / GRAND_CHAMPION fire once, at challenge end, off the final
# season leaderboard. The four GOLDEN_TICKET_* values are moderator-
# triggered surprise bonuses (see cogs/admin.py's /q2 goldenticket* commands
# and database/models.py's GoldenTicketModel) - "no warning, no schedule"
# per the doc, so these are never fired automatically on their own.
RAFFLE_TICKETS = {
    "WIN_WEEK": 25,
    "WEEKLY_TOP_10": 25,
    "WEEKLY_CHAMPION": 100,
    "WIN_MONTH": 100,
    "MONTHLY_TOP_10": 100,
    "MONTHLY_CHAMPION": 250,
    "OFFICIAL_FINISHER": 500,
    "FINAL_TOP_25": 250,
    "FINAL_TOP_10": 500,
    "GRAND_CHAMPION": 1000,
    "GOLDEN_TICKET_DAY": 100,  # "anyone who wins the week that day" (the flagged week)
    "GOLDEN_TICKET_NEXT_N": 25,  # each of "the next N people to complete today's habits"
    "GOLDEN_TICKET_STREAK": 50,  # "everyone currently on a 14-day streak"
    "GOLDEN_TICKET_ALL_HABITS": 100,  # "everyone who completes every habit today"
}

# "The next N people to complete today's habits" - doc says 25.
GOLDEN_TICKET_NEXT_N_DEFAULT = 25

# "Everyone currently on a 14-day streak" - doc says 14.
GOLDEN_TICKET_STREAK_DAYS = 14

# Championship Raffle Prize Pool draw tiers, in draw order (highest tier
# first). Drawn weighted by ticket count, without replacement - once a
# user is picked for a tier they're removed from the pool for every
# lower tier, so nobody double-wins. {tier_key: (display name, winner count)}
RAFFLE_DRAW_TIERS = {
    "grand_prize": ("Grand Prize Winner", 1),
    "two_winners": ("Two Winners", 2),
    "three_winners": ("Three Winners", 3),
    "five_winners": ("Five Winners", 5),
    "ten_winners": ("Ten Winners", 10),
}
