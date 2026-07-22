"""
Üretim yeri × haftalık tonaj hedefleri — CRUD helpers.

Hedefler dönemsel (3 ayda bir tipik) güncellenir; her kayıt bir
[effective_from, effective_to] aralığında geçerlidir. Bir haftanın
hedefi, o haftanın Pazartesi'sini kapsayan kayıtın değeridir.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from db.models import ProductionSite, SiteTonnageTarget
from utils.week import week_iso_to_dates


def list_all_targets(session: Session) -> list[SiteTonnageTarget]:
    """Tüm hedef kayıtları — site_id, effective_from DESC sıralı."""
    stmt = (
        select(SiteTonnageTarget)
        .order_by(
            SiteTonnageTarget.production_site_id,
            SiteTonnageTarget.effective_from.desc(),
        )
    )
    return list(session.scalars(stmt))


def get_active_target(
    session: Session, site_id: int, on_date: date,
) -> Optional[SiteTonnageTarget]:
    """Belirtilen tarih için sitenin geçerli hedefi (yoksa None)."""
    stmt = select(SiteTonnageTarget).where(
        SiteTonnageTarget.production_site_id == site_id,
        SiteTonnageTarget.effective_from <= on_date,
        or_(
            SiteTonnageTarget.effective_to.is_(None),
            SiteTonnageTarget.effective_to >= on_date,
        ),
    ).order_by(SiteTonnageTarget.effective_from.desc()).limit(1)
    return session.scalars(stmt).first()


def get_weekly_targets_for_week(
    session: Session, week_iso: str,
) -> dict[int, Decimal]:
    """{site_id: hedef_ton} — bu haftanın Pazartesi'sinde geçerli hedefler.

    Aynı site için birden fazla aralık kapsıyorsa (veri hatası) en yeni
    ``effective_from``'lu kayıt geçerli.
    """
    monday, _ = week_iso_to_dates(week_iso)
    stmt = (
        select(SiteTonnageTarget)
        .where(
            SiteTonnageTarget.effective_from <= monday,
            or_(
                SiteTonnageTarget.effective_to.is_(None),
                SiteTonnageTarget.effective_to >= monday,
            ),
        )
        .order_by(SiteTonnageTarget.effective_from.asc())
    )
    # ASC iterasyon: aynı site tekrar gelirse üstüne yazılır → en yenisi kalır.
    result: dict[int, Decimal] = {}
    for row in session.scalars(stmt):
        result[row.production_site_id] = row.weekly_target_ton
    return result


def latest_targets_by_site(session: Session) -> dict[int, SiteTonnageTarget]:
    """Her site için en son (effective_from en büyük) hedef kaydı."""
    all_rows = list_all_targets(session)
    latest: dict[int, SiteTonnageTarget] = {}
    for row in all_rows:
        prev = latest.get(row.production_site_id)
        if prev is None or row.effective_from > prev.effective_from:
            latest[row.production_site_id] = row
    return latest


def create_new_period(
    session: Session,
    effective_from: date,
    targets_by_site_id: dict[int, Decimal],
    created_by: int,
) -> list[SiteTonnageTarget]:
    """Yeni dönem başlat: verilen tarihten itibaren siteler için hedefler
    yazılır.

    Geçmişe dönük veya out-of-order girişi de destekler:
      • Önceki dönem (``effective_from < new_from``) kapsıyor mu (açık uçlu
        veya ``effective_to >= new_from``)? → önceki dönemin
        ``effective_to`` bunu ``new_from - 1``'e çekilir.
      • Sonraki dönem (``effective_from > new_from``) var mı? → yeni
        kaydın ``effective_to``, o en yakın sonraki dönemin
        ``effective_from - 1``'ine set edilir (yoksa NULL — açık uçlu).

    Aynı (site, effective_from) daha önce yazıldıysa hata verir
    (UniqueConstraint). Bu davranış istenerek — kullanıcı önce eski
    kaydı düzeltmeli / silmeli.
    """
    if effective_from is None:
        raise ValueError("effective_from gerekli")
    if not targets_by_site_id:
        raise ValueError("En az bir site hedefi verilmeli")

    from datetime import timedelta
    prev_close_date = effective_from - timedelta(days=1)

    site_ids = list(targets_by_site_id.keys())

    # 1) Önceki dönemleri kapat (yeni_from < mevcut kapsam ise)
    prev_stmt = select(SiteTonnageTarget).where(
        SiteTonnageTarget.production_site_id.in_(site_ids),
        SiteTonnageTarget.effective_from < effective_from,
        or_(
            SiteTonnageTarget.effective_to.is_(None),
            SiteTonnageTarget.effective_to >= effective_from,
        ),
    )
    for row in session.scalars(prev_stmt):
        row.effective_to = prev_close_date

    # 2) Her site için sonraki dönemin başlangıcını bul (yeni kaydın
    #    üst sınırını belirlemek için). Site başına en yakın olanı seç.
    next_start_by_site: dict[int, date] = {}
    next_stmt = select(SiteTonnageTarget).where(
        SiteTonnageTarget.production_site_id.in_(site_ids),
        SiteTonnageTarget.effective_from > effective_from,
    ).order_by(SiteTonnageTarget.effective_from.asc())
    for row in session.scalars(next_stmt):
        sid = row.production_site_id
        if sid not in next_start_by_site:
            next_start_by_site[sid] = row.effective_from

    # 3) Yeni kayıtları ekle
    created: list[SiteTonnageTarget] = []
    for site_id, ton in targets_by_site_id.items():
        next_start = next_start_by_site.get(site_id)
        eff_to = (next_start - timedelta(days=1)) if next_start else None
        row = SiteTonnageTarget(
            production_site_id=site_id,
            weekly_target_ton=ton,
            effective_from=effective_from,
            effective_to=eff_to,
            created_by=created_by,
        )
        session.add(row)
        created.append(row)

    session.flush()
    return created


def delete_target(session: Session, target_id: int) -> None:
    """Bir hedef kaydını sil (audit sonrası). Önceki dönemin
    ``effective_to``'su bu işlemle otomatik açılmaz — admin dilerse
    manuel açar."""
    row = session.get(SiteTonnageTarget, target_id)
    if row is not None:
        session.delete(row)
        session.flush()
