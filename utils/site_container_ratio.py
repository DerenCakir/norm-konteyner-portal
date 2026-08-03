"""
Üretim yeri × dolu konteyner başına tonaj (t/konteyner) oranları.

Sayım formunda 'Dolu' alanı kapalı olan siteler için tonaj/oran ile
dolu konteyner adedi hesaplanır (ceil).

Ana kullanım:
  • ``get_ratio(session, site_id)`` — oran veya None
  • ``get_ratios_all(session)`` — {site_id: Decimal}
  • ``upsert_ratio(session, site_id, ratio, updated_by)`` — ekle/güncelle,
    o siteye ait mevcut manual_site_aggregates.full_total'i yeniden
    hesaplar (tonaj değişmediği halde oran değiştiği için).
  • ``compute_full_from_tonnage(ton, ratio)`` — ceil(ton / ratio),
    ratio yok/0 ise None.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from db.models import ManualSiteAggregate, SiteContainerRatio


def get_ratio(session: Session, site_id: int) -> Optional[Decimal]:
    row = session.get(SiteContainerRatio, site_id)
    return row.ratio_ton_per_container if row else None


def get_ratios_all(session: Session) -> dict[int, Decimal]:
    stmt = select(SiteContainerRatio)
    return {
        r.site_id: r.ratio_ton_per_container
        for r in session.scalars(stmt)
    }


def compute_full_from_tonnage(
    ton: Decimal | float | None, ratio: Decimal | float | None,
) -> Optional[int]:
    """Ceil(ton / ratio). None döner: veri eksik / oran 0."""
    if ton is None or ratio is None:
        return None
    try:
        t = float(ton)
        r = float(ratio)
    except (TypeError, ValueError):
        return None
    if r <= 0 or t < 0:
        return None
    return int(math.ceil(t / r))


def upsert_ratio(
    session: Session, site_id: int, ratio: Decimal, updated_by: int,
    *,
    recompute_existing: bool = True,
) -> SiteContainerRatio:
    """Oranı ekle/güncelle. Varsayılan olarak o siteye ait mevcut
    manual_site_aggregates.full_total değerlerini yeni orana göre
    yeniden hesaplar (tonaj_total sabit, oran değişti).
    """
    if ratio is None or ratio <= 0:
        raise ValueError("Oran pozitif olmalı")
    row = session.get(SiteContainerRatio, site_id)
    if row is None:
        row = SiteContainerRatio(
            site_id=site_id,
            ratio_ton_per_container=Decimal(str(ratio)),
            updated_by=updated_by,
        )
        session.add(row)
    else:
        row.ratio_ton_per_container = Decimal(str(ratio))
        row.updated_by = updated_by
    session.flush()

    if recompute_existing:
        # O siteye ait tum manual_site_aggregates satirlarinda
        # full_total = ceil(tonnage_total / yeni_oran).
        stmt = select(ManualSiteAggregate).where(
            ManualSiteAggregate.site_id == site_id,
        )
        for msa in session.scalars(stmt):
            new_full = compute_full_from_tonnage(
                msa.tonnage_total, row.ratio_ton_per_container,
            )
            if new_full is not None:
                msa.full_total = new_full
        session.flush()

    return row


def delete_ratio(session: Session, site_id: int) -> None:
    row = session.get(SiteContainerRatio, site_id)
    if row is not None:
        session.delete(row)
        session.flush()
