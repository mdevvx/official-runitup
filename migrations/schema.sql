-- Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL,
    total_points INTEGER DEFAULT 0,
    tier TEXT DEFAULT 'OBSERVER',
    is_scaler BOOLEAN DEFAULT FALSE,
    referral_count INTEGER DEFAULT 0,
    last_activity_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Daily Activity Table
CREATE TABLE IF NOT EXISTS daily_activity (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    activity_date DATE NOT NULL,
    message_count INTEGER DEFAULT 0,
    points_awarded INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, activity_date)
);

-- Value Posts Table
CREATE TABLE IF NOT EXISTS value_posts (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    message_id BIGINT UNIQUE NOT NULL,
    channel_id BIGINT NOT NULL,
    post_date DATE NOT NULL,
    fire_count INTEGER DEFAULT 0,
    gem_count INTEGER DEFAULT 0,
    hundred_count INTEGER DEFAULT 0,
    is_pinned BOOLEAN DEFAULT FALSE,
    total_points INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Submissions Table
CREATE TABLE IF NOT EXISTS submissions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    submission_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    description TEXT,
    proof_url TEXT,
    amount DECIMAL(10, 2),
    referral_type TEXT,
    points_awarded INTEGER DEFAULT 0,
    reviewed_by BIGINT,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Points History Table
CREATE TABLE IF NOT EXISTS points_history (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    points_change INTEGER NOT NULL,
    reason TEXT NOT NULL,
    reference_id INTEGER,
    reference_type TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_points ON users(total_points DESC);
CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);
CREATE INDEX IF NOT EXISTS idx_daily_activity_user_date ON daily_activity(user_id, activity_date);
CREATE INDEX IF NOT EXISTS idx_value_posts_user_date ON value_posts(user_id, post_date);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_user ON submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_points_history_user ON points_history(user_id);