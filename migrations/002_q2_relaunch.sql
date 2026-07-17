-- Q2 Relaunch migration
-- Run this once by hand in the Supabase SQL editor.
-- Archives Q1 standings, resets live standings for Q2, and adds the tables/columns
-- needed for DB-backed config (channels, value-drop emoji points, scaler threshold,
-- masters bonus role) instead of hardcoded env vars / constants.

-- 1. Generic key/value config store (channel IDs, value-drop emoji map, scaler threshold)
CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_by BIGINT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Seed the value-drop emoji map with today's point values so behavior is unchanged
-- until an admin edits it via /q2setvaluedropemoji.
INSERT INTO bot_config (key, value)
VALUES ('value_drop_emojis', '{"🔥": 3, "💎": 3, "💯": 5}')
ON CONFLICT (key) DO NOTHING;

-- Seed the scaler point threshold (same as the Elite tier floor).
INSERT INTO bot_config (key, value)
VALUES ('scaler_threshold', '300')
ON CONFLICT (key) DO NOTHING;

-- 2. Frozen per-season snapshot table (read-only history once a season ends)
CREATE TABLE IF NOT EXISTS season_archive (
    user_id BIGINT NOT NULL,
    season TEXT NOT NULL,
    username TEXT,
    total_points INTEGER,
    tier TEXT,
    is_scaler BOOLEAN,
    referral_count INTEGER,
    archived_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, season)
);

-- Snapshot current (Q1) standings before resetting the live table.
INSERT INTO season_archive (user_id, season, username, total_points, tier, is_scaler, referral_count)
SELECT user_id, 'Q1', username, total_points, tier, is_scaler, referral_count
FROM users
ON CONFLICT (user_id, season) DO NOTHING;

-- 3. Season-tag the append-only/detail tables so future seasons never mix data.
ALTER TABLE points_history ADD COLUMN IF NOT EXISTS season TEXT NOT NULL DEFAULT 'Q2';
ALTER TABLE value_posts    ADD COLUMN IF NOT EXISTS season TEXT NOT NULL DEFAULT 'Q2';
ALTER TABLE daily_todos    ADD COLUMN IF NOT EXISTS season TEXT NOT NULL DEFAULT 'Q2';
ALTER TABLE calls_posts    ADD COLUMN IF NOT EXISTS season TEXT NOT NULL DEFAULT 'Q2';
ALTER TABLE submissions    ADD COLUMN IF NOT EXISTS season TEXT NOT NULL DEFAULT 'Q2';

-- Backfill existing rows (all pre-migration data belongs to Q1).
UPDATE points_history SET season = 'Q1' WHERE season = 'Q2';
UPDATE value_posts    SET season = 'Q1' WHERE season = 'Q2';
UPDATE daily_todos    SET season = 'Q1' WHERE season = 'Q2';
UPDATE calls_posts    SET season = 'Q1' WHERE season = 'Q2';
UPDATE submissions    SET season = 'Q1' WHERE season = 'Q2';

CREATE INDEX IF NOT EXISTS idx_points_history_season ON points_history(season);
CREATE INDEX IF NOT EXISTS idx_value_posts_season ON value_posts(season);
CREATE INDEX IF NOT EXISTS idx_daily_todos_season ON daily_todos(season);
CREATE INDEX IF NOT EXISTS idx_calls_posts_season ON calls_posts(season);

-- 4. value_posts: replace fixed fire/gem/hundred columns with a generic reaction map,
--    so the tracked emoji set is no longer hardcoded to 3 fixed emojis.
-- Guarded so this whole file is safe to re-run: fire_count/etc. only exist
-- before this step has run once, so re-running is a clean no-op afterward.
ALTER TABLE value_posts ADD COLUMN IF NOT EXISTS reaction_counts JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'value_posts' AND column_name = 'fire_count'
    ) THEN
        UPDATE value_posts
        SET reaction_counts = jsonb_build_object('🔥', fire_count, '💎', gem_count, '💯', hundred_count)
        WHERE reaction_counts = '{}'::jsonb;

        ALTER TABLE value_posts DROP COLUMN fire_count;
        ALTER TABLE value_posts DROP COLUMN gem_count;
        ALTER TABLE value_posts DROP COLUMN hundred_count;
    END IF;
END $$;

-- 5. users: add the persistent (non-reset) Masters bonus flag, then reset live
--    standings for Q2. is_master and username are intentionally left untouched.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_master BOOLEAN DEFAULT FALSE;

UPDATE users
SET total_points = 0,
    tier = 'OBSERVER',
    is_scaler = FALSE,
    referral_count = 0,
    updated_at = NOW();
