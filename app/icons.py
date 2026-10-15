"""ไอคอน (Material Design Icons ผ่าน qtawesome) พร้อมสี active/disabled"""
from __future__ import annotations

from functools import lru_cache

import qtawesome as qta
from PySide6.QtGui import QIcon

from .theme import ACCENT, ICON, ICON_DISABLED


@lru_cache(maxsize=256)
def icon(name: str, color: str = ICON, active: str = ACCENT) -> QIcon:
    try:
        return qta.icon(
            f"mdi6.{name}", color=color, color_active=active, color_disabled=ICON_DISABLED, color_selected=active
        )
    except Exception:
        return QIcon()
