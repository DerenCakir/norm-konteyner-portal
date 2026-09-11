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
    """UPSERT: verilen tarihten itibaren siteler için hedefler yazılır.

    Var olan `(site, effective_from)` kaydı UPDATE edilir; yoksa INSERT.
    Kullanici ayni tarihe defalarca kayit yapabilir -- unique constraint
    hatasi vermez.

    Geçmişe dönük veya out-of-order girişi de destekler:
      • Önceki dönem (``effective_from < new_from``) kapsıyor mu (açık uçlu
        veya ``effective_to >= new_from``)? → önceki dönemin
        ``effective_to`` bunu ``new_from - 1``'e çekilir.
      • Sonraki dönem (``effective_from > new_from``) var mı? → yeni
        kaydın ``effective_to``, o en yakın sonraki dönemin
        ``effective_from - 1``'ine set edilir (yoksa NULL — açık uçlu).
    """
    if effective_from is None:
        raise ValueError("effective_from gerekli")
    if not targets_by_site_id:
        raise ValueError("En az bir site hedefi verilmeli")

    from datetime import timedelta
    prev_close_date = effective_from - timedelta(days=1)

    site_ids = list(targets_by_site_id.keys())

    # 1) Önceki dönemleri kapat (yeni_from < mevcut kapsam ise).
    #    NOT: Ayni effective_from'a esit olanlar burada dokunulmuyor --
    #    onlar asagida UPSERT ile update ediliyor.
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

    # 3) Ayni (site, effective_from) icin mevcut kayitlari cek (UPSERT
    #    icin update etmek uzere).
    existing_stmt = select(SiteTonnageTarget).where(
        SiteTonnageTarget.production_site_id.in_(site_ids),
        SiteTonnageTarget.effective_from == effective_from,
    )
    existing_by_site: dict[int, SiteTonnageTarget] = {
        row.production_site_id: row
        for row in session.scalars(existing_stmt)
    }

    # 4) UPSERT — var olan kayitlari UPDATE, yenileri INSERT
    created_or_updated: list[SiteTonnageTarget] = []
    for site_id, ton in targets_by_site_id.items():
        next_start = next_start_by_site.get(site_id)
        eff_to = (next_start - timedelta(days=1)) if next_start else None

        existing = existing_by_site.get(site_id)
        if existing is not None:
            # UPDATE — kullanicinin yeni girdigi degeri yaz.
            existing.weekly_target_ton = ton
            existing.effective_to = eff_to
            existing.created_by = created_by
            created_or_updated.append(existing)
        else:
            # INSERT — yeni kayit
            row = SiteTonnageTarget(
                production_site_id=site_id,
                weekly_target_ton=ton,
                effective_from=effective_from,
                effective_to=eff_to,
                created_by=created_by,
            )
            session.add(row)
            created_or_updated.append(row)

    session.flush()
    return created_or_updated


def get_targets_by_week_site(
    session: Session, week_isos: Sequence[str],
) -> dict[str, dict[int, float]]:
    """Excel export için: {week_iso: {site_id: hedef_ton}}.

    Her hafta için o haftanın Pazartesi'sinde geçerli hedefleri toplar.
    Bir haftada bir site için hedef yoksa o (week, site) çifti sonuçta yer
    almaz — chart tarafı None olarak yorumlar.
    """
    result: dict[str, dict[int, float]] = {}
    for wk in week_isos:
        raw = get_weekly_targets_for_week(session, wk)
        if raw:
            result[wk] = {sid: float(v) for sid, v in raw.items()}
    return result


def all_target_effective_weeks(session: Session) -> list[str]:
    """Hedef girilen tum effective_from tarihlerini ISO haftaya cevirir.

    Kullanici hedef girerken sectigi Pazartesi'ler burada listelenir --
    Excel export'a bu haftalari dahil edip Karsilastirma sheet'inde
    tablo cizmemizi saglar (sayim verisi olmasa dahi).
    """
    from utils.week import week_iso_from_date
    stmt = select(SiteTonnageTarget.effective_from).distinct()
    weeks: set[str] = set()
    for eff_from in session.scalars(stmt):
        try:
            weeks.add(week_iso_from_date(eff_from))
        except Exception:
            continue
    return sorted(weeks)


def get_all_site_labels(session: Session) -> dict[int, tuple[str, str]]:
    """{site_id: (code, name)} — aktif tüm üretim yerleri."""
    from db.models import ProductionSite
    stmt = select(ProductionSite).where(ProductionSite.is_active.is_(True))
    return {
        row.id: (row.code, row.name)
        for row in session.scalars(stmt)
    }


def delete_target(session: Session, target_id: int) -> None:
    """Bir hedef kaydını sil (audit sonrası). Önceki dönemin
    ``effective_to``'su bu işlemle otomatik açılmaz — admin dilerse
    manuel açar."""
    row = session.get(SiteTonnageTarget, target_id)
    if row is not None:
        session.delete(row)
        session.flush()
