-- Migration: rondela_count sayım alanı
-- ---------------------------------------------------------------------------
-- Yeni renk-bazlı alan: Rondela. Sayım formunda seçili üretim yerinde
-- gösterilir; toplam konteyner sayısı hesaplarına Boş/Proseste/Dolu/Hurda
-- ile birlikte eklenir.

-- 1) count_details: rondela_count kolonu (default 0, non-negative)
ALTER TABLE count_details
    ADD COLUMN IF NOT EXISTS rondela_count INTEGER NOT NULL DEFAULT 0;

-- non_negative constraint'i genisletiyoruz (varsa drop + yeniden ekle)
ALTER TABLE count_details DROP CONSTRAINT IF EXISTS non_negative;
ALTER TABLE count_details ADD CONSTRAINT non_negative CHECK (
    empty_count >= 0
    AND full_count >= 0
    AND kanban_count >= 0
    AND scrap_count >= 0
    AND wip_count >= 0
    AND rondela_count >= 0
);

-- 2) site_count_config: show_rondela boolean (default true, safe fallback)
ALTER TABLE site_count_config
    ADD COLUMN IF NOT EXISTS show_rondela BOOLEAN NOT NULL DEFAULT TRUE;

-- Mevcut config satirlarinda default false yaparsak Ronda'yi hiçbir
-- site kullanmiyor sayilir; kullanici admin panelinden istedigi
-- siteye acar. Yeni siteler icin varsayilan TRUE (mevcut davranis
-- ile tutarli — kayit yoksa hepsi acik).
UPDATE site_count_config SET show_rondela = FALSE;
