"""
Admin paneli — kullanıcı CRUD + bölüm yetkilendirme.

Sekmeler:
  1. Kullanıcılar:   yeni kullanıcı oluştur, listele, aktif/pasif yap
  2. Yetkilendirme:  bir kullanıcıya bölüm atama (çoka çok)

Tüm değişiklikler audit_log'a yazılır.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.connection import get_session
from db.models import (
    AuditLog,
    Department,
    ProductionSite,
    User,
    UserDepartment,
)
from utils.auth import hash_password, require_admin
from utils.ui import inject_css, page_header, render_sidebar_user


st.set_page_config(page_title="Admin Paneli", page_icon="⚙️", layout="wide")
inject_css()

# ---------------------------------------------------------------------------
# Yetki kontrolü — sadece adminler
# ---------------------------------------------------------------------------
with get_session() as _s:
    current_admin = require_admin(_s)
admin_id = current_admin.id
admin_username = current_admin.username
render_sidebar_user(current_admin.full_name, current_admin.role)

page_header(
    title="Admin Paneli",
    subtitle=f"Giriş yapan yönetici: {admin_username}",
    icon="⚙️",
)

tab_users, tab_perms = st.tabs(["👥 Kullanıcılar", "🔗 Yetkilendirme"])


# ---------------------------------------------------------------------------
# TAB 1 — KULLANICILAR
# ---------------------------------------------------------------------------
with tab_users:
    st.subheader("Yeni Kullanıcı Oluştur")

    with st.form("create_user_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("Kullanıcı adı")
            new_full_name = st.text_input("Ad Soyad")
        with col2:
            new_password = st.text_input("Geçici şifre", type="password")
            new_role = st.selectbox("Rol", ["user", "admin"], index=0,
                                     format_func=lambda r: "Kullanıcı" if r == "user" else "Yönetici")
        new_email = st.text_input("E-posta (opsiyonel)")
        create_clicked = st.form_submit_button("Oluştur", use_container_width=True)

    if create_clicked:
        if not new_username or not new_full_name or not new_password:
            st.error("Kullanıcı adı, ad soyad ve şifre zorunlu.")
        elif len(new_password) < 6:
            st.error("Şifre en az 6 karakter olmalı.")
        else:
            try:
                with get_session() as s:
                    existing = s.execute(
                        select(User).where(User.username == new_username.strip())
                    ).scalar_one_or_none()
                    if existing is not None:
                        st.error(f"'{new_username}' kullanıcı adı zaten alınmış.")
                    else:
                        u = User(
                            username=new_username.strip(),
                            password_hash=hash_password(new_password),
                            full_name=new_full_name.strip(),
                            email=(new_email.strip() or None),
                            role=new_role,
                            is_active=True,
                        )
                        s.add(u)
                        s.flush()  # u.id'i al
                        s.add(AuditLog(
                            user_id=admin_id,
                            action="user_create",
                            entity_type="user",
                            entity_id=u.id,
                            new_value={
                                "username": u.username,
                                "full_name": u.full_name,
                                "role": u.role,
                            },
                        ))
                        st.success(f"✅ '{new_username}' oluşturuldu.")
            except Exception as exc:
                st.error(f"Hata: {exc}")

    st.divider()
    st.subheader("Mevcut Kullanıcılar")

    with get_session() as s:
        users = list(s.execute(
            select(User).order_by(User.username)
        ).scalars())

    if not users:
        st.info("Henüz kullanıcı yok.")
    else:
        for u in users:
            cols = st.columns([2, 3, 1, 1, 1])
            cols[0].write(f"**{u.username}**")
            cols[1].write(u.full_name)
            cols[2].write("Yönetici" if u.role == "admin" else "Kullanıcı")
            cols[3].write("✅ Aktif" if u.is_active else "🚫 Pasif")

            # Kendini pasifleştirmesin
            if u.id == admin_id:
                cols[4].caption("(siz)")
            else:
                btn_label = "Pasifleştir" if u.is_active else "Aktif Et"
                if cols[4].button(btn_label, key=f"toggle_{u.id}"):
                    try:
                        with get_session() as s2:
                            target = s2.get(User, u.id)
                            old_state = target.is_active
                            target.is_active = not target.is_active
                            s2.add(AuditLog(
                                user_id=admin_id,
                                action="user_deactivate" if old_state else "user_activate",
                                entity_type="user",
                                entity_id=target.id,
                                old_value={"is_active": old_state},
                                new_value={"is_active": target.is_active},
                            ))
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Hata: {exc}")


# ---------------------------------------------------------------------------
# TAB 2 — YETKİLENDİRME
# ---------------------------------------------------------------------------
with tab_perms:
    st.subheader("Kullanıcı-Bölüm Yetkilendirme")
    st.caption("Bir kullanıcıyı seç, hangi bölümlerin sayımını girebileceğini belirle.")

    with get_session() as s:
        all_users = list(s.execute(
            select(User).where(User.is_active.is_(True)).order_by(User.username)
        ).scalars())
        all_depts = list(s.execute(
            select(Department, ProductionSite)
            .join(ProductionSite, Department.production_site_id == ProductionSite.id)
            .where(Department.is_active.is_(True))
            .order_by(ProductionSite.name, Department.name)
        ).all())

    if not all_users:
        st.info("Aktif kullanıcı yok.")
    elif not all_depts:
        st.info("Aktif bölüm yok.")
    else:
        user_options = {f"{u.username} — {u.full_name}": u.id for u in all_users}
        selected_label = st.selectbox("Kullanıcı seç", list(user_options.keys()))
        selected_user_id = user_options[selected_label]

        # Kullanıcının mevcut bölüm yetkilerini çek
        with get_session() as s:
            current_links = set(
                row[0] for row in s.execute(
                    select(UserDepartment.department_id)
                    .where(UserDepartment.user_id == selected_user_id)
                ).all()
            )

        st.write(f"**Mevcut yetkili olduğu bölüm sayısı:** {len(current_links)}")

        # Bölümleri üretim yerine göre grupla
        with st.form("perm_form"):
            st.write("Yetkili olduğu bölümleri işaretle:")
            new_selection: set[int] = set()

            grouped: dict[str, list[tuple[Department, ProductionSite]]] = {}
            for dept, site in all_depts:
                grouped.setdefault(site.name, []).append((dept, site))

            for site_name in sorted(grouped.keys()):
                with st.expander(site_name, expanded=False):
                    for dept, _site in grouped[site_name]:
                        checked = st.checkbox(
                            dept.name,
                            value=(dept.id in current_links),
                            key=f"perm_{selected_user_id}_{dept.id}",
                        )
                        if checked:
                            new_selection.add(dept.id)

            save_clicked = st.form_submit_button("Yetkileri Kaydet", use_container_width=True)

        if save_clicked:
            to_add = new_selection - current_links
            to_remove = current_links - new_selection

            if not to_add and not to_remove:
                st.info("Değişiklik yok.")
            else:
                try:
                    with get_session() as s:
                        for dept_id in to_add:
                            s.add(UserDepartment(
                                user_id=selected_user_id,
                                department_id=dept_id,
                            ))
                        for dept_id in to_remove:
                            link = s.execute(
                                select(UserDepartment).where(
                                    UserDepartment.user_id == selected_user_id,
                                    UserDepartment.department_id == dept_id,
                                )
                            ).scalar_one_or_none()
                            if link:
                                s.delete(link)
                        s.add(AuditLog(
                            user_id=admin_id,
                            action="user_departments_update",
                            entity_type="user",
                            entity_id=selected_user_id,
                            old_value={"department_ids": sorted(current_links)},
                            new_value={"department_ids": sorted(new_selection)},
                        ))
                    st.success(
                        f"✅ Güncellendi: +{len(to_add)} eklendi, -{len(to_remove)} kaldırıldı."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")
