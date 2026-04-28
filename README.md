# Norm Konteyner Takip Portalı

Norm Holding'in 11 üretim yerinde, 42 bölümde kullanılan demir konteynerlerin haftalık sayımını toplayan ve analiz eden Streamlit tabanlı web portal.

## Stack

- Streamlit (multi-page)
- PostgreSQL (Supabase)
- SQLAlchemy 2.0+
- bcrypt (custom auth)
- Python 3.11+

## Kurulum

```bash
# 1. Sanal ortam
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. Bağımlılıklar
pip install -r requirements.txt

# 3. Ortam değişkenleri
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
# .env içindeki DATABASE_URL ve SECRET_KEY değerlerini doldur

# 4. Çalıştır
streamlit run app.py
```

## Veritabanı

Şema Supabase üzerinde oluşturulmuştur. Referans için `sql/schema.sql` projede saklanır.

Bağlantı için Supabase **Transaction Pooler** (port 6543, IPv4) kullanılır — Railway IPv6 desteklemediği için doğrudan bağlantı (5432) çalışmaz.

## Klasör Yapısı

```
app.py              # Login + yönlendirme
pages/              # Streamlit sayfaları
db/                 # SQLAlchemy modelleri ve sorgular
utils/              # Auth, hafta hesabı, izinler, audit
config/             # pydantic-settings ile ayarlar
sql/                # Şema referansı
```

## Roller

- **user** — yetkili olduğu bölümlerin haftalık sayımını girer
- **admin** — kullanıcı/bölüm/renk yönetimi, sayım override

Kayıt sistemi yoktur; kullanıcıları admin oluşturur.

## Haftalık Döngü

| Pencere (Europe/Istanbul) | Durum |
|---|---|
| Pazartesi 00:00 → Cuma 12:00 | Form açık |
| Cuma 12:00 → Cumartesi 00:00 | Geç giriş (uyarılı) |
| Cumartesi 00:00 sonrası | Kilitli (admin override) |

## Geliştirme Notları

Detaylı mimari kararlar ve kurallar için `CLAUDE.md` dosyasına bakın.
