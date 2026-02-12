# # Point Values
# POINTS = {
#     "DAILY_ACTIVITY": 1,
#     "DAILY_TODO": 1,  # New: 1 point for posting daily todo
#     "REACTION": 0.25,
#     "FIRE_EMOJI": 3,
#     "GEM_EMOJI": 3,
#     "HUNDRED_EMOJI": 5,
#     "PINNED": 15,
#     "FIRST_SALE": 3,
#     "WIN_100": 5,
#     "WIN_500": 15,
#     "WIN_1K": 30,
#     "WIN_5K": 75,
#     "CASE_STUDY": 25,
#     "WHOP_REFERRAL": 10,
#     "DISCORD_REFERRAL": 5,
# }

# # Tier Thresholds
# TIERS = {
#     "OBSERVER": {"min": 0, "max": 49, "role_name": "Q1 — Challenger", "emoji": "🟤"},
#     "BUILDER": {"min": 50, "max": 149, "role_name": "Q1 — Builder", "emoji": "🟢"},
#     "OPERATOR": {"min": 150, "max": 299, "role_name": "Q1 — Operator", "emoji": "🔵"},
#     "ELITE": {
#         "min": 300,
#         "max": float("inf"),
#         "role_name": "Q1 — Elite",
#         "emoji": "🟣",
#     },
# }

# # Emojis
# TRACK_EMOJIS = {
#     "fire": "🔥",
#     "gem": "💎",
#     "hundred": "💯",
# }

# # Submission Types
# SUBMISSION_TYPES = {
#     "WIN": "win",
#     "REFERRAL": "referral",
#     "SCALER": "scaler_application",
# }

# # Referral Types
# REFERRAL_TYPES = {
#     "WHOP": "whop",
#     "DISCORD": "discord",
# }

# # Submission Status
# SUBMISSION_STATUS = {
#     "PENDING": "pending",
#     "APPROVED": "approved",
#     "REJECTED": "rejected",
# }

# # Limits - These values can be overridden by settings.py
# MAX_VALUE_POSTS_PER_DAY = 2
# MAX_POINTS_PER_POST = 30
# MAX_TODO_POSTS_PER_DAY = 1  # New: 1 daily todo post per day

# BRAND_COLOR = 0x719DCB

# Point Values
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
}

# Tier Thresholds
TIERS = {
    "OBSERVER": {"min": 0, "max": 49, "role_name": "Q1 — Challenger", "emoji": "🟤"},
    "BUILDER": {"min": 50, "max": 149, "role_name": "Q1 — Builder", "emoji": "🟢"},
    "OPERATOR": {"min": 150, "max": 299, "role_name": "Q1 — Operator", "emoji": "🔵"},
    "ELITE": {
        "min": 300,
        "max": float("inf"),
        "role_name": "Q1 — Elite",
        "emoji": "🟣",
    },
}

# Emojis
TRACK_EMOJIS = {
    "fire": "🔥",
    "gem": "💎",
    "hundred": "💯",
}

# Submission Types
SUBMISSION_TYPES = {
    "WIN": "win",
    "REFERRAL": "referral",
    "SCALER": "scaler_application",
}

# Referral Types
REFERRAL_TYPES = {
    "WHOP": "whop",
    "DISCORD": "discord",
}

# Submission Status
SUBMISSION_STATUS = {
    "PENDING": "pending",
    "APPROVED": "approved",
    "REJECTED": "rejected",
}

# Limits - These values can be overridden by settings.py
MAX_VALUE_POSTS_PER_DAY = 2
MAX_POINTS_PER_POST = 30
MAX_TODO_POSTS_PER_DAY = 1  # New: 1 daily todo post per day

BRAND_COLOR = 0x719DCB
