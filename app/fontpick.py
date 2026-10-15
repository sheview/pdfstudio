"""ตัวเลือกฟอนต์/ขนาดตัวอักษรแบบ dropdown (ใช้ในหน้าต่างใส่ข้อความและลายน้ำ)"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator, QFont, QFontDatabase
from PySide6.QtWidgets import QComboBox

from .config import FONT_FAMILY

SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40, 48, 60, 72, 96, 120, 160, 200]


def thai_font_families() -> list[str]:
    fams = set(QFontDatabase.families(QFontDatabase.WritingSystem.Thai))
    all_ = set(QFontDatabase.families())
    out = sorted(fams, key=str.lower)
    if FONT_FAMILY in all_:
        out = [f for f in out if f != FONT_FAMILY]
        out.insert(0, FONT_FAMILY)
    return out


class FontCombo(QComboBox):
    changed = Signal()

    def __init__(self, current: str = "", parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaxVisibleItems(14)
        for name in thai_font_families():
            self.addItem(name)
            self.setItemData(self.count() - 1, QFont(name, 11), Qt.ItemDataRole.FontRole)
        self.set_family(current)
        self.currentIndexChanged.connect(lambda _: self.changed.emit())

    def family(self) -> str:
        return self.currentText()

    def set_family(self, fam: str) -> None:
        i = self.findText(fam)
        if i < 0 and fam:
            self.addItem(fam)
            i = self.count() - 1
        if i >= 0:
            self.setCurrentIndex(i)


class SizeCombo(QComboBox):
    changed = Signal()

    def __init__(self, value: float = 14.0, suffix: str = "", parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(14)
        self.setFixedWidth(104)
        for s in SIZES:
            self.addItem(str(s))
        v = QDoubleValidator(1.0, 999.0, 1, self)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.lineEdit().setValidator(v)
        self.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_value(value)
        self.currentTextChanged.connect(lambda _: self.changed.emit())

    def value(self) -> float:
        try:
            return max(1.0, float(self.currentText().replace(",", ".")))
        except ValueError:
            return 14.0

    def set_value(self, v: float) -> None:
        self.setCurrentText(f"{v:g}")
