-- Championship Raffle tickets migration
-- Run this once by hand in the Supabase SQL editor.

-- Persistent running total (like total_points) - doesn't reset until a
-- full season relaunch.
ALTER TABLE users ADD COLUMN IF NOT EXISTS raffle_tickets INTEGER DEFAULT 0;

-- Append-only ledger (like points_history) - one row per ticket award, so
-- automatic awards (Win the Week, Weekly Top 10, etc.) can check "have I
-- already awarded this exact reason to this user" and stay idempotent
-- across repeated task runs. See RaffleTicketModel.add_tickets_once.
CREATE TABLE IF NOT EXISTS raffle_ticket_history (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    season TEXT NOT NULL DEFAULT 'Q2',
    tickets_change INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_raffle_ticket_history_user ON raffle_ticket_history(user_id);
