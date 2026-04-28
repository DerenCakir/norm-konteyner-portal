"""
Bir kullanıcının şifresini değiştirir.

Kullanım:
    & "C:\\Users\\elif.cakir\\Desktop\\python-3.12.4\\python.exe" change_password.py <username> <new_password>

Örnek:
    ... change_password.py admin Norm2026Yeni
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select  # noqa: E402

from db.connection import get_session  # noqa: E402
from db.models import User  # noqa: E402
from utils.auth import hash_password  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print("Kullanım: change_password.py <username> <new_password>")
        sys.exit(1)

    username = sys.argv[1]
    new_password = sys.argv[2]

    if len(new_password) < 6:
        print("HATA: Şifre en az 6 karakter olmalı.")
        sys.exit(1)

    with get_session() as s:
        user = s.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()

        if user is None:
            print(f"HATA: '{username}' kullanıcısı yok.")
            sys.exit(1)

        user.password_hash = hash_password(new_password)
        print(f"✅ '{username}' şifresi güncellendi.")


if __name__ == "__main__":
    main()
