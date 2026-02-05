import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Discord Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Channel IDs
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID"))
WINS_CHANNEL_ID = int(os.getenv("WINS_CHANNEL_ID"))
VALUE_DROPS_CHANNEL_ID = int(os.getenv("VALUE_DROPS_CHANNEL_ID"))
SUBMISSIONS_CHANNEL_ID = int(os.getenv("SUBMISSIONS_CHANNEL_ID"))
ANNOUNCEMENTS_CHANNEL_ID = int(os.getenv("ANNOUNCEMENTS_CHANNEL_ID"))

# Challenge Settings
CHALLENGE_START_DATE = datetime.strptime(os.getenv("CHALLENGE_START_DATE"), "%Y-%m-%d")
CHALLENGE_END_DATE = datetime.strptime(os.getenv("CHALLENGE_END_DATE"), "%Y-%m-%d")
PRIZE_AMOUNT = int(os.getenv("PRIZE_AMOUNT", 1000))

# Point Limits
MAX_REFERRALS = int(os.getenv("MAX_REFERRALS", 10))
MAX_VALUE_POSTS_PER_DAY = int(os.getenv("MAX_VALUE_POSTS_PER_DAY", 2))
MAX_POINTS_PER_POST = int(os.getenv("MAX_POINTS_PER_POST", 30))

# Validation
required_vars = [
    DISCORD_TOKEN,
    GUILD_ID,
    SUPABASE_URL,
    SUPABASE_KEY,
    ADMIN_ROLE_ID,
    MOD_ROLE_ID,
]

if not all(required_vars):
    raise ValueError("Missing required environment variables. Check .env file.")
