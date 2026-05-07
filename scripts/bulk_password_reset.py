"""
Toplu şifre değiştirme yardımcısı.

DB'de şifreler bcrypt hash olarak saklı; direkt SQL ile düz şifre
yazamazsın. Bu script CSV'den (username, plain_password) okuyup
bcrypt ile hashler, Supabase SQL Editor'da çalıştırılabilecek
UPDATE statement'ları üretir.

Kullanım:
    1. scripts/passwords.csv dosyası oluştur (UTF-8):
           username,password
           admin,YeniAdmin2026
           ferhat.akel,YeniSifre1
           ali.veli,YeniSifre2

    2. Bu script'i portable Python ile çalıştır:
           "C:\\Users\\elif.cakir\\Desktop\\python-3.12.4\\python.exe" -m scripts.bulk_password_reset

    3. Çıktı SQL'i kopyala, Supabase SQL Editor'a yapıştır, Run.
       (Tek transaction — herhangi bir kullanıcı için UPDATE
       başarısız olursa hepsi geri alınır.)

Güvenlik:
    - passwords.csv .gitignore'da, repoya gitmiyor.
    - Hash bcrypt — geri çevrilemez. Eğer plain şifreleri
      kaybedersen, kullanıcıya yeni şifre bildirme yolun yok.
    - Audit log'a 'user_password_reset_bulk' satırı düşmüyor
      (script DB'ye yazmıyor); istenirse bu da eklenebilir.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import bcrypt


CSV_PATH = Path(__file__).parent / "passwords.csv"


def hash_password(plain: str) -> str:
    """utils.auth.hash_password'un kopyası — DB import etmeden çalışsın diye."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main() -> int:
    if not CSV_PATH.exists():
        print(f"HATA: {CSV_PATH} bulunamadı.", file=sys.stderr)
        print("CSV formatı:", file=sys.stderr)
        print("    username,password", file=sys.stderr)
        print("    admin,YeniAdmin2026", file=sys.stderr)
        return 1

    rows: list[tuple[str, str]] = []
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            username = (row.get("username") or "").strip()
            password = row.get("password") or ""
            if not username or not password:
                continue
            rows.append((username, password))

    if not rows:
        print("HATA: CSV boş veya geçersiz.", file=sys.stderr)
        return 1

    print("-- Toplu şifre güncellemesi (Supabase SQL Editor'a yapıştır)")
    print(f"-- {len(rows)} kullanıcı için bcrypt hash üretildi")
    print("BEGIN;")
    for username, password in rows:
        h = hash_password(password)
        # SQL içinde tek tırnak escape
        h_escaped = h.replace("'", "''")
        u_escaped = username.replace("'", "''")
        print(
            f"UPDATE users SET password_hash = '{h_escaped}' "
            f"WHERE username = '{u_escaped}';"
        )
    print("COMMIT;")
    print()
    print("-- Doğrulama:")
    usernames = ", ".join(f"'{u.replace(chr(39), chr(39) + chr(39))}'" for u, _ in rows)
    print(
        f"SELECT username, length(password_hash) AS hash_len, last_login_at "
        f"FROM users WHERE username IN ({usernames});"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
