"""
Admin paneli — kullanıcı CRUD + bölüm yetkilendirme.

Sekmeler:
  1. Kullanıcılar:   yeni kullanıcı oluştur, listele, aktif/pasif yap
  2. Yetkilendirme:  bir kullanıcıya bölüm atama (çoka çok)

Tüm değişiklikler audit_log'a yazılır.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import streamlit as st
from sqlalchemy import select
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
from utils.ui import inject_css, page_header, render_sidebar_user
from utils.week import current_week_iso, format_week_human, now_tr


inject_css()
restore_session_from_cookie()

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
    )

tab_users, tab_perms, tab_late, tab_override = st.tabs([
    "Kullanıcılar",
    "Yetkilendirme",
    "Geç Giriş",
    "Sayım Override",
])


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
                        st.success(f"'{new_username}' oluşturuldu.")
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
    if current_week not in known_weeks:
        known_weeks = [current_week] + known_weeks

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
# TAB 4 — SAYIM OVERRIDE
# ---------------------------------------------------------------------------
with tab_override:
    st.subheader("Sayım Override")
    st.caption("Pencere kapandıktan sonra hatalı sayımı yönetici olarak düzelt.")

    with get_session() as s:
        override_weeks = list(s.execute(
            select(CountSubmission.week_iso)
            .distinct()
            .order_by(CountSubmission.week_iso.desc())
        ).scalars())
        if current_week_iso() not in override_weeks:
            override_weeks = [current_week_iso()] + override_weeks

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
            "Override haftası",
            override_weeks,
            index=0,
            format_func=lambda w: f"{w} — {format_week_human(w)}",
            key="override_week",
        )
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
                "Override Kaydet",
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
                    st.success("Admin override kaydedildi.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hata: {exc}")
