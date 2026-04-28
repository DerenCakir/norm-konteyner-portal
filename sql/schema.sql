-- =============================================
-- NORM HOLDİNG KONTEYNER TAKİP PORTAL
-- Veritabanı Şeması v1.1
-- =============================================
-- Bu dosya REFERANS amaçlıdır. Şema Supabase üzerinde
-- zaten çalıştırılmıştır. Uygulama kodunu değiştirirken
-- veri modelini buradan kontrol et.
-- =============================================

-- 1. ÜRETİM YERLERİ
CREATE TABLE production_sites (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. BÖLÜMLER
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    production_site_id INTEGER NOT NULL REFERENCES production_sites(id),
    name VARCHAR(100) NOT NULL,
    weekly_tonnage_target NUMERIC(10, 2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(production_site_id, name)
);

-- 3. RENKLER
CREATE TABLE colors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    hex_code VARCHAR(7),
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. KULLANICILAR
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(150),
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    CONSTRAINT valid_role CHECK (role IN ('user', 'admin'))
);

-- 5. KULLANICI-BÖLÜM YETKİLENDİRME
CREATE TABLE user_departments (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, department_id)
);

-- 6. SAYIM KAYITLARI
CREATE TABLE count_submissions (
    id SERIAL PRIMARY KEY,
    department_id INTEGER NOT NULL REFERENCES departments(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    week_iso VARCHAR(8) NOT NULL,
    count_date DATE NOT NULL,
    count_time TIME,
    actual_tonnage NUMERIC(10, 2),
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(department_id, week_iso),
    CONSTRAINT valid_status CHECK (status IN ('draft', 'submitted', 'late_submitted'))
);

-- 7. RENK BAZLI SAYIM DETAYI
CREATE TABLE count_details (
    id SERIAL PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES count_submissions(id) ON DELETE CASCADE,
    color_id INTEGER NOT NULL REFERENCES colors(id),
    empty_count INTEGER DEFAULT 0,
    full_count INTEGER DEFAULT 0,
    kanban_count INTEGER DEFAULT 0,
    UNIQUE(submission_id, color_id),
    CONSTRAINT non_negative CHECK (
        empty_count >= 0 AND full_count >= 0 AND kanban_count >= 0
    ),
    CONSTRAINT kanban_le_full CHECK (kanban_count <= full_count)
);

-- 8. LATE WINDOW OVERRIDES
-- Admin manuel olarak hafta bazında geç giriş penceresi açar.
-- Kayıt yoksa o hafta için geç giriş kapalı (varsayılan).
CREATE TABLE late_window_overrides (
    week_iso VARCHAR(8) PRIMARY KEY,
    opened_by INTEGER NOT NULL REFERENCES users(id),
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closes_at TIMESTAMPTZ NOT NULL,
    reason VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_late_overrides_closes ON late_window_overrides(closes_at);

-- 9. AUDIT LOG
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50),
    entity_id INTEGER,
    old_value JSONB,
    new_value JSONB,
    ip_address VARCHAR(45),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- INDEXLER
CREATE INDEX idx_submissions_week ON count_submissions(week_iso);
CREATE INDEX idx_submissions_dept_week ON count_submissions(department_id, week_iso);
CREATE INDEX idx_submissions_status ON count_submissions(status);
CREATE INDEX idx_details_submission ON count_details(submission_id);
CREATE INDEX idx_details_color ON count_details(color_id);
CREATE INDEX idx_user_depts_user ON user_departments(user_id);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_departments_site ON departments(production_site_id);
CREATE INDEX idx_departments_active ON departments(is_active);
CREATE INDEX idx_colors_active ON colors(is_active);

-- SEED DATA: ÜRETİM YERLERİ (11 adet)
INSERT INTO production_sites (code, name) VALUES
('2003', 'Norm Holding'),
('2101', 'Norm Cıvata Salihli'),
('2201', 'Norm Somun İzmir'),
('2202', 'Norm Somun Salihli'),
('2301', 'MS Vida'),
('2401', 'Sıcak Dövme'),
('2501', 'Norm Cıvata İzmir'),
('3001', 'Uysal İzmir'),
('3003', 'Uysal Salihli'),
('3201', 'Sac Şekillendirme'),
('3501', 'Nedu');

-- SEED DATA: BÖLÜMLER (42 adet)
INSERT INTO departments (production_site_id, name) VALUES
((SELECT id FROM production_sites WHERE code='2501'), 'İzmir Cıvata'),
((SELECT id FROM production_sites WHERE code='2101'), 'Salihli Cıvata'),
((SELECT id FROM production_sites WHERE code='2201'), 'İzmir Somun'),
((SELECT id FROM production_sites WHERE code='2202'), 'Salihli Somun'),
((SELECT id FROM production_sites WHERE code='2301'), 'Ms Vida'),
((SELECT id FROM production_sites WHERE code='3001'), 'İzmir Uysal 1'),
((SELECT id FROM production_sites WHERE code='3001'), 'İzmir Uysal 2'),
((SELECT id FROM production_sites WHERE code='3001'), 'İzmir Uysal Paketleme'),
((SELECT id FROM production_sites WHERE code='3003'), 'Salihli Uysal 1'),
((SELECT id FROM production_sites WHERE code='3003'), 'Salihli Uysal 2'),
((SELECT id FROM production_sites WHERE code='3003'), 'Salihli Uysal 3'),
((SELECT id FROM production_sites WHERE code='3501'), 'Nedu'),
((SELECT id FROM production_sites WHERE code='2401'), 'Sıcak Dövme'),
((SELECT id FROM production_sites WHERE code='3201'), 'Saç Şekillendirme'),
((SELECT id FROM production_sites WHERE code='2003'), 'İzmir Lm'),
((SELECT id FROM production_sites WHERE code='2003'), 'Salihli Lm'),
((SELECT id FROM production_sites WHERE code='2003'), 'Yol'),
((SELECT id FROM production_sites WHERE code='2101'), 'HAKSAN'),
((SELECT id FROM production_sites WHERE code='2201'), 'CAN CNC'),
((SELECT id FROM production_sites WHERE code='2201'), 'İZKALIP'),
((SELECT id FROM production_sites WHERE code='2201'), 'ÖZ BİRLİK'),
((SELECT id FROM production_sites WHERE code='2201'), 'SANPA'),
((SELECT id FROM production_sites WHERE code='2201'), 'TRİO KOMPOZİT'),
((SELECT id FROM production_sites WHERE code='2202'), 'CAN CNC'),
((SELECT id FROM production_sites WHERE code='2202'), 'İZKALIP'),
((SELECT id FROM production_sites WHERE code='2202'), 'İZMİR METAL'),
((SELECT id FROM production_sites WHERE code='2202'), 'PEK MÜHENDİSLİK'),
((SELECT id FROM production_sites WHERE code='2202'), 'TRİO KOMPOZİT'),
((SELECT id FROM production_sites WHERE code='2301'), 'ÇİNKOSAN'),
((SELECT id FROM production_sites WHERE code='2501'), 'ALPHA METALURJİ'),
((SELECT id FROM production_sites WHERE code='2501'), 'ATASAN'),
((SELECT id FROM production_sites WHERE code='2501'), 'CAN CNC'),
((SELECT id FROM production_sites WHERE code='2501'), 'DÖKSAN'),
((SELECT id FROM production_sites WHERE code='2501'), 'İZMİSTAS'),
((SELECT id FROM production_sites WHERE code='2501'), 'METSAN'),
((SELECT id FROM production_sites WHERE code='2501'), 'OMEGA'),
((SELECT id FROM production_sites WHERE code='2501'), 'ÖZBİRLİK'),
((SELECT id FROM production_sites WHERE code='2501'), 'TRİO KOMPOZİT'),
((SELECT id FROM production_sites WHERE code='3501'), 'ÖZBİRLİK'),
((SELECT id FROM production_sites WHERE code='3501'), 'GÖKDEMİR'),
((SELECT id FROM production_sites WHERE code='3001'), 'EKAP'),
((SELECT id FROM production_sites WHERE code='3001'), 'POLİKİM');

-- SEED DATA: BAŞLANGIÇ RENKLERİ (6 adet)
INSERT INTO colors (name, hex_code, sort_order) VALUES
('Mavi', '#1E40AF', 1),
('Turuncu', '#EA580C', 2),
('Yeşil', '#16A34A', 3),
('Gri', '#6B7280', 4),
('MS Vida', '#92400E', 5),
('Sarı', '#EAB308', 6);
