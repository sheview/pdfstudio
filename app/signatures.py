"""คลังลายเซ็น/รูปภาพ: นำเข้ารูป, ลบพื้นหลังขาว, วาดลายเซ็นเอง, เก็บไว้ใช้ซ้ำ"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QPointF, QSize, QStandardPaths, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from .icons import icon
from .theme import MUTED

IMG_FILTER = "รูปภาพ (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)"


def sig_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation) or str(Path.home() / ".pdfstudio")
    d = Path(base) / "signatures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_signatures() -> list[Path]:
    return sorted(sig_dir().glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)


def remove_white_background(src: str, dst: str) -> None:
    """ทำพื้นขาว/สว่างให้โปร่งใส เหลือเฉพาะลายเซ็น (ใช้กับรูปถ่าย/สแกนลายเซ็น)"""
    from PIL import Image
    im = Image.open(src).convert("RGB")
    gray = im.convert("L")
    alpha = gray.point(lambda v: 0 if v > 235 else min(255, int((235 - v) * 2.2)))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    bbox = alpha.getbbox()
    if bbox:
        out = out.crop(bbox)
    out.save(dst)


def save_signature(src: str, transparent: bool) -> Path:
    dst = sig_dir() / f"sig_{int(time.time() * 1000)}.png"
    if transparent:
        remove_white_background(src, str(dst))
    else:
        QImage(src).save(str(dst))
    return dst


class DrawPad(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(520, 200)
        self.strokes: list[list[QPointF]] = []
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, e):  # noqa: N802
        self.strokes.append([e.position()])

    def mouseMoveEvent(self, e):  # noqa: N802
        if self.strokes:
            self.strokes[-1].append(e.position())
            self.update()

    def clear(self):
        self.strokes.clear()
        self.update()

    def _path(self, s):
        p = QPainterPath(s[0])
        for q in s[1:]:
            p.lineTo(q)
        return p

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        p.setPen(QPen(QColor("#CDD3DF"), 1, Qt.PenStyle.DashLine))
        p.drawLine(20, 150, self.width() - 20, 150)
        p.setPen(QPen(QColor("#111827"), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for s in self.strokes:
            p.drawPath(self._path(s))
        if not self.strokes:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "ใช้เมาส์/ปากกา เซ็นชื่อในกรอบนี้")

    def to_png(self, path: str) -> bool:
        if not self.strokes:
            return False
        img = QImage(self.size() * 2, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(2, 2)
        p.setPen(QPen(QColor("#111827"), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        rect = None
        for s in self.strokes:
            path_ = self._path(s)
            p.drawPath(path_)
            r = path_.boundingRect()
            rect = r if rect is None else rect.united(r)
        p.end()
        r = rect.adjusted(-6, -6, 6, 6)
        img.copy(int(r.x() * 2), int(r.y() * 2), int(r.width() * 2), int(r.height() * 2)).save(path)
        return True


class DrawDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("วาดลายเซ็น")
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        self.pad = DrawPad()
        v.addWidget(self.pad)
        row = QHBoxLayout()
        clear = QPushButton("ล้าง")
        clear.clicked.connect(self.pad.clear)
        row.addWidget(clear)
        row.addStretch(1)
        box = QDialogButtonBox()
        ok = box.addButton("บันทึกลายเซ็น", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setObjectName("Primary")
        box.addButton("ยกเลิก", QDialogButtonBox.ButtonRole.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        row.addWidget(box)
        v.addLayout(row)


class SignatureDialog(QDialog):
    """เลือกรูป/ลายเซ็นที่จะวางลงเอกสาร — นำเข้าใหม่หรือเลือกจากคลังที่เคยเก็บไว้"""

    def __init__(self, parent, start_dir: str = ""):
        super().__init__(parent)
        self.setWindowTitle("แทรกรูปภาพ / ลายเซ็น")
        self.resize(620, 480)
        self.start_dir = start_dir
        self.chosen: str | None = None
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        t = QLabel("แทรกรูปภาพ / ลายเซ็น")
        t.setStyleSheet("font-size:14pt;font-weight:700;")
        v.addWidget(t)
        s = QLabel("นำเข้ารูปลายเซ็น (ถ่ายหรือสแกน) หรือวาดเอง แล้วเก็บไว้ใช้ซ้ำได้ — เลือกรูปแล้วกด “ใช้รูปนี้”")
        s.setStyleSheet(f"color:{MUTED};")
        s.setWordWrap(True)
        v.addWidget(s)
        row = QHBoxLayout()
        b1 = QPushButton(" นำเข้ารูปลายเซ็น…")
        b1.setIcon(icon("image-plus-outline"))
        b1.clicked.connect(self.import_sig)
        b2 = QPushButton(" วาดลายเซ็น…")
        b2.setIcon(icon("draw"))
        b2.clicked.connect(self.draw_sig)
        b3 = QPushButton(" ใช้รูปภาพอื่น (ไม่เก็บ)…")
        b3.setIcon(icon("image-outline"))
        b3.clicked.connect(self.pick_once)
        for b in (b1, b2, b3):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.chk = QCheckBox("ลบพื้นหลังขาวตอนนำเข้า (ให้ลายเซ็นโปร่งใส)")
        self.chk.setChecked(True)
        v.addWidget(self.chk)
        self.lst = QListWidget()
        self.lst.setViewMode(QListWidget.ViewMode.IconMode)
        self.lst.setIconSize(QSize(150, 70))
        self.lst.setGridSize(QSize(170, 90))
        self.lst.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.lst.setMovement(QListWidget.Movement.Static)
        self.lst.itemDoubleClicked.connect(lambda _: self.accept())
        v.addWidget(self.lst, 1)
        row2 = QHBoxLayout()
        rm = QPushButton("ลบจากคลัง")
        rm.setObjectName("Danger")
        rm.clicked.connect(self.remove_sel)
        row2.addWidget(rm)
        row2.addStretch(1)
        box = QDialogButtonBox()
        self.ok = box.addButton("ใช้รูปนี้", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setObjectName("Primary")
        box.addButton("ยกเลิก", QDialogButtonBox.ButtonRole.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        row2.addWidget(box)
        v.addLayout(row2)
        self.reload()

    def reload(self, select: Path | None = None):
        self.lst.clear()
        for p in list_signatures():
            pm = QPixmap(str(p))
            if pm.isNull():
                continue
            bg = QPixmap(150, 70)
            bg.fill(QColor("white"))
            q = QPainter(bg)
            sc = pm.scaled(146, 66, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            q.drawPixmap((150 - sc.width()) // 2, (70 - sc.height()) // 2, sc)
            q.end()
            it = QListWidgetItem(QIcon(bg), "")
            it.setData(Qt.ItemDataRole.UserRole, str(p))
            self.lst.addItem(it)
            if select and p == select:
                it.setSelected(True)
        if self.lst.count() and not self.lst.selectedItems():
            self.lst.item(0).setSelected(True)

    def import_sig(self):
        f, _ = QFileDialog.getOpenFileName(self, "เลือกรูปลายเซ็น", self.start_dir, IMG_FILTER)
        if not f:
            return
        try:
            self.reload(save_signature(f, self.chk.isChecked()))
        except Exception as e:
            QMessageBox.warning(self, "นำเข้าไม่สำเร็จ", str(e))

    def draw_sig(self):
        d = DrawDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted:
            dst = sig_dir() / f"sig_{int(time.time() * 1000)}.png"
            if d.pad.to_png(str(dst)):
                self.reload(dst)

    def pick_once(self):
        f, _ = QFileDialog.getOpenFileName(self, "เลือกรูปภาพ", self.start_dir, IMG_FILTER)
        if f:
            self.chosen = f
            self.accept()

    def remove_sel(self):
        for it in self.lst.selectedItems():
            Path(it.data(Qt.ItemDataRole.UserRole)).unlink(missing_ok=True)
        self.reload()

    def accept(self):
        if self.chosen is None:
            its = self.lst.selectedItems()
            if not its:
                QMessageBox.information(self, "เลือกรูป", "ยังไม่ได้เลือกรูป — นำเข้าหรือวาดลายเซ็นก่อน")
                return
            self.chosen = its[0].data(Qt.ItemDataRole.UserRole)
        super().accept()
