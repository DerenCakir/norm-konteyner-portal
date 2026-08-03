-- Migration: Norm Holding manual_site_aggregates -> Lojistik Merkezleri
-- ---------------------------------------------------------------------------
-- Norm Holding site is_active=FALSE oldu ama manual_site_aggregates
-- tablosundaki eski Norm Holding kayıtları hâlâ site_id=Norm Holding'e
-- referans veriyor — Excel'de "Norm Holding" boş satır olarak çıkıyor.
-- Bu satırları Lojistik Merkezleri'ne taşıyıp Norm Holding'i tamamen
-- boşaltıyoruz.
--
-- Aynı (week_iso, Lojistik Merkezleri) çakışması varsa toplayarak
-- birleştiriyor (ON CONFLICT).

BEGIN;

-- 1) Norm Holding satırlarını Lojistik Merkezleri'ne kopyala (merge)
INSERT INTO manual_site_aggregates
    (week_iso, site_id, empty_total, full_total, scrap_total, tonnage_total, created_by)
SELECT
    week_iso,
    (SELECT id FROM production_sites WHERE code = '2005'),
    empty_total,
    full_total,
    scrap_total,
    tonnage_total,
    created_by
FROM manual_site_aggregates
WHERE site_id = (SELECT id FROM production_sites WHERE code = '2003')
ON CONFLICT (week_iso, site_id) DO UPDATE SET
    empty_total   = manual_site_aggregates.empty_total   + EXCLUDED.empty_total,
    full_total    = manual_site_aggregates.full_total    + EXCLUDED.full_total,
    scrap_total   = COALESCE(manual_site_aggregates.scrap_total, 0)
                  + COALESCE(EXCLUDED.scrap_total, 0),
    tonnage_total = COALESCE(manual_site_aggregates.tonnage_total, 0)
                  + COALESCE(EXCLUDED.tonnage_total, 0),
    updated_at    = NOW();

-- 2) Norm Holding eski satırlarını sil
DELETE FROM manual_site_aggregates
WHERE site_id = (SELECT id FROM production_sites WHERE code = '2003');

COMMIT;
