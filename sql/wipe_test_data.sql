-- =============================================================================
-- TEST VERİSİ SIFIRLAMA — Norm Konteyner Portalı
-- =============================================================================
-- Bu betik, test sırasında üretilen sayım kayıtlarını ve audit log'u
-- temizler. Master data (kullanıcılar, bölümler, renkler, üretim yerleri)
-- KORUNUR.
--
-- KULLANIM (Supabase SQL Editor):
--   1) Bu dosyanın TAMAMINI kopyala
--   2) Supabase Dashboard → SQL Editor → "New query"
--   3) Yapıştır
--   4) AŞAĞIDAKİ "BEGIN;" satırının başındaki "--" işaretini kaldır
--      (yani yorum satırı olmaktan çıkar)
--   5) "Run" butonuna bas
--   6) Hata yoksa COMMIT için "COMMIT;" yaz ve tekrar Run
--      (geri almak istersen "ROLLBACK;" yaz)
-- =============================================================================
-- Yanlışlıkla çalışmasın diye BEGIN/COMMIT yorumda. Onaylamak için kaldır.

-- BEGIN;

-- 1. Sayım detayları (önce çocuk tablo, FK için)
TRUNCATE TABLE count_details CASCADE;

-- 2. Sayım kayıtları
TRUNCATE TABLE count_submissions CASCADE;

-- 3. Geç giriş pencereleri (admin tarafından açılan override'lar)
DELETE FROM late_user_window_overrides;
DELETE FROM late_window_overrides;

-- 4. Audit log — sadece transactional aksiyonları sil, kullanıcı yönetimi
--    kayıtlarını koru. user_create / department_create gibi master-data
--    aksiyonları "geçerli kalsın" diye saklı tutuluyor.
DELETE FROM audit_log
WHERE action IN (
    'count_submit',
    'count_update',
    'count_delete',
    'count_admin_override',
    'count_bulk_delete',
    'late_window_open',
    'late_window_close',
    'late_user_window_open',
    'late_user_window_close',
    'login_success',
    'login_failed',
    'logout'
);

-- 5. Doğrulama sorguları — hepsi 0 dönmeli (master data hariç)
SELECT 'count_submissions' AS tablo, COUNT(*) AS kayit FROM count_submissions
UNION ALL SELECT 'count_details',          COUNT(*) FROM count_details
UNION ALL SELECT 'late_window_overrides',  COUNT(*) FROM late_window_overrides
UNION ALL SELECT 'late_user_window_overrides', COUNT(*) FROM late_user_window_overrides
UNION ALL SELECT 'audit_log (kalan)',      COUNT(*) FROM audit_log
UNION ALL SELECT 'users (DOKUNULMADI)',    COUNT(*) FROM users
UNION ALL SELECT 'departments (DOKUNULMADI)', COUNT(*) FROM departments
UNION ALL SELECT 'colors (DOKUNULMADI)',   COUNT(*) FROM colors
UNION ALL SELECT 'production_sites (DOKUNULMADI)', COUNT(*) FROM production_sites;

-- COMMIT;
-- ROLLBACK;
