"""สร้าง QR Code จากลิงก์ (แบบ A: ลิงก์ที่มีอยู่แล้ว เช่น SharePoint / Google Drive / เว็บบริษัท)"""
from __future__ import annotations

import io
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout

from .dialogs import _buttons, _title
from .theme import MUTED


def normalize_url(text: str) -> str:
    t = text.strip()
    if not t:
        raise ValueError("ยังไม่ได้ใส่ลิงก์")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", t):
        if " " in t or "." not in t:
            raise ValueError("ลิงก์ไม่ถูกต้อง — ใส่ที่อยู่เว็บ เช่น https://…")
        t = "https://" + t
    if len(t) > 700:
        raise ValueError("ลิงก์ยาวเกินไป (เกิน 700 ตัวอักษร) QR จะละเอียดจนสแกนยาก — ใช้ลิงก์แบบสั้นแทน")
    return t


def make_qr_png(url: str, scale: int = 10, border: int = 2, level: str = "m") -> bytes:
    import segno          # นำเข้าตอนใช้งานจริง — ถ้าไลบรารีหายก็ไม่ทำให้โปรแกรมเปิดไม่ขึ้น

    q = segno.make(url, error=level, micro=False)
    buf = io.BytesIO()
    q.save(buf, kind="png", scale=scale, border=border, dark="#000000", light="#FFFFFF")
    return buf.getvalue()


class QrDialog(QDialog):
    SIZES = [("เล็ก (2.5 ซม.)", 70), ("กลาง (3.5 ซม.)", 100), ("ใหญ่ (5 ซม.)", 140)]

    def __init__(self, parent=None, preset: str = ""):
        super().__init__(parent)
        self.setWindowTitle("สร้าง QR Code")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(_title("สร้าง QR Code ให้ลูกค้า scan", "วางลิงก์ของไฟล์ที่อยู่บน SharePoint / Google Drive / เว็บบริษัท (ตั้งสิทธิ์ให้ลูกค้าเปิดได้) — QR คือตัวลิงก์ ไม่ได้บรรจุไฟล์"))
        form = QFormLayout()
        self.url = QLineEdit(preset)
        self.url.setPlaceholderText("https://…")
        self.caption = QLineEdit("สแกนเพื่อดูเอกสาร")
        self.size = QComboBox()
        for n, v in self.SIZES:
            self.size.addItem(n, v)
        self.size.setCurrentIndex(1)
        form.addRow("ลิงก์", self.url)
        form.addRow("ข้อความใต้ QR", self.caption)
        form.addRow("ขนาด", self.size)
        lay.addLayout(form)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(170)
        lay.addWidget(self.preview)
        self.note = QLabel("")
        self.note.setStyleSheet(f"color:{MUTED};")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        lay.addWidget(_buttons(self, "วาง QR ลงหน้า"))
        self.url.textChanged.connect(self._update)
        self._update()

    def _update(self) -> None:
        try:
            u = normalize_url(self.url.text())
            img = QImage.fromData(make_qr_png(u, 6))
            self.preview.setPixmap(QPixmap.fromImage(img).scaled(160, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
            self.note.setText("ทดลองสแกนด้วยมือถือก่อนแจกลูกค้าทุกครั้ง")
        except ValueError as e:
            self.preview.clear()
            self.note.setText(str(e) if self.url.text().strip() else "")

    def accept(self) -> None:
        try:
            normalize_url(self.url.text())
        except ValueError as e:
            QMessageBox.warning(self, "สร้าง QR Code", str(e))
            return
        super().accept()

    def values(self) -> tuple[bytes, str, float]:
        u = normalize_url(self.url.text())
        return make_qr_png(u), self.caption.text().strip(), float(self.size.currentData())
