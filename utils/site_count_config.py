"""
Üretim yerine göre sayım giriş ekranı alan yapılandırması.

Kayıt yoksa varsayılan olarak tüm alanlar açık (mevcut form davranışı).
İş kuralı için `sql/migration_add_site_count_config.sql` seed'ine bakın.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from db.models import SiteCountConfig


@dataclass(frozen=True)
class CountFieldsConfig:
    """Site için hangi sayım alanlarının gösterileceği."""

    show_empty: bool = True
    show_wip: bool = True
    show_full: bool = True
    show_kanban: bool = True
    show_scrap: bool = True
    show_tonnage: bool = True

    @property
    def any_color_field(self) -> bool:
        """En az bir renk alanı açık mı? (grid'i çizmek için)"""
        return any([
            self.show_empty, self.show_wip, self.show_full,
            self.show_kanban, self.show_scrap,
        ])

    @property
    def visible_color_fields(self) -> list[str]:
        """Görünür renk alanları — sıralı."""
        out = []
        if self.show_empty: out.append("empty")
        if self.show_wip: out.append("wip")
        if self.show_full: out.append("full")
        if self.show_kanban: out.append("kanban")
        if self.show_scrap: out.append("scrap")
        return out


_DEFAULT_ALL_ON = CountFieldsConfig()


def get_count_fields_config(
    session: Session, site_id: int,
) -> CountFieldsConfig:
    """Sitenin config'ini getir; yoksa hepsi açık (default)."""
    row: Optional[SiteCountConfig] = session.get(SiteCountConfig, site_id)
    if row is None:
        return _DEFAULT_ALL_ON
    return CountFieldsConfig(
        show_empty=row.show_empty,
        show_wip=row.show_wip,
        show_full=row.show_full,
        show_kanban=row.show_kanban,
        show_scrap=row.show_scrap,
        show_tonnage=row.show_tonnage,
    )


def upsert_count_fields_config(
    session: Session,
    site_id: int,
    *,
    show_empty: bool,
    show_wip: bool,
    show_full: bool,
    show_kanban: bool,
    show_scrap: bool,
    show_tonnage: bool,
    updated_by: int,
) -> SiteCountConfig:
    """Site config'i ekle veya güncelle."""
    row = session.get(SiteCountConfig, site_id)
    if row is None:
        row = SiteCountConfig(
            site_id=site_id,
            show_empty=show_empty, show_wip=show_wip, show_full=show_full,
            show_kanban=show_kanban, show_scrap=show_scrap,
            show_tonnage=show_tonnage,
            updated_by=updated_by,
        )
        session.add(row)
    else:
        row.show_empty = show_empty
        row.show_wip = show_wip
        row.show_full = show_full
        row.show_kanban = show_kanban
        row.show_scrap = show_scrap
        row.show_tonnage = show_tonnage
        row.updated_by = updated_by
    session.flush()
    return row
