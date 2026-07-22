-- Migration: site_tonnage_targets
-- ---------------------------------------------------------------------------
-- Üretim yeri bazlı haftalık tonaj hedefleri. Hedefler dönemsel
-- güncelleniyor (3 ayda bir tipik) — versionlu tutmak için
-- effective_from / effective_to alanları var.
--
-- İş kuralı:
--   • Yeni bir hedef eklendiğinde, o siteye ait açık uçlu (effective_to
--     NULL) önceki kayıt otomatik kapatılır: effective_to = new.effective_from - 1
--     (bu iş katmanda yapılır, DB trigger yok — audit için niyet açık kalsın).
--   • Bir haftanın "geçerli hedefi" = o haftanın Pazartesi'sini içeren
--     [effective_from, coalesce(effective_to, 'infinity')] aralıklı kayıt.
--   • Aynı (site, effective_from) unique — aynı gün için iki hedef olamaz.
--
-- Bu tablo, mevcut departments.weekly_tonnage_target alanını REPLACE ETMEZ;
-- o alan bölüm bazlı hedefler için kalıyor (04_analiz sayfası kullanıyor).

CREATE TABLE IF NOT EXISTS site_tonnage_targets (
    id                  BIGSERIAL PRIMARY KEY,
    production_site_id  INTEGER NOT NULL REFERENCES production_sites(id),
    weekly_target_ton   NUMERIC(10, 2) NOT NULL CHECK (weekly_target_ton >= 0),
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    created_by          INTEGER NOT NULL REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT site_tonnage_targets_site_from_key
        UNIQUE (production_site_id, effective_from),
    CONSTRAINT site_tonnage_targets_range_check
        CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE INDEX IF NOT EXISTS idx_site_tonnage_targets_site
    ON site_tonnage_targets(production_site_id);
CREATE INDEX IF NOT EXISTS idx_site_tonnage_targets_active
    ON site_tonnage_targets(production_site_id, effective_from DESC)
    WHERE effective_to IS NULL;
