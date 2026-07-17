import os
from dotenv import load_dotenv

load_dotenv()

# Discord Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Channel IDs - all optional legacy fallbacks now. The real source of truth is
# /<season>setchannel (see database.bot_config.BotConfigModel.get_channel_id),
# which falls back to these only if a channel type has never been registered
# via that command. None of these being unset will crash startup.
def _optional_channel_id(env_var: str):
    raw = os.getenv(env_var)
    return int(raw) if raw else None


LEADERBOARD_CHANNEL_ID = _optional_channel_id("LEADERBOARD_CHANNEL_ID")
WINS_CHANNEL_ID = _optional_channel_id("WINS_CHANNEL_ID")
VALUE_DROPS_CHANNEL_ID = _optional_channel_id("VALUE_DROPS_CHANNEL_ID")
DAILY_TODO_CHANNEL_ID = _optional_channel_id("DAILY_TODO_CHANNEL_ID")
CALLS_CHANNEL_ID = _optional_channel_id("CALLS_CHANNEL_ID")
ANNOUNCEMENTS_CHANNEL_ID = _optional_channel_id("ANNOUNCEMENTS_CHANNEL_ID")
LOG_CHANNEL_ID = _optional_channel_id("LOG_CHANNEL_ID")

# Challenge Settings
# Dates are command-only now (/<season> setchallengedates - see
# database.bot_config.BotConfigModel), never read from .env. No hardcoded
# fallback here on purpose - it was causing stale expired dates to silently
# take over whenever the command hadn't been run yet.
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

# Branding
LEADERBOARD_IMAGE_URL = os.getenv(
    "LEADERBOARD_IMAGE_URL",
    "https://your-image-url-here.com/leaderboard.png",  # Replace with your actual image URL
)

DIALED_GUILD_ID = int(os.getenv("DIALED_GUILD_ID"))
DIALED_WINS_CHANNEL_ID = int(os.getenv("DIALED_WINS_CHANNEL_ID"))
RUNITUP_WINS_CHANNEL_ID = int(os.getenv("RUNITUP_WINS_CHANNEL_ID"))

if not all(required_vars):
    raise ValueError("Missing required environment variables. Check .env file.")
