-- Monthly Victory migration
-- Run this once by hand in the Supabase SQL editor.

-- One row per user per season month that was actually won (won
-- MONTHLY_VICTORY_WEEKS_RATIO of that month's weeks - see
-- config.constants.MONTHLY_VICTORY_WEEK_GROUPS). Absence of a row for a
-- given month = did not win that month. Written once, when the month's
-- last constituent week finalizes - see MonthlyVictoryModel.finalize_month.
CREATE TABLE IF NOT EXISTS monthly_victories (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    season TEXT NOT NULL DEFAULT 'Q2',
    month_number INTEGER NOT NULL,
    weeks_won INTEGER NOT NULL,
    weeks_required INTEGER NOT NULL,
    awarded_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, season, month_number)
);
CREATE INDEX IF NOT EXISTS idx_monthly_victories_user ON monthly_victories(user_id, season);
