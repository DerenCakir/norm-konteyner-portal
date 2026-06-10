-- 2026-06-02 Work In Progress (WIP) sayımı
--
-- Sayım girişine 'Boş' ile 'Dolu' arasında yeni bir kategori: WIP.
-- Yeni 'Toplam Konteyner' tanımı = Boş + WIP + Dolu + Hurda.
-- Mevcut kayıtlar default 0 ile geriye uyumlu kalır.
--
-- Supabase SQL Editor'da BİR KEZ çalıştırılmalıdır.

ALTER TABLE count_details
ADD COLUMN IF NOT EXISTS wip_count INTEGER NOT NULL DEFAULT 0
    CHECK (wip_count >= 0);
