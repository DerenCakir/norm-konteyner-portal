-- Migration: site_count_config
-- ---------------------------------------------------------------------------
-- Üretim yerine göre sayım giriş ekranında hangi alanların gösterileceğini
-- kontrol eder. Kayıt yoksa varsayılan olarak HEPSİ True kabul edilir
-- (mevcut davranışa geri düşer, güvenli fallback).
--
-- İş kuralı (kullanıcı isteği):
--   • 10 üretim yeri: sadece Boş + Proseste
--     (Norm Cıvata İzmir/Salihli, Norm Somun İzmir/Salihli,
--      Uysal İzmir/Salihli, MS Vida, Nedu, Sac Şekillendirme, Sıcak Dövme)
--   • Norm Holding: sadece Boş + Dolu + Tonaj

CREATE TABLE IF NOT EXISTS site_count_config (
    site_id       INTEGER PRIMARY KEY REFERENCES production_sites(id),
    show_empty    BOOLEAN NOT NULL DEFAULT TRUE,
    show_wip      BOOLEAN NOT NULL DEFAULT TRUE,
    show_full     BOOLEAN NOT NULL DEFAULT TRUE,
    show_kanban   BOOLEAN NOT NULL DEFAULT TRUE,
    show_scrap    BOOLEAN NOT NULL DEFAULT TRUE,
    show_tonnage  BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by    INTEGER REFERENCES users(id)
);

-- 10 site: sadece Boş + Proseste
INSERT INTO site_count_config
    (site_id, show_empty, show_wip, show_full, show_kanban, show_scrap, show_tonnage)
SELECT id, TRUE, TRUE, FALSE, FALSE, FALSE, FALSE
FROM production_sites
WHERE code IN (
    '2101', '2201', '2202', '2301', '2401', '2501',
    '3001', '3003', '3201', '3501'
)
ON CONFLICT (site_id) DO NOTHING;

-- Norm Holding (2003): Boş + Dolu + Tonaj
INSERT INTO site_count_config
    (site_id, show_empty, show_wip, show_full, show_kanban, show_scrap, show_tonnage)
SELECT id, TRUE, FALSE, TRUE, FALSE, FALSE, TRUE
FROM production_sites
WHERE code = '2003'
ON CONFLICT (site_id) DO NOTHING;
