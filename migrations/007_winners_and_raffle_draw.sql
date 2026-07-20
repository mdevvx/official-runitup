-- Winners visibility + Championship Raffle draw migration
-- Run this once by hand in the Supabase SQL editor.

-- Records the actual Championship Raffle Prize Pool draw (Grand Prize,
-- Two/Three/Five/Ten Winners tiers) - a weighted, no-repeat draw across the
-- full ticket pool. One row per (user, tier); a season only ever gets
-- drawn once - see RaffleDrawModel.has_been_drawn / run_draw.
CREATE TABLE IF NOT EXISTS raffle_draw_winners (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    season TEXT NOT NULL DEFAULT 'Q2',
    tier TEXT NOT NULL,
    drawn_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, season, tier)
);
CREATE INDEX IF NOT EXISTS idx_raffle_draw_winners_season ON raffle_draw_winners(season);
