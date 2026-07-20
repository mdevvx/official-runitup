-- Weekly Victory + Official Finisher migration
-- Run this once by hand in the Supabase SQL editor.

-- 1. Tags each points_history row so Weekly Victory can sum only the
--    auto-tracked "consistency" sources (daily activity/todo/calls/value
--    posts) and exclude admin-awarded "performance" points (wins,
--    referrals, bonuses, manual corrections) - those already drive the
--    season/weekly leaderboard separately. Existing rows default to
--    'consistency'; a handful of old win/referral rows may be
--    misclassified retroactively, but every award is explicitly tagged at
--    the call site going forward (see UserModel.update_points).
ALTER TABLE points_history ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'consistency';

-- 2. One row per user per season week that was actually won (points earned
--    met/exceeded the Weekly Victory threshold at the time the week
--    closed). Absence of a row for a given week = did not win that week.
--    Written once, when the week closes - see WeeklyVictoryModel.finalize_week.
CREATE TABLE IF NOT EXISTS weekly_victories (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    season TEXT NOT NULL DEFAULT 'Q2',
    week_number INTEGER NOT NULL,
    points_earned INTEGER NOT NULL,
    threshold INTEGER NOT NULL,
    awarded_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, season, week_number)
);
CREATE INDEX IF NOT EXISTS idx_weekly_victories_user ON weekly_victories(user_id, season);

-- 3. Persistent Official Finisher flag (same pattern as is_master/is_scaler) -
--    doesn't reset until a full season relaunch.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_official_finisher BOOLEAN DEFAULT FALSE;
