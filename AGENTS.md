# AGENTS.md — Norm Holding Konteyner Takip Portalı

Bu dosya, projede çalışan AI ajanları için kalıcı bağlamdır. Her oturumda okunmalı.

## Proje Amacı

11 üretim yeri, 42 bölüm ve ~38.000 demir konteynerin haftalık sayımını toplayıp analiz eden web portal. Amaç: bölümler arası konteyner dağılımını görünür kılmak, üretim duruşlarını ve fazla konteyner kullanımını azaltmak.

## Teknik Stack

- **Frontend/Backend:** Streamlit (multi-page)
- **DB:** PostgreSQL (Supabase)
- **ORM:** SQLAlchemy 2.0+
- **Auth:** Custom (bcrypt + `st.session_state`) — `streamlit-authenticator` KULLANMIYORUZ
- **Config:** pydantic-settings (env variables)
- **Deploy:** Railway
- **Python:** 3.11+
- **Paket yönetimi:** `requirements.txt` (uv/poetry yok)

## Veri Modeli — Kritik Kurallar

- **Hiyerarşi:** Production Site → Department. Aynı bölüm adı farklı sitelerde tekrarlanabilir; unique key `(production_site_id, name)`.
- **Production Sites portaldan yönetilmez.** 11 site sabit; admin paneline "üretim yeri ekle" butonu KOYMA. Yeni site gerekirse SQL ile eklenir.
- **Colors tablosu:** Mavi, Turuncu, Yeşil, Gri, MS Vida, Sarı (seed). UI'da "Renk" olarak gösterilir. "MS Vida" diğer renklerle aynı kategoride — ayrı tip değil. Renkler asla silinmez, `is_active=false` yapılır.
- **Sayım kaydı:** `count_submissions` (bölüm × hafta) + `count_details` (her aktif renk için boş/dolu/kanban).
- **Kanban:** Dolu konteynerlerin alt kümesi. DB constraint: `kanban_count <= full_count`. Frontend de önceden uyarmalı.
- **Tonaj sapması:** `(actual_tonnage - weekly_tonnage_target) / weekly_tonnage_target`. Yüksek sapma = ekstra konteyner sinyali.

## Roller

- **user:** Yetkili olduğu bölümlerin sayımını girer; diğerlerini sadece görür. Analiz sayfalarına erişimi var.
- **admin:** User/bölüm/renk CRUD, tüm sayımları override edebilir, audit log görür.
- **Kayıt sistemi yok** — kullanıcıları admin oluşturur. Şifreler bcrypt hash.

## Haftalık Döngü (Europe/Istanbul)

ISO hafta formatı (`2026-W18`). Tüm zaman karşılaştırmaları TR timezone'da.

Sayım sadece **Cuma 09:00–12:00** arası yapılır. Bu pencerede form açıktır,
kullanıcı veriyi girip "Gönder"e basar. **Taslak özelliği YOKTUR** — pencere
zaten dar, doğrudan gönder mantığı.

Cuma 12:00 sonrasında form **otomatik kapanır**. Kullanıcı geç kalmışsa,
admin o hafta için **geç giriş penceresi** açabilir
(`late_window_overrides` tablosu). Açıldığında `closes_at`'e kadar
`status='late_submitted'` ile giriş kabul edilir.

Geç pencere de kapandıysa sadece admin müdahale edebilir.

| Durum | Koşul | Status |
|---|---|---|
| `open` | Cuma 09:00–12:00 + bu hafta | `submitted` |
| `late` | Admin `late_window_overrides`'ta açtıysa + `closes_at` geçmemişse | `late_submitted` |
| `locked` | Diğer her durum | sadece admin override |

DB'de `TIMESTAMPTZ` saklanır, `utils/week.py` TR'ye çevirip karşılaştırır.

Status değerleri: `submitted`, `late_submitted`. CHECK constraint'te `draft`
hâlâ var (geriye uyumluluk için), ama uygulama kodu üretmiyor.

### `utils/week.py` API

- `now_tr(now=None)` — TR-aware datetime; test için `now` parametresi
- `current_week_iso(now=None)` — bu haftanın `YYYY-Www` kodu
- `week_iso_from_date(d)` — verilen tarihin ISO hafta kodu
- `week_iso_to_dates(week_iso)` — `(monday, sunday)` tuple
- `is_submission_open(now=None)` — Cuma 09:00–12:00 mı
- `is_late_window_open(week_iso, session, now=None)` — DB-driven, admin override
- `get_submission_status(week_iso, session, now=None)` — `"open"|"late"|"locked"`
- `format_week_human(week_iso)` — `"21-27 Nisan 2026"` gibi

## Status Değerleri

`count_submissions.status`: `draft`, `submitted`, `late_submitted`. DB'de CHECK constraint var.

## Audit Log Kapsamı

Loglanır:
- Login (başarılı/başarısız)
- Logout
- Sayım **submit** (taslak DEĞİL)
- Admin override (başkasının sayımına müdahale)
- User/Department/Color CRUD (create, update, deactivate)

Loglanmaz: taslak kaydetme, sayfa görüntüleme.

## Sayfa Yapısı

```
app.py                       # Login + yönlendirme + session
pages/
  01_sayim_girisi.py         # Yetkili bölüm sayım formu
  02_anlik_durum.py          # Bölüm × renk matrisi (son hafta)
  03_haftalik_takip.py       # Bu hafta giren/girmeyen tablosu
  04_tonaj_sapma.py          # Hedef vs gerçekleşen (faz 2)
  05_trend.py                # Zamansal grafikler (faz 2)
  06_bolum_detay.py          # Tek bölüm zoom (faz 2)
  99_admin.py                # Sekmeli admin paneli
```

**MVP'de var:** `app.py`, `01_sayim_girisi.py`, `02_anlik_durum.py`, `03_haftalik_takip.py`, `99_admin.py`.

## Klasör Yapısı

```
db/          # models.py, connection.py, queries.py
utils/       # auth.py, week.py, permissions.py, audit.py
config/      # settings.py (pydantic-settings)
sql/         # schema.sql (referans, Supabase'de çalıştırıldı)
pages/
```

## Bağlantı / Ortam

- Supabase **Transaction Pooler (port 6543, IPv4)** kullanılıyor — Railway IPv6 desteklemiyor.
- `DATABASE_URL` env variable'dan okunur, `.env` git'te değil.
- `SECRET_KEY` session imzalama için.

## Geliştirme Ortamı (yerel makine)

- Python sistem PATH'inde **YOK**. Portable Python kullanılıyor:
  `C:\Users\elif.cakir\Desktop\python-3.12.4\python.exe`
- IT izni nedeniyle PATH'e eklenemiyor. Tüm `python` / `pip` çağrılarında **tam yol** kullan:
  ```
  C:\Users\elif.cakir\Desktop\python-3.12.4\python.exe -m venv venv
  C:\Users\elif.cakir\Desktop\python-3.12.4\python.exe -m pip install -r requirements.txt
  ```
- `venv` aktive edildikten sonra `python` komutu venv içinden gelir, sorun yok.
- **NOT:** Bu portable kurulum **embeddable distribution** — `venv` modülü içermiyor.
  Paketler doğrudan `python-3.12.4\Lib\site-packages`'a kuruluyor (izolasyon yok).
  Bu Python sadece bu projeye ayrılmış olduğu için sorun değil. İzolasyon
  istenirse `pip install virtualenv` ile alternatif kullanılabilir.

## Kod Kuralları

- Değişken/fonksiyon/sınıf isimleri **İngilizce**.
- Kullanıcıya gösterilen tüm metinler **Türkçe**.
- Tüm config env variable'dan; koda hardcode YOK.
- Şifreler bcrypt; plain text saklanmaz.
- DB session'ları context manager ile (`with SessionLocal() as session`).
- SQLAlchemy parametreli sorgular (zaten yapıyor); raw SQL'de string concat YOK.
- Streamlit'te login `st.session_state.user` üzerinden takip edilir.
- Frontend kanban validation: submit'ten önce `kanban_count <= full_count` uyarısı.

## Form (sayim_girisi) Davranışı

- Aktif renkler dinamik (`SELECT * FROM colors WHERE is_active=true`).
- Aynı (department, week) için tek kayıt — UPSERT.
- Sadece **"Gönder"** butonu var (taslak yok).
- Form yalnızca `get_submission_status(...) in ("open", "late")` iken açılır:
  - `open` → `status='submitted'`
  - `late` → `status='late_submitted'`
- `locked` durumunda kullanıcı form'a erişemez; sadece admin override.

## Çalıştırma

Proje kök dizininden, portable Python tam yoluyla:

**1. Bağımlılıkları kur** (sadece ilk kez veya requirements değişince):

```powershell
"C:\Users\elif.cakir\Desktop\python-3.12.4\python.exe" -m pip install -r requirements.txt
```

**2. `.env` dosyasını oluştur** (sadece ilk kez):

```powershell
Copy-Item .env.example .env
```

`.env`'i aç, `DATABASE_URL` (Supabase Transaction Pooler) ve `SECRET_KEY` doldur. SECRET_KEY üretmek için:

```powershell
"C:\Users\elif.cakir\Desktop\python-3.12.4\python.exe" -c "import secrets; print(secrets.token_urlsafe(48))"
```

**3. İlk admin kullanıcısını oluştur** (sadece ilk kez):

```powershell
"C:\Users\elif.cakir\Desktop\python-3.12.4\python.exe" -c "from db.connection import get_session; from utils.auth import hash_password; from db.models import User; ses=get_session();
import contextlib
with get_session() as s:
    s.add(User(username='admin', password_hash=hash_password('GECICI_SIFREYI_DEGISTIR'), full_name='Sistem Yöneticisi', role='admin'))
"
```

(Tek satırlık komut için ayrıntı: `app.py`'nin sonundaki yorum bloğuna bak.)

**4. Streamlit'i başlat:**

```powershell
"C:\Users\elif.cakir\Desktop\python-3.12.4\python.exe" -m streamlit run app.py
```

**5. Test çalıştır:**

```powershell
"C:\Users\elif.cakir\Desktop\python-3.12.4\python.exe" -m pytest tests/ -v
```

## MVP Öncelik Sırası

1. AGENTS.md, .gitignore, requirements.txt, .env.example, README.md ✅
2. Klasör iskeleti ✅
3. config/settings.py
4. db/connection.py
5. db/models.py
6. utils/week.py
7. utils/auth.py
8. app.py (login + yönlendirme)
9. pages/01_sayim_girisi.py
10. pages/99_admin.py (kullanıcı oluşturma)
11. pages/02_anlik_durum.py
12. pages/03_haftalik_takip.py

Her adımda dur, kullanıcıya göster, onay al. Toplu kod yazma yok.

## Yapma Listesi

- ❌ `streamlit-authenticator` ekleme
- ❌ Admin paneline "üretim yeri ekle/sil" koyma
- ❌ Color tablosundan kayıt silme (sadece deactivate)
- ❌ Plain text şifre saklama
- ❌ Form'a "Taslak Kaydet" butonu ekleme (sadece "Gönder" var)
- ❌ Otomatik geç giriş penceresi (Cuma 12:00 sonrası kapanır; admin manuel açar)
- ❌ Hardcoded DB URL / secret
- ❌ uv/poetry/pipenv ekleme
