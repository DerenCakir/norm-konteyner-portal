"""
Toplu şifre değiştirme yardımcısı.

İki kullanım modu var:

MOD A — Her kullanıcıya farklı şifre (CSV)
    1. scripts/passwords.csv dosyası oluştur (UTF-8):
           username,password
           admin,YeniAdmin2026
           ferhat.akel,YeniSifre1
           ali.veli,YeniSifre2
    2. Çalıştır:
           python scripts/bulk_password_reset.py

MOD B — Tüm kullanıcılara TEK ortak şifre (basit liste)
    1. scripts/usernames.txt dosyası oluştur, her satır bir kullanıcı:
           admin
           ferhat.akel
           ali.veli
           ...
    2. Şifreyi argüman olarak ver:
           python scripts/bulk_password_reset.py Norm2026!

Çıktı: Supabase SQL Editor'a yapıştırılacak UPDATE statement'ları.
Tek transaction (BEGIN/COMMIT) — tek bir hata hepsini geri alır.

Güvenlik:
    - passwords.csv ve usernames.txt .gitignore'da, repoya gitmez.
    - Hash bcrypt — geri çevrilemez.
    - Çalıştırma sonrası dosyaları silmen önerilir.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import bcrypt


CSV_PATH = Path(__file__).parent / "passwords.csv"
USERNAMES_TXT_PATH = Path(__file__).parent / "usernames.txt"


def hash_password(plain: str) -> str:
    """utils.auth.hash_password'un kopyası — DB import etmeden çalışsın diye."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _read_csv() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            username = (row.get("username") or "").strip()
            password = row.get("password") or ""
            if not username or not password:
                continue
            rows.append((username, password))
    return rows


def _read_usernames(shared_password: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with USERNAMES_TXT_PATH.open(encoding="utf-8") as f:
        for line in f:
            username = line.strip()
            if not username or username.startswith("#"):
                continue
            rows.append((username, shared_password))
    return rows


def main() -> int:
    # Mod B — tek argüman ile ortak şifre
    if len(sys.argv) == 2:
        shared_password = sys.argv[1]
        if not USERNAMES_TXT_PATH.exists():
            print(f"HATA: {USERNAMES_TXT_PATH} bulunamadı.", file=sys.stderr)
            print("Her satıra bir kullanıcı adı yazıp tekrar deneyin.", file=sys.stderr)
            return 1
        rows = _read_usernames(shared_password)
        mode_label = f"ortak şifre — {len(rows)} kullanıcı"
    # Mod A — CSV ile per-kullanıcı şifre
    elif CSV_PATH.exists():
        rows = _read_csv()
        mode_label = f"CSV per-kullanıcı — {len(rows)} kullanıcı"
    else:
        print("HATA: Ne passwords.csv ne usernames.txt bulundu.", file=sys.stderr)
        print("", file=sys.stderr)
        print("MOD A — her kullanıcıya farklı şifre:", file=sys.stderr)
        print(f"  {CSV_PATH.name} dosyası oluştur, sonra: python {Path(__file__).name}", file=sys.stderr)
        print("", file=sys.stderr)
        print("MOD B — herkese aynı şifre:", file=sys.stderr)
        print(f"  {USERNAMES_TXT_PATH.name} (her satır bir kullanıcı), sonra:", file=sys.stderr)
        print(f"  python {Path(__file__).name} Norm2026!", file=sys.stderr)
        return 1

    if not rows:
        print("HATA: Liste boş.", file=sys.stderr)
        return 1

    print("-- Toplu şifre güncellemesi (Supabase SQL Editor'a yapıştır)")
    print(f"-- Mod: {mode_label}")
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
