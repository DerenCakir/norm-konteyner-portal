-- 2026-05-05 Kullanıcı özel geç giriş izinleri
-- Supabase SQL Editor'da bir kez çalıştırılmalıdır.

CREATE TABLE IF NOT EXISTS late_user_window_overrides (
    id SERIAL PRIMARY KEY,
    week_iso VARCHAR(8) NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id),
    department_id INTEGER REFERENCES departments(id),
    opened_by INTEGER NOT NULL REFERENCES users(id),
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closes_at TIMESTAMPTZ NOT NULL,
    reason VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_late_user_overrides_lookup
    ON late_user_window_overrides(week_iso, user_id, department_id, closes_at);

CREATE INDEX IF NOT EXISTS idx_late_user_overrides_closes
    ON late_user_window_overrides(closes_at);
