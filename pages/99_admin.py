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

import pandas as pd
import streamlit as st
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased, selectinload

from db.connection import get_session
from db.models import (
    AuditLog,
    Color,
    CountDetail,
    CountSubmission,
    Department,
    LateUserWindowOverride,
    LateWindowOverride,
    ProductionSite,
    SubmissionSchedule,
    User,
    UserDepartment,
)
from config.settings import get_settings
from utils.auth import hash_password, require_admin, restore_session_from_query
from utils.cached_queries import (
    clear_cached_queries,
    get_active_department_count,
    get_all_weeks_export_rows,
    get_week_export_rows,
)
from utils.excel_export import build_all_weeks_excel, build_week_excel
from utils.performance import page_timer
from utils.ui import (
    flush_pending_toasts,
    inject_css,
    page_header,
    queue_toast,
    render_sidebar_user,
)
from utils.week import (
    DEFAULT_SCHEDULE,
    current_week_iso,
    format_week_human,
    format_schedule_human,
    load_schedule,
    now_tr,
    week_iso_from_date,
    weekday_name_tr,
)


inject_css()
restore_session_from_query()
flush_pending_toasts()
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

# Test Sıfırlama sekmesi her zaman görünür — destructive aksiyon iki onaylı
# (ONAYLIYORUM yazma + checkbox), bu yüzden ayrıca env-gate'e ihtiyacımız yok.
_settings = get_settings()

# st.tabs Streamlit reruns sonrası ilk sekmeye dönüyor; selectbox/form
# etkileşimleri kullanıcıyı her seferinde Kullanıcılar sekmesine atıyordu.
# session_state'e bağlı bir radio ile sticky bir sekme yapısı kuruyoruz.
_TAB_KEYS = [
    ("users",        "Kullanıcılar"),
    ("perms",        "Yetkilendirme"),
    ("departments",  "Bölümler"),
    ("colors",       "Renkler"),
    ("schedule",     "Sayım Takvimi"),
    ("late",         "Geç Giriş"),
    ("override",     "Sayım Düzeltme"),
    ("audit",        "İşlem Geçmişi"),
    ("test_reset",   "⚠ Test Sıfırlama"),
]
_TAB_LABELS = [label for _, label in _TAB_KEYS]
_active_label = st.radio(
    "Sekme",
    _TAB_LABELS,
    horizontal=True,
    label_visibility="collapsed",
    key="admin_tab",
)
_active_key = next(k for k, label in _TAB_KEYS if label == _active_label)


def _is_active(key: str) -> bool:
    return _active_key == key


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
if _is_active("users"):
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
                        st.toast(f"'{new_username}' oluşturuldu.", icon="✅")
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
                update_ok = False
                update_error: str | None = None
                updated_username = clean_username
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
                            update_error = f"'{clean_username}' kullanıcı adı zaten alınmış."
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

                            updated_username = target.username
                            update_ok = True
                except Exception as exc:
                    update_error = f"Hata: {exc}"

                if update_ok:
                    clear_cached_queries()
                    if selected_user_id == admin_id:
                        st.session_state["username"] = updated_username
                        st.session_state["role"] = edit_role
                        st.session_state["full_name"] = clean_full_name
                    # Clear cached widget state for this user's edit form
                    # so Streamlit picks up the new DB values on the next
                    # render (otherwise session_state shadows `value=`).
                    for stale_key in (
                        f"{user_form_key}_username",
                        f"{user_form_key}_full_name",
                        f"{user_form_key}_email",
                        f"{user_form_key}_role",
                        f"{user_form_key}_active",
                        f"{user_form_key}_password",
                    ):
                        st.session_state.pop(stale_key, None)
                    queue_toast(f"'{updated_username}' güncellendi.", icon="✅")
                    st.rerun()
                elif update_error:
                    st.error(update_error)


# ---------------------------------------------------------------------------
# TAB 6 — RENKLER
# ---------------------------------------------------------------------------
if _is_active("colors"):
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
                st.toast(f"'{clean_name}' rengi eklendi.", icon="✅")
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
                    st.toast("Renk güncellendi.", icon="✅")
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
                    st.toast("Renk pasifleştirildi.", icon="✅")
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
if _is_active("audit"):
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

if _is_active("users"):
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
                    st.toast(f"'{selected_user.username}' pasifleştirildi.", icon="✅")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")


# ---------------------------------------------------------------------------
# TAB 5 — BÖLÜMLER
# ---------------------------------------------------------------------------
if _is_active("departments"):
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
                    st.toast(f"'{clean_name}' bölümü eklendi.", icon="✅")
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
                        st.toast("Bölüm güncellendi.", icon="✅")
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
                    st.toast("Bölüm pasifleştirildi.", icon="✅")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")

if _is_active("users"):
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
if _is_active("perms"):
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
                    # Clear stale checkbox state so the next render reads
                    # fresh DB-derived values via `value=`.
                    for dept, _site in all_depts:
                        st.session_state.pop(f"perm_{selected_user_id}_{dept.id}", None)
                    queue_toast(
                        f"Güncellendi: +{len(to_add)} eklendi, -{len(to_remove)} kaldırıldı.",
                        icon="✅",
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")


# ---------------------------------------------------------------------------
# TAB — SAYIM TAKVİMİ (admin-konfigüre edilebilir pencere)
# ---------------------------------------------------------------------------
if _is_active("schedule"):
    st.subheader("Sayım Takvimi")
    st.caption(
        "Haftanın hangi günü ve saat aralığında sayım girişinin açık "
        "olacağını buradan yönetin. Değişiklik anında geçerli olur — "
        "tüm kullanıcılar yeni günde/saatte veri girebilir."
    )

    with get_session() as _s:
        current_schedule = load_schedule(_s)
    cur_day, cur_open, cur_close = current_schedule

    st.info(f"**Aktif takvim:** {format_schedule_human(current_schedule)}")

    weekday_options = list(range(1, 8))  # 1=Mon..7=Sun
    hour_options = list(range(24))

    with st.form("schedule_form"):
        sc_day = st.selectbox(
            "Gün",
            weekday_options,
            index=weekday_options.index(cur_day),
            format_func=weekday_name_tr,
            key="schedule_day",
        )
        col_open, col_close = st.columns(2)
        sc_open = col_open.selectbox(
            "Açılış saati",
            hour_options,
            index=cur_open,
            format_func=lambda h: f"{h:02d}:00",
            key="schedule_open",
        )
        sc_close = col_close.selectbox(
            "Kapanış saati",
            list(range(1, 25)),
            index=max(cur_close - 1, 0),
            format_func=lambda h: f"{h:02d}:00",
            key="schedule_close",
        )
        save_schedule_clicked = st.form_submit_button(
            "Takvimi Güncelle", use_container_width=True, type="primary",
        )

    if save_schedule_clicked:
        if sc_close <= sc_open:
            st.error("Kapanış saati açılış saatinden büyük olmalı.")
        elif (sc_day, sc_open, sc_close) == (cur_day, cur_open, cur_close):
            queue_toast("Değişiklik yapılmadı — değerler zaten kayıtlı.", icon="ℹ️")
            st.rerun()
        else:
            try:
                with get_session() as s:
                    row = s.execute(
                        select(SubmissionSchedule).where(SubmissionSchedule.id == 1)
                    ).scalar_one_or_none()
                    old_value = (
                        {
                            "day_of_week": row.day_of_week,
                            "open_hour": row.open_hour,
                            "close_hour": row.close_hour,
                        }
                        if row is not None
                        else {
                            "day_of_week": DEFAULT_SCHEDULE[0],
                            "open_hour": DEFAULT_SCHEDULE[1],
                            "close_hour": DEFAULT_SCHEDULE[2],
                        }
                    )
                    if row is None:
                        row = SubmissionSchedule(
                            id=1,
                            day_of_week=int(sc_day),
                            open_hour=int(sc_open),
                            close_hour=int(sc_close),
                            updated_by=admin_id,
                        )
                        s.add(row)
                    else:
                        row.day_of_week = int(sc_day)
                        row.open_hour = int(sc_open)
                        row.close_hour = int(sc_close)
                        row.updated_by = admin_id
                    s.add(AuditLog(
                        user_id=admin_id,
                        action="schedule_update",
                        entity_type="submission_schedule",
                        entity_id=1,
                        old_value=old_value,
                        new_value={
                            "day_of_week": int(sc_day),
                            "open_hour": int(sc_open),
                            "close_hour": int(sc_close),
                        },
                    ))
                clear_cached_queries()
                queue_toast(
                    f"Takvim güncellendi: {format_schedule_human((int(sc_day), int(sc_open), int(sc_close)))}",
                    icon="✅",
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Hata: {exc}")


# ---------------------------------------------------------------------------
# TAB 3 — GEÇ GİRİŞ PENCERESİ
# ---------------------------------------------------------------------------
if _is_active("late"):
    st.subheader("Geç Giriş Penceresi")
    st.caption("Kapanmış bir hafta için hafta geneli veya kullanıcı özelinde sayım girişi açar.")

    with get_session() as s:
        known_weeks = list(s.execute(
            select(CountSubmission.week_iso)
            .distinct()
            .order_by(CountSubmission.week_iso.desc())
        ).scalars())
        late_users = list(s.execute(
            select(User)
            .where(User.is_active.is_(True))
            .order_by(User.full_name)
        ).scalars())
        user_departments_for_late = list(s.execute(
            select(UserDepartment.user_id, Department, ProductionSite)
            .join(Department, Department.id == UserDepartment.department_id)
            .join(ProductionSite, ProductionSite.id == Department.production_site_id)
            .where(Department.is_active.is_(True))
            .order_by(ProductionSite.name, Department.name)
        ).all())

    current_week = current_week_iso()
    known_weeks = _merge_week_options(_recent_week_options(12), known_weeks)

    default_closes_at = now_tr() + timedelta(hours=1)
    late_scope = st.radio(
        "İzin kapsamı",
        ["Kullanıcı özel", "Hafta geneli"],
        horizontal=True,
        help="Kullanıcı özel izin yalnızca seçilen kullanıcıya açılır. Hafta geneli izin o haftadaki yetkili tüm kullanıcıları kapsar.",
    )

    selected_late_user_id = None
    selected_late_department_id = None
    if late_scope == "Kullanıcı özel":
        if not late_users:
            st.info("Aktif kullanıcı bulunamadı.")
            st.stop()
        selected_late_user_id = st.selectbox(
            "Kullanıcı",
            [user.id for user in late_users],
            format_func=lambda user_id: _user_label(next(user for user in late_users if user.id == user_id)),
            key="late_user_select",
        )
        dept_options_for_user = [
            (dept, site)
            for user_id, dept, site in user_departments_for_late
            if user_id == selected_late_user_id
        ]
        dept_scope_options = [0] + [dept.id for dept, _site in dept_options_for_user]
        selected_late_department_id = st.selectbox(
            "Bölüm kapsamı",
            dept_scope_options,
            format_func=lambda dept_id: (
                "Yetkili olduğu tüm bölümler"
                if dept_id == 0 else
                next(
                    f"{site.name} — {dept.name}"
                    for dept, site in dept_options_for_user
                    if dept.id == dept_id
                )
            ),
            key="late_department_scope",
        )
        if selected_late_department_id == 0:
            selected_late_department_id = None

    with st.form("late_window_form"):
        selected_week = st.selectbox(
            "Hafta",
            known_weeks,
            index=0,
            format_func=lambda w: f"{w} — {format_week_human(w)}",
        )
        col_date, col_time = st.columns(2)
        closes_date = col_date.date_input("Kapanış tarihi", value=default_closes_at.date())
        closes_time = col_time.time_input("Kapanış saati", value=default_closes_at.time().replace(microsecond=0))
        reason = st.text_area("Açıklama", placeholder="Örn. bölüm sayımı zamanında tamamlanamadı")
        open_clicked = st.form_submit_button("Pencereyi Aç / Güncelle", use_container_width=True)

    if open_clicked:
        closes_at = now_tr(datetime.combine(closes_date, closes_time))
        current_time = now_tr()
        if closes_at <= current_time:
            st.error(
                "Kapanış zamanı şu andan ileri olmalı. "
                f"Seçilen: {closes_at:%Y-%m-%d %H:%M}, şu an: {current_time:%Y-%m-%d %H:%M}."
            )
        else:
            try:
                with get_session() as s:
                    old_value = None
                    if late_scope == "Hafta geneli":
                        existing = s.get(LateWindowOverride, selected_week)
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

                        audit_action = "late_window_open"
                        audit_entity = "late_window_override"
                        audit_new_value = {
                            "scope": "week",
                            "week_iso": selected_week,
                            "closes_at": closes_at.isoformat(),
                            "reason": reason.strip() or None,
                        }
                    else:
                        existing = s.execute(
                            select(LateUserWindowOverride).where(
                                LateUserWindowOverride.week_iso == selected_week,
                                LateUserWindowOverride.user_id == selected_late_user_id,
                                (
                                    LateUserWindowOverride.department_id.is_(None)
                                    if selected_late_department_id is None else
                                    LateUserWindowOverride.department_id == selected_late_department_id
                                ),
                            )
                        ).scalar_one_or_none()
                        if existing is None:
                            override = LateUserWindowOverride(
                                week_iso=selected_week,
                                user_id=selected_late_user_id,
                                department_id=selected_late_department_id,
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

                        audit_action = "late_user_window_open"
                        audit_entity = "late_user_window_override"
                        audit_new_value = {
                            "scope": "user",
                            "week_iso": selected_week,
                            "user_id": selected_late_user_id,
                            "department_id": selected_late_department_id,
                            "closes_at": closes_at.isoformat(),
                            "reason": reason.strip() or None,
                        }

                    s.add(AuditLog(
                        user_id=admin_id,
                        action=audit_action,
                        entity_type=audit_entity,
                        entity_id=None,
                        old_value=old_value,
                        new_value=audit_new_value,
                    ))
                clear_cached_queries()
                if late_scope == "Hafta geneli":
                    st.toast(f"{selected_week} için hafta geneli geç giriş penceresi açıldı.", icon="✅")
                else:
                    st.toast(f"{selected_week} için kullanıcı özel geç giriş izni açıldı.", icon="✅")
                st.rerun()
            except Exception as exc:
                st.error(f"Hata: {exc}")

    st.divider()
    st.subheader("Açık / Geçmiş Pencereler")

    with get_session() as s:
        target_user_alias = aliased(User)
        opened_by_alias = aliased(User)
        overrides = list(s.execute(
            select(LateWindowOverride, User)
            .join(User, User.id == LateWindowOverride.opened_by)
            .order_by(LateWindowOverride.closes_at.desc())
        ).all())
        try:
            user_overrides = list(s.execute(
                select(LateUserWindowOverride, target_user_alias, opened_by_alias, Department, ProductionSite)
                .join(target_user_alias, target_user_alias.id == LateUserWindowOverride.user_id)
                .join(opened_by_alias, opened_by_alias.id == LateUserWindowOverride.opened_by)
                .outerjoin(Department, Department.id == LateUserWindowOverride.department_id)
                .outerjoin(ProductionSite, ProductionSite.id == Department.production_site_id)
                .order_by(LateUserWindowOverride.closes_at.desc())
            ).all())
        except SQLAlchemyError:
            user_overrides = []
            st.warning(
                "Kullanıcı özel geç giriş tablosu henüz veritabanında yok. "
                "sql/migrations/2026-05-05_late_user_window_overrides.sql dosyasındaki SQL'i Supabase'de çalıştırın."
            )

    if not overrides and not user_overrides:
        st.info("Henüz geç giriş penceresi yok.")
    else:
        rows = []
        current_time = now_tr()
        for override, opened_by in overrides:
            rows.append({
                "Kapsam": "Hafta geneli",
                "Hafta": override.week_iso,
                "Tarih Aralığı": format_week_human(override.week_iso),
                "Kullanıcı": "Tüm yetkili kullanıcılar",
                "Bölüm": "Tüm yetkili bölümler",
                "Durum": "Açık" if now_tr(override.closes_at) > current_time else "Kapandı",
                "Kapanış": now_tr(override.closes_at).strftime("%Y-%m-%d %H:%M"),
                "Açan": opened_by.full_name,
                "Açıklama": override.reason or "-",
            })
        for override, target_user, opened_by, dept, site in user_overrides:
            rows.append({
                "Kapsam": "Kullanıcı özel",
                "Hafta": override.week_iso,
                "Tarih Aralığı": format_week_human(override.week_iso),
                "Kullanıcı": target_user.full_name,
                "Bölüm": (
                    "Tüm yetkili bölümler"
                    if dept is None else
                    f"{site.name if site else '-'} — {dept.name}"
                ),
                "Durum": "Açık" if now_tr(override.closes_at) > current_time else "Kapandı",
                "Kapanış": now_tr(override.closes_at).strftime("%Y-%m-%d %H:%M"),
                "Açan": opened_by.full_name,
                "Açıklama": override.reason or "-",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# TAB 6 — SAYIM DÜZELTME
# ---------------------------------------------------------------------------
if _is_active("override"):
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
            late_submission_count = s.execute(
                select(func.count(CountSubmission.id)).where(
                    CountSubmission.week_iso == override_week,
                    CountSubmission.status == "late_submitted",
                )
            ).scalar_one()

        active_department_count = get_active_department_count()
        missing_department_count = max(active_department_count - week_submission_count, 0)
        completion_pct = (
            week_submission_count / active_department_count * 100
            if active_department_count else 0
        )
        export_rows = get_week_export_rows(override_week)

        st.markdown("#### Seçili Hafta Özeti")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Giren Bölüm", f"{week_submission_count} / {active_department_count}")
        m2.metric("Eksik Bölüm", missing_department_count)
        m3.metric("Tamamlanma", f"%{completion_pct:.0f}")
        m4.metric("Geç Girilen", late_submission_count)

        export_col1, export_col2 = st.columns(2)

        if export_rows:
            xlsx_bytes = build_week_excel(
                export_rows, override_week, format_week_human(override_week)
            )
            export_col1.download_button(
                "Seçili Haftayı Excel İndir",
                data=xlsx_bytes,
                file_name=f"sayim_export_{override_week}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        else:
            export_col1.info("Seçili hafta için indirilecek sayım kaydı yok.")

        # Tüm haftaların verisi tek bir long-format Excel — pivot için.
        all_weeks_rows = get_all_weeks_export_rows()
        if all_weeks_rows:
            today_str = now_tr().strftime("%Y-%m-%d")
            all_xlsx_bytes = build_all_weeks_excel(all_weeks_rows)
            export_col2.download_button(
                f"Tüm Haftaları Excel İndir ({len(all_weeks_rows)} satır)",
                data=all_xlsx_bytes,
                file_name=f"sayim_export_tum_haftalar_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                help="Tüm haftalardaki sayım kayıtlarını tek bir Excel dosyasında long-format (pivot için uygun) olarak indirir.",
            )
        else:
            export_col2.info("Henüz hiç sayım kaydı yok — tüm haftalar export'u boş olur.")

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
                    st.toast(f"{override_week} haftasındaki {len(submissions)} sayım kaydı silindi.", icon="✅")
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
                                        "scrap": detail.scrap_count,
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
                    st.toast("Sayım kaydı silindi.", icon="✅")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")

        # Widget keys must change when (week, department) changes — see
        # the same fix in pages/01_sayim_girisi.py for full reasoning.
        override_scope = f"{override_dept_id}_{override_week}"

        with st.form(f"admin_override_form_{override_scope}"):
            override_tonnage = st.number_input(
                "Gerçekleşen tonaj (ton)",
                min_value=0.0,
                value=float(existing_sub.actual_tonnage) if existing_sub and existing_sub.actual_tonnage else 0.0,
                step=0.1,
                format="%.2f",
                key=f"override_tonnage_{override_scope}",
            )
            override_reason = st.text_area(
                "Düzeltme nedeni",
                placeholder="Örn. kullanıcı yanlış renk sayısı girdi",
                key=f"override_reason_{override_scope}",
            )

            h1, h2, h3, h4, h5 = st.columns([2, 1, 1, 1, 1])
            h1.markdown("**Renk**")
            h2.markdown("**Boş**")
            h3.markdown("**Dolu**")
            h4.markdown("**Kanban**")
            h5.markdown("**Hurda**")

            override_counts: dict[int, dict[str, int]] = {}
            for color in override_colors:
                previous = existing_details.get(color.id)
                c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
                c1.write(color.name)
                empty_value = c2.number_input(
                    f"{color.name} — Boş",
                    key=f"override_empty_{override_scope}_{color.id}",
                    min_value=0,
                    value=previous.empty_count if previous else 0,
                    step=1,
                    label_visibility="collapsed",
                )
                full_value = c3.number_input(
                    f"{color.name} — Dolu",
                    key=f"override_full_{override_scope}_{color.id}",
                    min_value=0,
                    value=previous.full_count if previous else 0,
                    step=1,
                    label_visibility="collapsed",
                )
                kanban_value = c4.number_input(
                    f"{color.name} — Kanban",
                    key=f"override_kanban_{override_scope}_{color.id}",
                    min_value=0,
                    value=previous.kanban_count if previous else 0,
                    step=1,
                    label_visibility="collapsed",
                )
                scrap_value = c5.number_input(
                    f"{color.name} — Hurda",
                    key=f"override_scrap_{override_scope}_{color.id}",
                    min_value=0,
                    value=previous.scrap_count if previous else 0,
                    step=1,
                    label_visibility="collapsed",
                )
                override_counts[color.id] = {
                    "empty": int(empty_value),
                    "full": int(full_value),
                    "kanban": int(kanban_value),
                    "scrap": int(scrap_value),
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
                        # Eski kaydı SELECT FOR UPDATE ile kilitle —
                        # admin override ile kullanıcı submit'i çakışırsa
                        # yarış koşulu olmasın.
                        sub = s.execute(
                            select(CountSubmission)
                            .where(
                                CountSubmission.department_id == override_dept_id,
                                CountSubmission.week_iso == override_week,
                            )
                            .with_for_update()
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
                                        "scrap": detail.scrap_count,
                                    }
                                    for detail in sub.details
                                },
                            }

                        now_value = now_tr()
                        new_tonnage_dec = Decimal(str(override_tonnage)).quantize(Decimal("0.01"))

                        # PostgreSQL native UPSERT — atomik, race-free.
                        sub_stmt = (
                            pg_insert(CountSubmission.__table__)
                            .values(
                                department_id=override_dept_id,
                                user_id=admin_id,
                                week_iso=override_week,
                                count_date=now_value.date(),
                                count_time=now_value.time().replace(microsecond=0),
                                actual_tonnage=new_tonnage_dec,
                                status="submitted",
                                submitted_at=now_value,
                            )
                            .on_conflict_do_update(
                                index_elements=["department_id", "week_iso"],
                                set_={
                                    "user_id": admin_id,
                                    "actual_tonnage": new_tonnage_dec,
                                    "status": "submitted",
                                    "submitted_at": now_value,
                                },
                            )
                            .returning(CountSubmission.__table__.c.id)
                        )
                        sub_id = s.execute(sub_stmt).scalar_one()

                        # Detayları replace et — atomik transaction içinde.
                        s.execute(
                            delete(CountDetail).where(CountDetail.submission_id == sub_id)
                        )
                        s.execute(
                            CountDetail.__table__.insert(),
                            [
                                {
                                    "submission_id": sub_id,
                                    "color_id": color_id,
                                    "empty_count": values["empty"],
                                    "full_count": values["full"],
                                    "kanban_count": values["kanban"],
                                    "scrap_count": values["scrap"],
                                }
                                for color_id, values in override_counts.items()
                            ],
                        )

                        s.add(AuditLog(
                            user_id=admin_id,
                            action="admin_override",
                            entity_type="count_submission",
                            entity_id=sub_id,
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
                    queue_toast("Admin override kaydedildi.", icon="✅")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")


# ---------------------------------------------------------------------------
# TAB 8 — TEST VERİSİ SIFIRLAMA
# ---------------------------------------------------------------------------
if _is_active("test_reset"):
    st.subheader("Test Verisini Sıfırla")
    st.caption(
        "Test sırasında üretilen sayım kayıtlarını ve transactional audit "
        "log'u kalıcı olarak siler. Master data (kullanıcılar, bölümler, "
        "renkler) korunur. İki aşamalı onay gerekiyor."
    )
    st.warning(
        "Bu işlem **tüm sayım kayıtlarını, sayım detaylarını, geç giriş "
        "pencerelerini ve transactional audit log girdilerini kalıcı "
        "olarak siler.** Master data (kullanıcılar, bölümler, renkler, "
        "üretim yerleri) korunur."
    )

    # Önce kullanıcıya silinecekleri özetle
    with get_session() as s:
        n_subs = s.execute(select(func.count(CountSubmission.id))).scalar_one()
        n_details = s.execute(select(func.count(CountDetail.id))).scalar_one()
        n_late = s.execute(select(func.count(LateWindowOverride.week_iso))).scalar_one()
        n_late_user = s.execute(select(func.count(LateUserWindowOverride.id))).scalar_one()
        n_audit_tx = s.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.action.in_([
                    # Sayım yaşam döngüsü
                    "count_submit", "count_update",
                    "admin_submission_delete", "bulk_submission_delete",
                    "admin_override",
                    # Geç giriş yönetimi
                    "late_window_open", "late_window_close",
                    "late_user_window_open", "late_user_window_close",
                    # Oturum
                    "login_success", "login_failed", "logout",
                ])
            )
        ).scalar_one()
        n_users = s.execute(select(func.count(User.id))).scalar_one()
        n_depts = s.execute(select(func.count(Department.id))).scalar_one()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sayım Kayıtları", n_subs)
    c2.metric("Sayım Detayları", n_details)
    c3.metric("Geç Giriş Pencereleri", n_late + n_late_user)
    c4.metric("Audit (transactional)", n_audit_tx)

    st.markdown(
        f"<small style='color:var(--text-muted);'>Korunacak: "
        f"<b>{n_users}</b> kullanıcı, <b>{n_depts}</b> bölüm, "
        f"6 renk, 11 üretim yeri.</small>",
        unsafe_allow_html=True,
    )

    st.divider()

    # Onay zinciri: ONAYLIYORUM yaz + checkbox + buton
    confirm_text = st.text_input(
        "Silmek için ONAYLIYORUM yaz",
        key="test_reset_confirm_text",
        placeholder="ONAYLIYORUM",
    )
    confirm_check = st.checkbox(
        "Master data'nın korunacağını ve geri dönüşü olmadığını anladım.",
        key="test_reset_confirm_check",
    )
    do_wipe = st.button(
        "TÜM TEST VERİSİNİ KALICI OLARAK SİL",
        key="test_reset_button",
        use_container_width=True,
        type="primary",
        disabled=(confirm_text != "ONAYLIYORUM") or (not confirm_check),
    )

    if do_wipe:
        try:
            with get_session() as s:
                # Sayım detaylarını CASCADE ile siliyoruz
                deleted_details = s.execute(
                    CountDetail.__table__.delete()
                ).rowcount
                deleted_subs = s.execute(
                    CountSubmission.__table__.delete()
                ).rowcount
                deleted_late = s.execute(
                    LateWindowOverride.__table__.delete()
                ).rowcount
                deleted_late_user = s.execute(
                    LateUserWindowOverride.__table__.delete()
                ).rowcount
                deleted_audit = s.execute(
                    AuditLog.__table__.delete().where(
                        AuditLog.action.in_([
                            "count_submit", "count_update", "count_delete",
                            "count_admin_override", "count_bulk_delete",
                            "late_window_open", "late_window_close",
                            "late_user_window_open", "late_user_window_close",
                            "login_success", "login_failed", "logout",
                        ])
                    )
                ).rowcount
                # Sıfırlama işleminin kendisini audit log'a yaz (kalıcı).
                s.add(AuditLog(
                    user_id=admin_id,
                    action="test_data_wipe",
                    entity_type="system",
                    new_value={
                        "deleted_submissions": deleted_subs,
                        "deleted_details": deleted_details,
                        "deleted_late_overrides": deleted_late + deleted_late_user,
                        "deleted_audit_rows": deleted_audit,
                        "app_env": _settings.app_env,
                    },
                ))
            clear_cached_queries()
            st.toast(
                f"Sıfırlama tamam. Silinen: {deleted_subs} sayım, "
                f"{deleted_details} detay, {deleted_late + deleted_late_user} "
                f"geç giriş penceresi, {deleted_audit} audit satırı.",
                icon="✅",
            )
        except Exception as exc:
            st.error(f"Hata: {exc}")


timer.finish()
