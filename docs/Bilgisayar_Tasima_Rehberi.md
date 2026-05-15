# Bilgisayar Taşıma Rehberi

Yeni bilgisayara projeyi taşıma adımları. Tahmini süre: **30–45 dakika**.

> ⚠️ **Hassas bilgi:** Bu rehber sadece yöntemi anlatır. Şifreler, token'lar, DB
> bağlantı string'leri vb. dosyaya yazılmamıştır — onları **manuel** olarak
> (parola yöneticisi, kağıt not, ya da güvenli notlar) yanında getir.

---

## Eski bilgisayarda — almayı unutma

### 1. Proje klasörünü tam kopyala

```
C:\Users\<eski-kullanıcı>\Desktop\Norm-konteyner-portal\
```

USB veya OneDrive ile. **`.env` dosyası dahil** — bu dosya `DATABASE_URL` ve
`SECRET_KEY` içeriyor, repoda yok, onsuz portal çalışmaz.

### 2. Portable Python klasörünü kopyala

```
C:\Users\<eski-kullanıcı>\Desktop\python-3.12.4\
```

Bütün klasör; içinde tüm paketler kurulu.

### 3. Yanına yaz / parola yöneticisine kaydet

| Bilgi | Nerede bulunur |
|---|---|
| GitHub kullanıcı adı | Anahtar görevini PAT yapıyor (bkz. aşağı) |
| GitHub Personal Access Token (PAT) | github.com → Settings → Developer settings → Personal access tokens |
| Supabase login (e-mail + şifre) | supabase.com hesabın |
| Railway login (e-mail + şifre) | railway.app hesabın |
| `.env` dosyasının içeriği (yedek) | Proje köşesindeki `.env` — açıp metnini kopyala |
| Git config | PowerShell'de `git config --global user.name` ve `user.email` |

PAT yoksa: GitHub → Settings → Developer settings → Personal access tokens →
Tokens (classic) → Generate new → `repo` ve `workflow` scope'larını işaretle →
30-90 gün geçerli yap. **Bu kez göründüğünde mutlaka not al** (bir kez gösterilir).

---

## Yeni bilgisayarda — kurulum

### 1. Git'i kur

https://git-scm.com/download/win — varsayılan ayarlarla kur.

PowerShell aç, git'in çalıştığını doğrula:
```powershell
git --version
```

Adını ve e-mail'ini ayarla (commit mesajları için):
```powershell
git config --global user.name "Senin Adın"
git config --global user.email "senin@email.com"
```

### 2. Klasörleri yerleştir

USB/OneDrive'dan masaüstüne kopyala:

```
C:\Users\<yeni-kullanıcı>\Desktop\python-3.12.4\
C:\Users\<yeni-kullanıcı>\Desktop\Norm-konteyner-portal\
```

> Yeni bilgisayarda Windows kullanıcı adın farklıysa, bu klasörlerin
> içindeki bazı dökümanlarda (`CLAUDE.md`, eski commit mesajları) eski
> `elif.cakir` yolu yazıyor olabilir. Komutlardaki tam yolları kendi
> kullanıcı adınla güncelle.

### 3. Python paketleri (gerekirse)

Portable Python'u kopyaladıysan **tüm paketler zaten yüklü**. Test et:

```powershell
cd C:\Users\<yeni-kullanıcı>\Desktop\Norm-konteyner-portal
"C:\Users\<yeni-kullanıcı>\Desktop\python-3.12.4\python.exe" -m streamlit run app.py
```

Tarayıcıda login ekranı açılırsa tamamdır.

Eğer paket eksik diye hata verirse:
```powershell
"C:\Users\<yeni-kullanıcı>\Desktop\python-3.12.4\python.exe" -m pip install -r requirements.txt
```

### 4. GitHub bağlantısını test et

```powershell
cd C:\Users\<yeni-kullanıcı>\Desktop\Norm-konteyner-portal
git status
git pull origin main
```

İlk pull/push'ta GitHub kullanıcı adı + PAT (şifre yerine) ister.

### 5. Production portala erişim

Tarayıcıdan Railway'deki canlı portal URL'ine git, hesabınla giriş yap.
Çalıştığını doğrula.

---

## Alternatif: USB yerine GitHub'dan çekme

USB yoksa veya proje klasörü çok büyükse:

```powershell
cd C:\Users\<yeni-kullanıcı>\Desktop
git clone https://github.com/DerenCakir/norm-konteyner-portal.git Norm-konteyner-portal
cd Norm-konteyner-portal

# .env dosyasını manuel oluştur — eski makinedeki içeriği yapıştır
notepad .env

# Paketleri kur
"C:\Users\<yeni-kullanıcı>\Desktop\python-3.12.4\python.exe" -m pip install -r requirements.txt
```

> Portable Python yine USB ile gelmesi lazım — pip install için Python gerekiyor,
> ve sistem PATH'inde Python yok.

> `.env` repoda gitmiyor. **Eski makinedeki içeriği manuel kopyala.**
> İçeriği genelde şu formatta:
> ```
> DATABASE_URL=postgresql://...
> SECRET_KEY=...
> ```

---

## Hızlı kontrol listesi

Yeni makinede:

- [ ] Git kurulu, `git --version` çalışıyor
- [ ] `git config user.name` ve `user.email` ayarlı
- [ ] Proje klasörü masaüstünde
- [ ] `.env` dosyası proje köşesinde, içinde `DATABASE_URL` ve `SECRET_KEY` var
- [ ] Portable Python masaüstünde, `python.exe -V` çalışıyor
- [ ] `streamlit run app.py` lokalde açılıyor, login oluyor
- [ ] `git pull` ve `git push` çalışıyor (PAT ile)
- [ ] Railway'deki canlı portal'a tarayıcıdan giriş yapabiliyorum
- [ ] Supabase Dashboard'a giriş yapabiliyorum

---

## Sorun çıkarsa

| Belirti | Çözüm |
|---|---|
| `streamlit: command not found` | Streamlit'i tam yol ile çağır: `python.exe -m streamlit run app.py` |
| `ModuleNotFoundError: streamlit` | `pip install -r requirements.txt` çalıştır |
| Login'de "DB bağlantısı yok" | `.env` dosyası eksik ya da `DATABASE_URL` hatalı |
| `git push` "permission denied" | PAT geçersiz/süresi dolmuş → yenisini üret |
| Portal çalışıyor ama veriler gözükmüyor | Browser cache → `Ctrl+Shift+R` ile hard refresh |

Yine takılırsan Claude Code'a (claude.ai) "Norm Konteyner projesinde yeni bilgisayara
geçtim, X hatası alıyorum" diyerek sor.
