"""
Admin paneli — kullanıcı CRUD + bölüm yetkilendirme.

Sekmeler:
  1. Kullanıcılar:   yeni kullanıcı oluştur, listele, aktif/pasif yap
  2. Yetkilendirme:  bir kullanıcıya bölüm atama (çoka çok)

Tüm değişiklikler audit_log'a yazılır.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from db.connection import get_session
from db.models import (
    AuditLog,
    Color,
    CountDetail,
    CountSubmission,
    Department,
    LateWindowOverride,
    ProductionSite,
    User,
    UserDepartment,
)
from utils.auth import hash_password, require_admin, restore_session_from_cookie
from utils.cached_queries import clear_cached_queries
from utils.performance import page_timer
from utils.ui import inject_css, page_header, render_sidebar_user
from utils.week import current_week_iso, format_week_human, now_tr, week_iso_from_date


inject_css()
restore_session_from_cookie()
timer = page_timer("admin")

# ---------------------------------------------------------------------------
# Yetki kontrolü — sadece adminler
# ---------------------------------------------------------------------------
with get_session() as _s:
    current_admin = require_admin(_s)
admin_id = current_admin.id
admin_username = current_admin.username
render_sidebar_user(current_admin.full_name, current_admin.role)


def _role_label(role: str) -> str:
    return "Yönetici" if role == "admin" else "Kullanıcı"


def _user_label(user: User) -> str:
    status = "Aktif" if user.is_active else "Pasif"
    return f"{user.username} — {user.full_name} ({_role_label(user.role)}, {status})"

page_header(
    title="Admin Paneli",
    subtitle=f"Giriş yapan yönetici: {admin_username}",
    )

tab_users, tab_perms, tab_departments, tab_colors, tab_late, tab_override, tab_audit = st.tabs([
    "Kullanıcılar",
    "Yetkilendirme",
    "Bölümler",
    "Renkler",
    "Geç Giriş",
    "Sayım Düzeltme",
    "İşlem Geçmişi",
])


def _recent_week_options(count: int = 12) -> list[str]:
    """Return current and previous ISO weeks for admin workflows."""
    today = now_tr().date()
    weeks: list[str] = []
    for offset in range(count):
        week = week_iso_from_date(today - timedelta(days=offset * 7))
        if week not in weeks:
            weeks.append(week)
    return weeks


def _merge_week_options(*groups: list[str]) -> list[str]:
    weeks: list[str] = []
    for group in groups:
        for week in group:
            if week not in weeks:
                weeks.append(week)
    return weeks


def _valid_hex_code(value: str) -> bool:
    if not value:
        return True
    if len(value) != 7 or not value.startswith("#"):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value[1:])


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
                        clear_cached_queries()
                        st.success(f"'{new_username}' oluşturuldu.")
            except Exception as exc:
                st.error(f"Hata: {exc}")

    st.divider()
    st.subheader("Kullanıcı Düzenle / Şifre Sıfırla")
    st.caption("Kullanıcılar fiziksel olarak silinmez; geçmiş sayım kayıtları bozulmasın diye pasif hale getirilir.")

    with get_session() as s:
        editable_users = list(s.execute(
            select(User).order_by(User.username)
        ).scalars())

    if not editable_users:
        st.info("Düzenlenecek kullanıcı yok.")
    else:
        selected_user_id = st.selectbox(
            "Düzenlenecek kullanıcı",
            [u.id for u in editable_users],
            format_func=lambda user_id: _user_label(next(u for u in editable_users if u.id == user_id)),
            key="edit_user_select",
        )
        selected_user = next(u for u in editable_users if u.id == selected_user_id)

        user_form_key = f"edit_user_{selected_user_id}"
        with st.form(f"edit_user_form_{selected_user_id}"):
            col1, col2 = st.columns(2)
            with col1:
                edit_username = st.text_input(
                    "Kullanıcı adı",
                    value=selected_user.username,
                    key=f"{user_form_key}_username",
                )
                edit_full_name = st.text_input(
                    "Ad Soyad",
                    value=selected_user.full_name,
                    key=f"{user_form_key}_full_name",
                )
                edit_email = st.text_input(
                    "E-posta (opsiyonel)",
                    value=selected_user.email or "",
                    key=f"{user_form_key}_email",
                )
            with col2:
                edit_role = st.selectbox(
                    "Rol",
                    ["user", "admin"],
                    index=0 if selected_user.role == "user" else 1,
                    format_func=_role_label,
                    key=f"{user_form_key}_role",
                )
                edit_is_active = st.checkbox(
                    "Aktif",
                    value=selected_user.is_active,
                    key=f"{user_form_key}_active",
                )
                edit_password = st.text_input(
                    "Yeni şifre (boş bırakırsan değişmez)",
                    type="password",
                    key=f"{user_form_key}_password",
                )

            update_clicked = st.form_submit_button("Kullanıcıyı Güncelle", use_container_width=True)

        if update_clicked:
            clean_username = edit_username.strip()
            clean_full_name = edit_full_name.strip()
            clean_email = edit_email.strip() or None

            if not clean_username or not clean_full_name:
                st.error("Kullanıcı adı ve ad soyad zorunlu.")
            elif edit_password and len(edit_password) < 6:
                st.error("Yeni şifre en az 6 karakter olmalı.")
            elif selected_user_id == admin_id and (not edit_is_active or edit_role != "admin"):
                st.error("Kendi yönetici hesabınızı pasifleştiremez veya kullanıcı rolüne düşüremezsiniz.")
            else:
                try:
                    with get_session() as s:
                        target = s.get(User, selected_user_id)
                        username_taken = s.execute(
                            select(User).where(
                                User.username == clean_username,
                                User.id != selected_user_id,
                            )
                        ).scalar_one_or_none()

                        if username_taken is not None:
                            st.error(f"'{clean_username}' kullanıcı adı zaten alınmış.")
                        else:
                            old_value = {
                                "username": target.username,
                                "full_name": target.full_name,
                                "email": target.email,
                                "role": target.role,
                                "is_active": target.is_active,
                            }

                            target.username = clean_username
                            target.full_name = clean_full_name
                            target.email = clean_email
                            target.role = edit_role
                            target.is_active = edit_is_active

                            new_value = {
                                "username": target.username,
                                "full_name": target.full_name,
                                "email": target.email,
                                "role": target.role,
                                "is_active": target.is_active,
                            }

                            s.add(AuditLog(
                                user_id=admin_id,
                                action="user_update",
                                entity_type="user",
                                entity_id=target.id,
                                old_value=old_value,
                                new_value=new_value,
                            ))

                            if edit_password:
                                target.password_hash = hash_password(edit_password)
                                s.add(AuditLog(
                                    user_id=admin_id,
                                    action="user_password_reset",
                                    entity_type="user",
                                    entity_id=target.id,
                                    old_value=None,
                                    new_value={"username": target.username},
                                ))

                            clear_cached_queries()
                            if selected_user_id == admin_id:
                                st.session_state["username"] = target.username
                                st.session_state["role"] = target.role
                                st.session_state["full_name"] = target.full_name
                            st.success(f"'{target.username}' güncellendi.")
                            st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")


# ---------------------------------------------------------------------------
# TAB 6 — RENKLER
# ---------------------------------------------------------------------------
with tab_colors:
    st.subheader("Renk Yönetimi")
    st.caption("Renkler fiziksel olarak silinmez; geçmiş sayımlar bozulmasın diye pasif hale getirilir.")

    with get_session() as s:
        colors = list(s.execute(
            select(Color).order_by(Color.sort_order, Color.id)
        ).scalars())

    st.markdown("#### Yeni Renk Ekle")
    with st.form("create_color_form", clear_on_submit=True):
        col_name, col_hex, col_sort = st.columns([2, 1, 1])
        color_name = col_name.text_input("Renk Adı")
        color_hex = col_hex.text_input("Hex Kod", placeholder="#1f77b4")
        color_sort = col_sort.number_input("Sıra", min_value=0, value=0, step=1)
        create_color_clicked = st.form_submit_button("Renk Ekle", use_container_width=True)

    if create_color_clicked:
        clean_name = color_name.strip()
        clean_hex = color_hex.strip() or None
        if not clean_name:
            st.error("Renk adı zorunlu.")
        elif clean_hex and not _valid_hex_code(clean_hex):
            st.error("Hex kod #RRGGBB formatında olmalı.")
        else:
            try:
                with get_session() as s:
                    existing = s.execute(
                        select(Color).where(Color.name == clean_name)
                    ).scalar_one_or_none()
                    if existing is not None:
                        st.error("Bu renk adı zaten var.")
                    else:
                        color = Color(
                            name=clean_name,
                            hex_code=clean_hex,
                            sort_order=int(color_sort),
                            is_active=True,
                        )
                        s.add(color)
                        s.flush()
                        s.add(AuditLog(
                            user_id=admin_id,
                            action="color_create",
                            entity_type="color",
                            entity_id=color.id,
                            new_value={
                                "name": color.name,
                                "hex_code": color.hex_code,
                                "sort_order": color.sort_order,
                                "is_active": color.is_active,
                            },
                        ))
                clear_cached_queries()
                st.success(f"'{clean_name}' rengi eklendi.")
                st.rerun()
            except Exception as exc:
                st.error(f"Hata: {exc}")

    st.divider()
    st.markdown("#### Renk Düzenle / Pasifleştir")

    if not colors:
        st.info("Düzenlenecek renk yok.")
    else:
        color_options = {
            f"{color.sort_order} — {color.name} ({'Aktif' if color.is_active else 'Pasif'})": color.id
            for color in colors
        }
        selected_color_label = st.selectbox("Düzenlenecek renk", list(color_options.keys()))
        selected_color_id = color_options[selected_color_label]
        selected_color = next(color for color in colors if color.id == selected_color_id)

        with st.form(f"edit_color_form_{selected_color_id}"):
            col_name, col_hex, col_sort, col_active = st.columns([2, 1, 1, 1])
            edit_color_name = col_name.text_input(
                "Renk Adı",
                value=selected_color.name,
                key=f"color_{selected_color_id}_name",
            )
            edit_color_hex = col_hex.text_input(
                "Hex Kod",
                value=selected_color.hex_code or "",
                key=f"color_{selected_color_id}_hex",
            )
            edit_color_sort = col_sort.number_input(
                "Sıra",
                min_value=0,
                value=int(selected_color.sort_order or 0),
                step=1,
                key=f"color_{selected_color_id}_sort",
            )
            edit_color_active = col_active.checkbox(
                "Aktif",
                value=selected_color.is_active,
                key=f"color_{selected_color_id}_active",
            )
            update_color_clicked = st.form_submit_button("Rengi Güncelle", use_container_width=True)

        if update_color_clicked:
            clean_name = edit_color_name.strip()
            clean_hex = edit_color_hex.strip() or None
            if not clean_name:
                st.error("Renk adı zorunlu.")
            elif clean_hex and not _valid_hex_code(clean_hex):
                st.error("Hex kod #RRGGBB formatında olmalı.")
            else:
                try:
                    with get_session() as s:
                        duplicate = s.execute(
                            select(Color).where(
                                Color.name == clean_name,
                                Color.id != selected_color_id,
                            )
                        ).scalar_one_or_none()
                        if duplicate is not None:
                            st.error("Bu renk adı zaten var.")
                        else:
                            color = s.get(Color, selected_color_id)
                            old_value = {
                                "name": color.name,
                                "hex_code": color.hex_code,
                                "sort_order": color.sort_order,
                                "is_active": color.is_active,
                            }
                            color.name = clean_name
                            color.hex_code = clean_hex
                            color.sort_order = int(edit_color_sort)
                            color.is_active = edit_color_active
                            s.add(AuditLog(
                                user_id=admin_id,
                                action="color_update",
                                entity_type="color",
                                entity_id=color.id,
                                old_value=old_value,
                                new_value={
                                    "name": color.name,
                                    "hex_code": color.hex_code,
                                    "sort_order": color.sort_order,
                                    "is_active": color.is_active,
                                },
                            ))
                    clear_cached_queries()
                    st.success("Renk güncellendi.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")

        if selected_color.is_active:
            if st.button("Rengi Sil (Pasifleştir)", key=f"deactivate_color_{selected_color_id}", use_container_width=True):
                try:
                    with get_session() as s:
                        color = s.get(Color, selected_color_id)
                        old_state = color.is_active
                        color.is_active = False
                        s.add(AuditLog(
                            user_id=admin_id,
                            action="color_delete",
                            entity_type="color",
                            entity_id=color.id,
                            old_value={"is_active": old_state},
                            new_value={"is_active": False, "delete_mode": "soft"},
                        ))
                    clear_cached_queries()
                    st.success("Renk pasifleştirildi.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")

        rows = [
            {
                "Renk": color.name,
                "Hex": color.hex_code or "-",
                "Sıra": color.sort_order,
                "Durum": "Aktif" if color.is_active else "Pasif",
            }
            for color in colors
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# TAB 7 — AUDIT LOG
# ---------------------------------------------------------------------------
with tab_audit:
    st.subheader("Audit Log")
    st.caption("Güvenlik ve operasyon açısından önemli işlemlerin kaydı.")

    with get_session() as s:
        action_options = list(s.execute(
            select(AuditLog.action).distinct().order_by(AuditLog.action)
        ).scalars())
        user_options = list(s.execute(
            select(User).order_by(User.full_name)
        ).scalars())

    col_action, col_user, col_limit = st.columns([2, 2, 1])
    selected_action = col_action.selectbox("İşlem", ["Tümü"] + action_options)
    selected_audit_user = col_user.selectbox(
        "Kullanıcı",
        [0] + [user.id for user in user_options],
        format_func=lambda user_id: (
            "Tümü" if user_id == 0 else _user_label(next(user for user in user_options if user.id == user_id))
        ),
    )
    audit_limit = col_limit.number_input("Kayıt", min_value=50, max_value=1000, value=200, step=50)

    with get_session() as s:
        query = select(AuditLog, User).outerjoin(User, User.id == AuditLog.user_id)
        if selected_action != "Tümü":
            query = query.where(AuditLog.action == selected_action)
        if selected_audit_user != 0:
            query = query.where(AuditLog.user_id == selected_audit_user)
        query = query.order_by(AuditLog.timestamp.desc()).limit(int(audit_limit))
        audit_rows = list(s.execute(query).all())

    if not audit_rows:
        st.info("Seçilen filtrelerde audit kaydı yok.")
    else:
        rows = []
        for log, user in audit_rows:
            rows.append({
                "Zaman": now_tr(log.timestamp).strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "-",
                "Kullanıcı": user.full_name if user else "-",
                "İşlem": log.action,
                "Varlık": log.entity_type or "-",
                "Varlık ID": log.entity_id or "-",
                "Eski Değer": log.old_value or "-",
                "Yeni Değer": log.new_value or "-",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

with tab_users:
    if editable_users and selected_user_id != admin_id:
            if st.button(
                "Kullanıcıyı Sil (Pasifleştir)",
                key=f"soft_delete_user_{selected_user_id}",
                use_container_width=True,
            ):
                try:
                    with get_session() as s:
                        target = s.get(User, selected_user_id)
                        old_state = target.is_active
                        target.is_active = False
                        s.add(AuditLog(
                            user_id=admin_id,
                            action="user_delete",
                            entity_type="user",
                            entity_id=target.id,
                            old_value={"is_active": old_state},
                            new_value={"is_active": False, "delete_mode": "soft"},
                        ))
                    clear_cached_queries()
                    st.success(f"'{selected_user.username}' pasifleştirildi.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")


# ---------------------------------------------------------------------------
# TAB 5 — BÖLÜMLER
# ---------------------------------------------------------------------------
with tab_departments:
    st.subheader("Bölüm Yönetimi")
    st.caption("Üretim yerleri sabittir; buradan mevcut üretim yerlerinin altındaki bölümler eklenir, düzenlenir veya pasifleştirilir.")

    with get_session() as s:
        sites = list(s.execute(
            select(ProductionSite)
            .where(ProductionSite.is_active.is_(True))
            .order_by(ProductionSite.name)
        ).scalars())
        departments = list(s.execute(
            select(Department, ProductionSite)
            .join(ProductionSite, Department.production_site_id == ProductionSite.id)
            .order_by(ProductionSite.name, Department.name)
        ).all())

    if not sites:
        st.info("Aktif üretim yeri bulunamadı.")
    else:
        st.markdown("#### Yeni Bölüm Ekle")
        with st.form("create_department_form", clear_on_submit=True):
            site_options = {site.name: site.id for site in sites}
            create_site_name = st.selectbox("Üretim Yeri", list(site_options.keys()))
            create_department_name = st.text_input("Bölüm / Müşteri Adı")
            create_tonnage = st.number_input(
                "Haftalık Tonaj Hedefi",
                min_value=0.0,
                value=0.0,
                step=0.1,
                format="%.2f",
            )
            create_department_clicked = st.form_submit_button("Bölüm Ekle", use_container_width=True)

        if create_department_clicked:
            clean_name = create_department_name.strip()
            site_id = site_options[create_site_name]
            if not clean_name:
                st.error("Bölüm adı zorunlu.")
            else:
                try:
                    with get_session() as s:
                        existing = s.execute(
                            select(Department).where(
                                Department.production_site_id == site_id,
                                Department.name == clean_name,
                            )
                        ).scalar_one_or_none()
                        if existing is not None:
                            st.error("Bu üretim yeri altında aynı bölüm adı zaten var.")
                        else:
                            dept = Department(
                                production_site_id=site_id,
                                name=clean_name,
                                weekly_tonnage_target=Decimal(str(create_tonnage)),
                                is_active=True,
                            )
                            s.add(dept)
                            s.flush()
                            s.add(AuditLog(
                                user_id=admin_id,
                                action="department_create",
                                entity_type="department",
                                entity_id=dept.id,
                                new_value={
                                    "production_site_id": site_id,
                                    "name": dept.name,
                                    "weekly_tonnage_target": float(create_tonnage),
                                },
                            ))
                    clear_cached_queries()
                    st.success(f"'{clean_name}' bölümü eklendi.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")

        st.divider()
        st.markdown("#### Bölüm Düzenle / Sil")

        if not departments:
            st.info("Düzenlenecek bölüm yok.")
        else:
            dept_options = {
                f"{site.name} — {dept.name} ({'Aktif' if dept.is_active else 'Pasif'})": dept.id
                for dept, site in departments
            }
            selected_dept_label = st.selectbox("Düzenlenecek bölüm", list(dept_options.keys()))
            selected_dept_id = dept_options[selected_dept_label]
            selected_dept, selected_site = next(
                (dept, site) for dept, site in departments if dept.id == selected_dept_id
            )

            with st.form("edit_department_form"):
                edit_site_options = {site.name: site.id for site in sites}
                site_names = list(edit_site_options.keys())
                current_site_index = site_names.index(selected_site.name)
                edit_site_name = st.selectbox("Üretim Yeri", site_names, index=current_site_index)
                edit_department_name = st.text_input("Bölüm / Müşteri Adı", value=selected_dept.name)
                edit_tonnage = st.number_input(
                    "Haftalık Tonaj Hedefi",
                    min_value=0.0,
                    value=float(selected_dept.weekly_tonnage_target or 0),
                    step=0.1,
                    format="%.2f",
                )
                edit_department_active = st.checkbox("Aktif", value=selected_dept.is_active)
                edit_department_clicked = st.form_submit_button("Bölümü Güncelle", use_container_width=True)

            if edit_department_clicked:
                clean_name = edit_department_name.strip()
                new_site_id = edit_site_options[edit_site_name]
                if not clean_name:
                    st.error("Bölüm adı zorunlu.")
                else:
                    try:
                        with get_session() as s:
                            duplicate = s.execute(
                                select(Department).where(
                                    Department.production_site_id == new_site_id,
                                    Department.name == clean_name,
                                    Department.id != selected_dept_id,
                                )
                            ).scalar_one_or_none()
                            if duplicate is not None:
                                st.error("Bu üretim yeri altında aynı bölüm adı zaten var.")
                            else:
                                dept = s.get(Department, selected_dept_id)
                                old_value = {
                                    "production_site_id": dept.production_site_id,
                                    "name": dept.name,
                                    "weekly_tonnage_target": float(dept.weekly_tonnage_target or 0),
                                    "is_active": dept.is_active,
                                }
                                dept.production_site_id = new_site_id
                                dept.name = clean_name
                                dept.weekly_tonnage_target = Decimal(str(edit_tonnage))
                                dept.is_active = edit_department_active
                                s.add(AuditLog(
                                    user_id=admin_id,
                                    action="department_update",
                                    entity_type="department",
                                    entity_id=dept.id,
                                    old_value=old_value,
                                    new_value={
                                        "production_site_id": dept.production_site_id,
                                        "name": dept.name,
                                        "weekly_tonnage_target": float(edit_tonnage),
                                        "is_active": dept.is_active,
                                    },
                                ))
                        clear_cached_queries()
                        st.success("Bölüm güncellendi.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Hata: {exc}")

            if st.button("Bölümü Sil (Pasifleştir)", key="soft_delete_department", use_container_width=True):
                try:
                    with get_session() as s:
                        dept = s.get(Department, selected_dept_id)
                        old_state = dept.is_active
                        dept.is_active = False
                        s.add(AuditLog(
                            user_id=admin_id,
                            action="department_delete",
                            entity_type="department",
                            entity_id=dept.id,
                            old_value={"is_active": old_state},
                            new_value={"is_active": False, "delete_mode": "soft"},
                        ))
                    clear_cached_queries()
                    st.success("Bölüm pasifleştirildi.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")

with tab_users:
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
            cols[3].write("Aktif" if u.is_active else "Pasif")

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
                        clear_cached_queries()
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
        selected_user_id = st.selectbox(
            "Kullanıcı seç",
            [u.id for u in all_users],
            format_func=lambda user_id: _user_label(next(u for u in all_users if u.id == user_id)),
            key="permission_user_select",
        )

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
                    clear_cached_queries()
                    st.success(
                        f"Güncellendi: +{len(to_add)} eklendi, -{len(to_remove)} kaldırıldı."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")


# ---------------------------------------------------------------------------
# TAB 3 — GEÇ GİRİŞ PENCERESİ
# ---------------------------------------------------------------------------
with tab_late:
    st.subheader("Geç Giriş Penceresi")
    st.caption("Kapanmış bir hafta için kullanıcıların sayım girebilmesini sağlar.")

    with get_session() as s:
        known_weeks = list(s.execute(
            select(CountSubmission.week_iso)
            .distinct()
            .order_by(CountSubmission.week_iso.desc())
        ).scalars())

    current_week = current_week_iso()
    known_weeks = _merge_week_options(_recent_week_options(12), known_weeks)

    with st.form("late_window_form"):
        selected_week = st.selectbox(
            "Hafta",
            known_weeks,
            index=0,
            format_func=lambda w: f"{w} — {format_week_human(w)}",
        )
        col_date, col_time = st.columns(2)
        closes_date = col_date.date_input("Kapanış tarihi", value=now_tr().date())
        closes_time = col_time.time_input("Kapanış saati", value=now_tr().time().replace(microsecond=0))
        reason = st.text_area("Açıklama", placeholder="Örn. bölüm sayımı zamanında tamamlanamadı")
        open_clicked = st.form_submit_button("Pencereyi Aç / Güncelle", use_container_width=True)

    if open_clicked:
        closes_at = now_tr(datetime.combine(closes_date, closes_time))
        if closes_at <= now_tr():
            st.error("Kapanış zamanı şu andan ileri olmalı.")
        else:
            try:
                with get_session() as s:
                    existing = s.get(LateWindowOverride, selected_week)
                    old_value = None
                    if existing is None:
                        override = LateWindowOverride(
                            week_iso=selected_week,
                            opened_by=admin_id,
                            closes_at=closes_at,
                            reason=(reason.strip() or None),
                        )
                        s.add(override)
                    else:
                        old_value = {
                            "closes_at": existing.closes_at.isoformat(),
                            "reason": existing.reason,
                        }
                        existing.opened_by = admin_id
                        existing.opened_at = now_tr()
                        existing.closes_at = closes_at
                        existing.reason = reason.strip() or None

                    s.add(AuditLog(
                        user_id=admin_id,
                        action="late_window_open",
                        entity_type="late_window_override",
                        entity_id=None,
                        old_value=old_value,
                        new_value={
                            "week_iso": selected_week,
                            "closes_at": closes_at.isoformat(),
                            "reason": reason.strip() or None,
                        },
                    ))
                clear_cached_queries()
                st.success(f"{selected_week} için geç giriş penceresi açıldı.")
                st.rerun()
            except Exception as exc:
                st.error(f"Hata: {exc}")

    st.divider()
    st.subheader("Açık / Geçmiş Pencereler")

    with get_session() as s:
        overrides = list(s.execute(
            select(LateWindowOverride, User)
            .join(User, User.id == LateWindowOverride.opened_by)
            .order_by(LateWindowOverride.closes_at.desc())
        ).all())

    if not overrides:
        st.info("Henüz geç giriş penceresi yok.")
    else:
        rows = []
        current_time = now_tr()
        for override, opened_by in overrides:
            rows.append({
                "Hafta": override.week_iso,
                "Tarih Aralığı": format_week_human(override.week_iso),
                "Durum": "Açık" if now_tr(override.closes_at) > current_time else "Kapandı",
                "Kapanış": now_tr(override.closes_at).strftime("%Y-%m-%d %H:%M"),
                "Açan": opened_by.full_name,
                "Açıklama": override.reason or "-",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# TAB 6 — SAYIM DÜZELTME
# ---------------------------------------------------------------------------
with tab_override:
    st.subheader("Sayım Düzeltme")
    st.caption("Pencere kapandıktan sonra hatalı sayımı yönetici olarak düzenle veya sil.")

    with get_session() as s:
        override_weeks = list(s.execute(
            select(CountSubmission.week_iso)
            .distinct()
            .order_by(CountSubmission.week_iso.desc())
        ).scalars())
        override_weeks = _merge_week_options(_recent_week_options(12), override_weeks)

        override_depts = list(s.execute(
            select(Department, ProductionSite)
            .join(ProductionSite, Department.production_site_id == ProductionSite.id)
            .where(Department.is_active.is_(True))
            .order_by(ProductionSite.name, Department.name)
        ).all())

        override_colors = list(s.execute(
            select(Color)
            .where(Color.is_active.is_(True))
            .order_by(Color.sort_order, Color.id)
        ).scalars())

    if not override_depts or not override_colors:
        st.info("Aktif bölüm veya renk bulunamadı.")
    else:
        override_week = st.selectbox(
            "Düzeltilecek hafta",
            override_weeks,
            index=0,
            format_func=lambda w: f"{w} — {format_week_human(w)}",
            key="override_week",
        )

        with get_session() as s:
            week_submission_count = s.execute(
                select(func.count(CountSubmission.id)).where(
                    CountSubmission.week_iso == override_week
                )
            ).scalar_one()

        with st.expander("Seçili Haftanın Tüm Sayımlarını Sil", expanded=False):
            st.warning(
                f"Bu işlem **{override_week} — {format_week_human(override_week)}** haftasına ait "
                f"tüm sayım kayıtlarını siler. Silinecek kayıt sayısı: **{week_submission_count}**."
            )
            bulk_confirm = st.text_input(
                "Silmek için ONAYLIYORUM yaz",
                key=f"bulk_delete_confirm_{override_week}",
            )
            bulk_delete_clicked = st.button(
                "Bu Haftadaki Tüm Sayımları Sil",
                key=f"bulk_delete_week_{override_week}",
                use_container_width=True,
                disabled=(week_submission_count == 0 or bulk_confirm != "ONAYLIYORUM"),
            )

            if bulk_delete_clicked:
                try:
                    with get_session() as s:
                        submissions = list(s.execute(
                            select(CountSubmission)
                            .options(selectinload(CountSubmission.details))
                            .where(CountSubmission.week_iso == override_week)
                        ).scalars())

                        old_value = {
                            "week_iso": override_week,
                            "deleted_count": len(submissions),
                            "submission_ids": [sub.id for sub in submissions],
                            "department_ids": [sub.department_id for sub in submissions],
                        }
                        for sub in submissions:
                            s.delete(sub)

                        s.add(AuditLog(
                            user_id=admin_id,
                            action="bulk_submission_delete",
                            entity_type="count_submission",
                            entity_id=None,
                            old_value=old_value,
                            new_value={
                                "week_iso": override_week,
                                "reason": "admin_deleted_entire_week_from_correction_panel",
                            },
                        ))
                    clear_cached_queries()
                    st.success(f"{override_week} haftasındaki {len(submissions)} sayım kaydı silindi.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")

        dept_options = {
            f"{site.name} — {dept.name}": dept.id for dept, site in override_depts
        }
        override_dept_label = st.selectbox(
            "Bölüm",
            list(dept_options.keys()),
            key="override_dept",
        )
        override_dept_id = dept_options[override_dept_label]

        with get_session() as s:
            existing_sub = s.execute(
                select(CountSubmission).where(
                    CountSubmission.department_id == override_dept_id,
                    CountSubmission.week_iso == override_week,
                )
            ).scalar_one_or_none()
            existing_details = {
                detail.color_id: detail
                for detail in (existing_sub.details if existing_sub else [])
            }

        if existing_sub is None:
            st.warning("Bu bölüm/hafta için kayıt yok. Kaydederseniz yeni admin override kaydı oluşur.")
        else:
            st.info(f"Mevcut kayıt durumu: {existing_sub.status}. Kaydetmek eski değerlerin üstüne yazar.")
            if st.button("Bu Sayım Kaydını Sil", key="delete_submission", use_container_width=True):
                try:
                    with get_session() as s:
                        sub = s.execute(
                            select(CountSubmission)
                            .options(selectinload(CountSubmission.details))
                            .where(
                                CountSubmission.department_id == override_dept_id,
                                CountSubmission.week_iso == override_week,
                            )
                        ).scalar_one_or_none()
                        if sub is None:
                            st.info("Silinecek sayım kaydı bulunamadı.")
                        else:
                            old_value = {
                                "week_iso": sub.week_iso,
                                "department_id": sub.department_id,
                                "status": sub.status,
                                "actual_tonnage": float(sub.actual_tonnage) if sub.actual_tonnage else None,
                                "details": {
                                    str(detail.color_id): {
                                        "empty": detail.empty_count,
                                        "full": detail.full_count,
                                        "kanban": detail.kanban_count,
                                    }
                                    for detail in sub.details
                                },
                            }
                            s.delete(sub)
                            s.add(AuditLog(
                                user_id=admin_id,
                                action="admin_submission_delete",
                                entity_type="count_submission",
                                entity_id=sub.id,
                                old_value=old_value,
                                new_value={
                                    "reason": "admin_deleted_from_override_panel",
                                    "week_iso": override_week,
                                    "department_id": override_dept_id,
                                },
                            ))
                    clear_cached_queries()
                    st.success("Sayım kaydı silindi.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")

        with st.form("admin_override_form"):
            override_tonnage = st.number_input(
                "Gerçekleşen tonaj (ton)",
                min_value=0.0,
                value=float(existing_sub.actual_tonnage) if existing_sub and existing_sub.actual_tonnage else 0.0,
                step=0.1,
                format="%.2f",
            )
            override_reason = st.text_area(
                "Düzeltme nedeni",
                placeholder="Örn. kullanıcı yanlış renk sayısı girdi",
            )

            h1, h2, h3, h4 = st.columns([2, 1, 1, 1])
            h1.markdown("**Renk**")
            h2.markdown("**Boş**")
            h3.markdown("**Dolu**")
            h4.markdown("**Kanban**")

            override_counts: dict[int, dict[str, int]] = {}
            for color in override_colors:
                previous = existing_details.get(color.id)
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                c1.write(color.name)
                empty_value = c2.number_input(
                    f"override_empty_{color.id}",
                    min_value=0,
                    value=previous.empty_count if previous else 0,
                    step=1,
                    label_visibility="collapsed",
                )
                full_value = c3.number_input(
                    f"override_full_{color.id}",
                    min_value=0,
                    value=previous.full_count if previous else 0,
                    step=1,
                    label_visibility="collapsed",
                )
                kanban_value = c4.number_input(
                    f"override_kanban_{color.id}",
                    min_value=0,
                    value=previous.kanban_count if previous else 0,
                    step=1,
                    label_visibility="collapsed",
                )
                override_counts[color.id] = {
                    "empty": int(empty_value),
                    "full": int(full_value),
                    "kanban": int(kanban_value),
                }

            override_clicked = st.form_submit_button(
                "Düzeltmeyi Kaydet",
                use_container_width=True,
                type="primary",
            )

        if override_clicked:
            errors = []
            for color in override_colors:
                values = override_counts[color.id]
                if values["kanban"] > values["full"]:
                    errors.append(
                        f"{color.name}: kanban ({values['kanban']}) dolu ({values['full']}) değerinden büyük olamaz."
                    )

            if errors:
                for error in errors:
                    st.error(error)
            elif not override_reason.strip():
                st.error("Düzeltme nedeni zorunlu.")
            else:
                try:
                    with get_session() as s:
                        sub = s.execute(
                            select(CountSubmission).where(
                                CountSubmission.department_id == override_dept_id,
                                CountSubmission.week_iso == override_week,
                            )
                        ).scalar_one_or_none()

                        old_value = None
                        if sub is not None:
                            old_value = {
                                "status": sub.status,
                                "actual_tonnage": float(sub.actual_tonnage) if sub.actual_tonnage else None,
                                "details": {
                                    str(detail.color_id): {
                                        "empty": detail.empty_count,
                                        "full": detail.full_count,
                                        "kanban": detail.kanban_count,
                                    }
                                    for detail in sub.details
                                },
                            }
                            for detail in list(sub.details):
                                s.delete(detail)
                            s.flush()
                        else:
                            now_value = now_tr()
                            sub = CountSubmission(
                                department_id=override_dept_id,
                                user_id=admin_id,
                                week_iso=override_week,
                                count_date=now_value.date(),
                                count_time=now_value.time().replace(microsecond=0),
                                status="submitted",
                                submitted_at=now_value,
                            )
                            s.add(sub)
                            s.flush()

                        sub.user_id = admin_id
                        sub.actual_tonnage = Decimal(str(override_tonnage))
                        sub.status = "submitted"
                        sub.submitted_at = now_tr()

                        for color_id, values in override_counts.items():
                            s.add(CountDetail(
                                submission_id=sub.id,
                                color_id=color_id,
                                empty_count=values["empty"],
                                full_count=values["full"],
                                kanban_count=values["kanban"],
                            ))

                        s.add(AuditLog(
                            user_id=admin_id,
                            action="admin_override",
                            entity_type="count_submission",
                            entity_id=sub.id,
                            old_value=old_value,
                            new_value={
                                "week_iso": override_week,
                                "department_id": override_dept_id,
                                "status": "submitted",
                                "actual_tonnage": float(override_tonnage),
                                "reason": override_reason.strip(),
                                "details": {
                                    str(color_id): values
                                    for color_id, values in override_counts.items()
                                },
                            },
                        ))
                    clear_cached_queries()
                    st.success("Admin override kaydedildi.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")

timer.finish()
