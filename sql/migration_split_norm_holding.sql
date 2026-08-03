-- Migration: Norm Holding → Yol + Lojistik Merkezleri
-- ---------------------------------------------------------------------------
-- Norm Holding (kod 2003) çatısı altındaki 3 bölüm iki yeni üretim yerine
-- taşınır:
--   • Bölüm "Yol"                        → Yeni site "Yol" (kod 2004)
--   • Bölüm "İzmir Lm" + "Salihli Lm"    → Yeni site "Lojistik Merkezleri"
--                                          (kod 2005)
-- Norm Holding site is_active=FALSE olur (silinmez -- geçmiş
-- count_submissions'ın FK bütünlüğü için gerekli).
--
-- Geçmiş sayım verileri (count_submissions.department_id sabit) otomatik
-- olarak yeni sitelere yansır çünkü join productionsite'yi departments'
-- güncellenen production_site_id üzerinden çeker.
--
-- Bu migration IDEMPOTENT — ON CONFLICT + WHERE koşullarıyla ikinci kez
-- çalıştırıldığında hata vermez.

BEGIN;

-- 1) Yeni siteleri ekle (yoksa)
INSERT INTO production_sites (code, name, is_active) VALUES
    ('2004', 'Yol',                  TRUE),
    ('2005', 'Lojistik Merkezleri',  TRUE)
ON CONFLICT (code) DO NOTHING;

-- 2) Bölümleri yeni sitelere taşı
--    (production_site_id güncellenir; departments.id ve name aynı kalır,
--    dolayısıyla count_submissions ve user_departments etkilenmez)
UPDATE departments
SET production_site_id = (SELECT id FROM production_sites WHERE code = '2004')
WHERE production_site_id = (SELECT id FROM production_sites WHERE code = '2003')
  AND name = 'Yol';

UPDATE departments
SET production_site_id = (SELECT id FROM production_sites WHERE code = '2005')
WHERE production_site_id = (SELECT id FROM production_sites WHERE code = '2003')
  AND name IN ('İzmir Lm', 'Salihli Lm');

-- 3) Norm Holding site'yi pasifleştir (analiz sayfalarında görünmez)
UPDATE production_sites SET is_active = FALSE WHERE code = '2003';

-- 4) Yeni siteler için site_count_config: Norm Holding'in eski
--    ayarını kopyala (Boş+Dolu+Tonaj açık). Admin isterse portaldan
--    değiştirir.
INSERT INTO site_count_config (
    site_id, show_empty, show_wip, show_full,
    show_kanban, show_scrap, show_rondela, show_tonnage
)
SELECT ns.id,
       COALESCE(cfg.show_empty, TRUE),
       COALESCE(cfg.show_wip, FALSE),
       COALESCE(cfg.show_full, TRUE),
       COALESCE(cfg.show_kanban, FALSE),
       COALESCE(cfg.show_scrap, FALSE),
       COALESCE(cfg.show_rondela, FALSE),
       COALESCE(cfg.show_tonnage, TRUE)
FROM production_sites ns
LEFT JOIN site_count_config cfg
       ON cfg.site_id = (SELECT id FROM production_sites WHERE code = '2003')
WHERE ns.code IN ('2004', '2005')
ON CONFLICT (site_id) DO NOTHING;

COMMIT;
