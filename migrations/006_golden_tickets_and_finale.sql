-- Golden Ticket events + Championship finale migration
-- Run this once by hand in the Supabase SQL editor.

-- Streak tracking (doc: "Weekly Streak Continues", "Everyone currently on
-- a 14-day streak receives 50 bonus tickets"). Updated once per user per
-- day, from DailyActivityModel.award_daily_point - the same "did they
-- actually engage today" signal already used to award the daily point.
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_streak INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_streak_date DATE;

-- Grand Championship Leaderboard badges (persistent, same pattern as
-- is_official_finisher) - Top 25 = Founder, Rank 1 = Grand Champion.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_founder BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_grand_champion BOOLEAN DEFAULT FALSE;

-- No new tables needed for Golden Ticket event state (flagged weeks,
-- armed "next 25" counter) - those live in the existing generic bot_config
-- key/value store (see BotConfigModel.get_golden_ticket_weeks /
-- get_golden_ticket_next_n_remaining).
