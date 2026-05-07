-- Make count_submissions.count_time NOT NULL.
--
-- Tüm uygulama kodu bu alanı zaten dolduruyor (sayım girişi ve admin
-- override) ama tip tanımı `Optional[time]` idi. Bypass yollarına karşı
-- DB seviyesinde garanti altına alıyoruz.
--
-- Mevcut NULL kayıt varsa önce shu anki saatle dolduruyoruz; canlıda
-- NULL satır olmaması beklenir, ama defansif fallback iyi olur.

UPDATE count_submissions
SET count_time = COALESCE(count_time, NOW()::time)
WHERE count_time IS NULL;

ALTER TABLE count_submissions
    ALTER COLUMN count_time SET NOT NULL;
