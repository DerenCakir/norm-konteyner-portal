-- Add 'scrap' (hurdaya ayrılacak) count to count_details.
--
-- Hurda, boş/dolu/kanban'dan bağımsız bir sayımdır. Artık kullanılmayacak
-- (ayağı kırık vb.) konteynerleri ifade eder. Boş ve dolu sayımlarına
-- DAHIL EDILMEZ (kullanıcı bilgilendirmesi sayım formunda yapılıyor).

ALTER TABLE count_details
    ADD COLUMN IF NOT EXISTS scrap_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE count_details
    DROP CONSTRAINT IF EXISTS non_negative;

ALTER TABLE count_details
    ADD CONSTRAINT non_negative CHECK (
        empty_count >= 0
        AND full_count >= 0
        AND kanban_count >= 0
        AND scrap_count >= 0
    );
