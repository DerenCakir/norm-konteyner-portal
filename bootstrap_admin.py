"""
İlk admin kullanıcısını oluşturur. Sadece bir kez çalıştırılır.

Kullanım:
    python bootstrap_admin.py <username> <password> [full_name]

Örnekler:
    python bootstrap_admin.py admin GuvenliSifre2026 "Sistem Yöneticisi"
    python bootstrap_admin.py admin GuvenliSifre2026

Yerel geliştirmede:
    & "C:\\Users\\elif.cakir\\Desktop\\python-3.12.4\\python.exe" bootstrap_admin.py admin SifreBuraya

Railway production'da:
    Railway dashboard → Service → "..." menü → "Run a Command"
    veya `railway run python bootstrap_admin.py admin SifreBuraya` (CLI ile)

Idempotent: aynı username ile çalışırsa "zaten var" der, hata vermez.
Çalıştıktan sonra script repoda kalabilir — şifre artık argümanla geliyor.
"""

from __future__ import annotations

import os
import sys

# Embeddable Python sys.path fix (yerelde gerekli)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select  # noqa: E402

from db.connection import get_session  # noqa: E402
from db.models import User  # noqa: E402
from utils.auth import hash_password  # noqa: E402


def main() -> None:
    if len(sys.argv) < 3:
        print("Kullanım: bootstrap_admin.py <username> <password> [full_name]")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    full_name = sys.argv[3] if len(sys.argv) > 3 else "Sistem Yöneticisi"

    if len(password) < 8:
        print("HATA: Şifre en az 8 karakter olmalı.")
        sys.exit(1)

    with get_session() as s:
        existing = s.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        if existing is not None:
            print(f"Zaten mevcut: '{username}' (id={existing.id}). İşlem yapılmadı.")
            return

        s.add(User(
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            role="admin",
            is_active=True,
        ))
        print(f"✅ Admin oluşturuldu.")
        print(f"   Kullanıcı: {username}")
        print(f"   Ad Soyad:  {full_name}")
        print(f"   Rol:       admin")


if __name__ == "__main__":
    main()
