-- 2026-06-01 Sayım kapatma (bayram/tatil haftaları)
--
-- Admin bir haftayı "sayım beklenmez" olarak işaretler. O hafta için
-- form kullanıcıya kapanır, mevcut kayıtlar (varsa) silinir, analiz
-- ve grafiklerde o hafta tamamen yok sayılır.
--
-- Supabase SQL Editor'da BİR KEZ çalıştırılmalıdır.

CREATE TABLE IF NOT EXISTS closed_weeks (
    week_iso   VARCHAR(8) PRIMARY KEY,
    reason     VARCHAR(500),
    closed_by  INTEGER NOT NULL REFERENCES users(id),
    closed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_closed_weeks_closed_at
    ON closed_weeks(closed_at);
