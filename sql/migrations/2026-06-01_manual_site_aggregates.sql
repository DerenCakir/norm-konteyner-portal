-- 2026-06-01 Manuel üretim yeri toplamları (geçmiş veri)
--
-- Sistem öncesi manuel sayılan haftalar için, üretim yeri başına
-- Boş / Dolu / Hurda toplamları. Bölüm + renk detayı yok; sadece
-- toplamlar. Grafiklerde tarihsel karşılaştırma amaçlı kullanılır.
--
-- Supabase SQL Editor'da BİR KEZ çalıştırılmalıdır.

CREATE TABLE IF NOT EXISTS manual_site_aggregates (
    id            SERIAL PRIMARY KEY,
    week_iso      VARCHAR(8) NOT NULL,
    site_id       INTEGER NOT NULL REFERENCES production_sites(id),
    empty_total   INTEGER NOT NULL DEFAULT 0,
    full_total    INTEGER NOT NULL DEFAULT 0,
    scrap_total   INTEGER,
    tonnage_total NUMERIC(10, 2),
    created_by    INTEGER NOT NULL REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_manual_site_week UNIQUE (week_iso, site_id)
);

CREATE INDEX IF NOT EXISTS idx_manual_site_aggs_week
    ON manual_site_aggregates(week_iso);
