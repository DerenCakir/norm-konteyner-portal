-- Migration: site_container_ratio
-- ---------------------------------------------------------------------------
-- Üretim yeri × dolu konteyner başına tonaj oranı (t/konteyner).
-- Sayım formunda 'Dolu' alanı kapalı olan siteler için tonaj/oran ile
-- dolu konteyner adedi hesaplanır (yukarı yuvarlanır).

CREATE TABLE IF NOT EXISTS site_container_ratio (
    site_id                 INTEGER PRIMARY KEY REFERENCES production_sites(id),
    ratio_ton_per_container NUMERIC(10, 4) NOT NULL
        CHECK (ratio_ton_per_container > 0),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by              INTEGER REFERENCES users(id)
);
