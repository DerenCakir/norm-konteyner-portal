-- =============================================
-- Migration 002: late_window_overrides
-- =============================================
-- Geç giriş penceresi artık otomatik açılmıyor (Cuma 12:00 sonrası).
-- Admin, hafta bazında manuel olarak açar; kayıt yoksa pencere kapalı.
--
-- Bu dosyayı Supabase SQL Editor'da çalıştır.
-- Idempotent: birden fazla çalıştırılırsa hata vermez.
-- =============================================

CREATE TABLE IF NOT EXISTS late_window_overrides (
    week_iso VARCHAR(8) PRIMARY KEY,
    opened_by INTEGER NOT NULL REFERENCES users(id),
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closes_at TIMESTAMPTZ NOT NULL,
    reason VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_late_overrides_closes
    ON late_window_overrides(closes_at);
