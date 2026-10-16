"""หน้าต่างครอปรูป และลบพื้นหลัง"""
from __future__ import annotations

import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import imagetools as it
from .dialogs import _buttons, _title
from .utils import parse_page_range
from .theme import ACCENT, MUTED


def _pil_to_qimage(im: Image.Image) -> QImage:
    im = im.convert("RGBA")
    q = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, im.width * 4, QImage.Format.Format_RGBA8888)
    return q.copy()


def _checker(p: QPainter, r: QRectF, size: int = 10) -> None:
    p.save()
    p.setClipRect(r)
    a, b = QColor("#FFFFFF"), QColor("#E3E3EA")
    y, row = r.top(), 0
    while y < r.bottom():
        x, col = r.left(), 0
        while x < r.right():
            p.fillRect(QRectF(x, y, size, size), a if (row + col) % 2 == 0 else b)
            x += size
            col += 1
        y += size
        row += 1
    p.restore()


# ───────────────────────── ครอป ─────────────────────────
class CropCanvas(QWidget):
    changed = Signal()
    HANDLE = 10

    def __init__(self, img: QImage):
        super().__init__()
        self.img = img
        self.setMinimumSize(560, 400)
        self.setMouseTracking(True)
        self.box = QRectF(0, 0, 1, 1)       # สัดส่วนของภาพ (0..1)
        self.ratio: float | None = None      # กว้าง/สูง ของพื้นที่ครอปที่ล็อกไว้ (หน่วยพิกเซลภาพจริง)
        self._drag: tuple[str, QRectF, QPointF] | None = None

    # พื้นที่แสดงภาพ
    def _img_rect(self) -> QRectF:
        W, H = self.width() - 20, self.height() - 20
        s = min(W / self.img.width(), H / self.img.height())
        w, h = self.img.width() * s, self.img.height() * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _box_px(self) -> QRectF:
        r = self._img_rect()
        b = self.box
        return QRectF(r.left() + b.left() * r.width(), r.top() + b.top() * r.height(), b.width() * r.width(), b.height() * r.height())

    def _handles(self) -> dict[str, QPointF]:
        b = self._box_px()
        return {"tl": b.topLeft(), "tr": b.topRight(), "bl": b.bottomLeft(), "br": b.bottomRight(),
                "t": QPointF(b.center().x(), b.top()), "b": QPointF(b.center().x(), b.bottom()),
                "l": QPointF(b.left(), b.center().y()), "r": QPointF(b.right(), b.center().y())}

    def _hit(self, pos: QPointF) -> str | None:
        for n, p in self._handles().items():
            if abs(pos.x() - p.x()) <= self.HANDLE and abs(pos.y() - p.y()) <= self.HANDLE:
                return n
        if self._box_px().contains(pos):
            return "move"
        return None

    def set_ratio(self, ratio: float | None) -> None:
        self.ratio = ratio
        if ratio:
            self._fit_ratio("br")
        self.update()
        self.changed.emit()

    def reset(self) -> None:
        self.box = QRectF(0, 0, 1, 1)
        if self.ratio:
            self._fit_ratio("br")
        self.update()
        self.changed.emit()

    def _fit_ratio(self, anchor: str) -> None:
        """ปรับกรอบให้ได้สัดส่วนที่ล็อกไว้ โดยคงมุมตรงข้ามกับ anchor (ย่อลงเสมอ ไม่ล้นภาพ)"""
        if not self.ratio:
            return
        iw, ih = self.img.width(), self.img.height()
        b = self.box
        w, h = b.width() * iw, b.height() * ih
        if w / h > self.ratio:
            w = h * self.ratio
        else:
            h = w / self.ratio
        nw, nh = w / iw, h / ih
        x = b.left() if "l" not in anchor else b.right() - nw
        y = b.top() if "t" not in anchor else b.bottom() - nh
        self.box = QRectF(x, y, nw, nh)

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), QColor("#2B2742"))
        r = self._img_rect()
        _checker(p, r)
        p.drawImage(r, self.img)
        b = self._box_px()
        shade = QColor(15, 12, 30, 150)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), b.top() - r.top()), shade)
        p.fillRect(QRectF(r.left(), b.bottom(), r.width(), r.bottom() - b.bottom()), shade)
        p.fillRect(QRectF(r.left(), b.top(), b.left() - r.left(), b.height()), shade)
        p.fillRect(QRectF(b.right(), b.top(), r.right() - b.right(), b.height()), shade)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("white"), 1.6))
        p.drawRect(b)
        p.setPen(QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DashLine))
        for k in (1, 2):                                  # เส้นแบ่งสามส่วน
            p.drawLine(QPointF(b.left() + b.width() * k / 3, b.top()), QPointF(b.left() + b.width() * k / 3, b.bottom()))
            p.drawLine(QPointF(b.left(), b.top() + b.height() * k / 3), QPointF(b.right(), b.top() + b.height() * k / 3))
        p.setBrush(QColor("white"))
        p.setPen(QPen(QColor(ACCENT), 1.6))
        for pt in self._handles().values():
            p.drawRoundedRect(QRectF(pt.x() - 5, pt.y() - 5, 10, 10), 2.5, 2.5)
        p.end()

    def mousePressEvent(self, ev):  # noqa: N802
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        h = self._hit(ev.position())
        if h:
            self._drag = (h, QRectF(self.box), ev.position())

    def mouseMoveEvent(self, ev):  # noqa: N802
        pos = ev.position()
        if self._drag is None:
            h = self._hit(pos)
            cur = {"tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                   "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                   "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
                   "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
                   "move": Qt.CursorShape.SizeAllCursor}.get(h or "", Qt.CursorShape.ArrowCursor)
            self.setCursor(QCursor(cur))
            return
        mode, orig, start = self._drag
        r = self._img_rect()
        dx, dy = (pos.x() - start.x()) / r.width(), (pos.y() - start.y()) / r.height()
        minw, minh = 12 / r.width(), 12 / r.height()
        x0, y0, x1, y1 = orig.left(), orig.top(), orig.right(), orig.bottom()
        if mode == "move":
            w, h = orig.width(), orig.height()
            nx = min(max(x0 + dx, 0.0), 1.0 - w)
            ny = min(max(y0 + dy, 0.0), 1.0 - h)
            self.box = QRectF(nx, ny, w, h)
        else:
            if "l" in mode:
                x0 = min(max(x0 + dx, 0.0), x1 - minw)
            if "r" in mode:
                x1 = max(min(x1 + dx, 1.0), x0 + minw)
            if "t" in mode:
                y0 = min(max(y0 + dy, 0.0), y1 - minh)
            if "b" in mode:
                y1 = max(min(y1 + dy, 1.0), y0 + minh)
            self.box = QRectF(QPointF(x0, y0), QPointF(x1, y1))
            if self.ratio:
                self._fit_ratio(mode if len(mode) == 2 else {"t": "bt", "b": "", "l": "lt", "r": ""}.get(mode, ""))
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, ev):  # noqa: N802
        self._drag = None

    def fractions(self) -> tuple[float, float, float, float]:
        b = self.box
        return b.left(), b.top(), b.right(), b.bottom()


class CropDialog(QDialog):
    RATIOS = [("อิสระ", None), ("1 : 1", 1.0), ("4 : 3", 4 / 3), ("3 : 2", 3 / 2), ("16 : 9", 16 / 9), ("3 : 4", 3 / 4), ("ตามภาพเดิม", "orig")]

    def __init__(self, parent, data: bytes):
        super().__init__(parent)
        self.setWindowTitle("ครอปรูป")
        im = it.load_image(data).convert("RGBA")
        if max(im.size) > 1600:
            k = 1600 / max(im.size)
            im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        self._orig_ratio = im.width / im.height
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(_title("ครอปรูป", "ลากมุม/ขอบเพื่อเลือกส่วนที่ต้องการเก็บ • ลากภายในกรอบเพื่อเลื่อน"))
        self.canvas = CropCanvas(_pil_to_qimage(im))
        lay.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("สัดส่วน"))
        self.ratio = QComboBox()
        for name, val in self.RATIOS:
            self.ratio.addItem(name, val)
        self.ratio.currentIndexChanged.connect(self._ratio_changed)
        row.addWidget(self.ratio)
        reset = QPushButton("รีเซ็ต")
        reset.clicked.connect(self.canvas.reset)
        row.addWidget(reset)
        row.addStretch(1)
        self.info = QLabel("")
        self.info.setStyleSheet(f"color:{MUTED};")
        row.addWidget(self.info)
        lay.addLayout(row)
        lay.addWidget(_buttons(self, "ครอป"))
        self.canvas.changed.connect(self._update_info)
        self._real = QSize(*it.load_image(data).size)
        self._update_info()

    def _ratio_changed(self) -> None:
        v = self.ratio.currentData()
        self.canvas.set_ratio(self._orig_ratio if v == "orig" else v)

    def _update_info(self) -> None:
        b = self.canvas.box
        self.info.setText(f"{round(b.width() * self._real.width())} × {round(b.height() * self._real.height())} พิกเซล")

    def fractions(self) -> tuple[float, float, float, float]:
        return self.canvas.fractions()


# ───────────────────────── ลบพื้นหลัง ─────────────────────────
class _Preview(QWidget):
    picked = Signal(QPointF)        # ตำแหน่งที่คลิก เป็นสัดส่วนของภาพ

    def __init__(self):
        super().__init__()
        self.setMinimumSize(520, 360)
        self.img: QImage | None = None
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _rect(self) -> QRectF:
        if self.img is None:
            return QRectF()
        W, H = self.width() - 16, self.height() - 16
        s = min(W / self.img.width(), H / self.img.height())
        w, h = self.img.width() * s, self.img.height() * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), QColor("#F1F0F8"))
        if self.img is not None:
            r = self._rect()
            _checker(p, r)
            p.drawImage(r, self.img)
            p.setPen(QPen(QColor("#CFCCE3"), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
        p.end()

    def mousePressEvent(self, ev):  # noqa: N802
        r = self._rect()
        if self.img is not None and r.contains(ev.position()) and ev.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(QPointF((ev.position().x() - r.left()) / r.width(), (ev.position().y() - r.top()) / r.height()))


class RemoveBgDialog(QDialog):
    def __init__(self, parent, data: bytes):
        super().__init__(parent)
        self.setWindowTitle("ลบพื้นหลัง")
        self.data = data
        full = it.load_image(data).convert("RGBA")
        small = full.copy()
        small.thumbnail((640, 640), Image.LANCZOS)
        self._small = np.array(small)
        self._bg = it.guess_background(self._small[..., :3])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(_title("ลบพื้นหลังรูป", "เหมาะกับลายเซ็น โลโก้ ตราประทับ และรูปที่พื้นหลังเป็นสีเรียบ • คลิกบนรูปเพื่อเลือกสีที่จะลบ"))
        self.preview = _Preview()
        lay.addWidget(self.preview, 1)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.sw = QPushButton()
        self.sw.setFixedSize(46, 26)
        self.sw.setToolTip("สีพื้นหลังที่จะลบ (คลิกบนรูปเพื่อเปลี่ยน)")
        auto = QPushButton("เดาจากขอบรูป")
        auto.clicked.connect(self._auto)
        h = QHBoxLayout()
        h.addWidget(self.sw)
        h.addWidget(auto)
        h.addStretch(1)
        form.addRow("สีที่จะลบ", h)
        self.tol = self._slider(30)
        self.soft = self._slider(25)
        form.addRow("ความไว (ช่วงสีใกล้เคียง)", self.tol)
        form.addRow("ความนุ่มของขอบ", self.soft)
        self.contig = QCheckBox("ลบเฉพาะส่วนที่ติดขอบภาพ (ไม่ลบสีเดียวกันที่อยู่ในตัวภาพ)")
        self.contig.setChecked(False)
        self.trim = QCheckBox("ตัดขอบว่างรอบรูปออก")
        self.trim.setChecked(True)
        form.addRow("", self.contig)
        form.addRow("", self.trim)
        lay.addLayout(form)
        lay.addWidget(_buttons(self, "ใช้รูปนี้"))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._render)
        for w in (self.tol, self.soft):
            w.valueChanged.connect(lambda _: self._timer.start())
        self.contig.toggled.connect(lambda _: self._timer.start())
        self.preview.picked.connect(self._pick)
        self._sync_swatch()
        self._render()

    @staticmethod
    def _slider(v: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setValue(v)
        return s

    def _sync_swatch(self) -> None:
        r, g, b = self._bg
        self.sw.setStyleSheet(f"background: rgb({r},{g},{b}); border: 1px solid #8C86B0; border-radius: 6px;")

    def _auto(self) -> None:
        self._bg = it.guess_background(self._small[..., :3])
        self._sync_swatch()
        self._render()

    def _pick(self, f: QPointF) -> None:
        h, w = self._small.shape[:2]
        x, y = min(w - 1, max(0, int(f.x() * w))), min(h - 1, max(0, int(f.y() * h)))
        self._bg = tuple(int(v) for v in self._small[y, x, :3])
        self._sync_swatch()
        self._render()

    def _render(self) -> None:
        res = it.remove_background(self._small, self._bg, self.tol.value(), self.soft.value(), self.contig.isChecked())
        self.preview.img = _pil_to_qimage(Image.fromarray(res, "RGBA"))
        self.preview.update()

    def result(self) -> tuple[bytes, tuple[float, float, float, float]]:
        return it.remove_background_bytes(self.data, self._bg, self.tol.value(), self.soft.value(),
                                          self.contig.isChecked(), self.trim.isChecked())


# ───────────────────────── ตัวเลือกตอนบันทึกเป็น Word / JPEG ─────────────────────────
class ExportOptionsDialog(QDialog):
    def __init__(self, parent, kind: str, total: int, current: int, preset: str = ""):
        super().__init__(parent)
        self.kind, self.total = kind, total
        self.setWindowTitle("บันทึกเป็น Word" if kind == "docx" else "บันทึกเป็นรูป JPEG")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        if kind == "docx":
            lay.addWidget(_title("บันทึกเป็น Word (.docx)", f"เอกสารนี้มี {total} หน้า"))
            self.r_edit = QRadioButton("แก้ไขข้อความได้ — แปลงเป็นข้อความ/ตาราง/รูปใน Word (หน้าตาอาจเพี้ยนบ้าง)")
            self.r_img = QRadioButton("เหมือนต้นฉบับ 100% — แต่ละหน้าเป็นรูปภาพ (แก้ข้อความไม่ได้)")
            self.r_edit.setChecked(True)
            lay.addWidget(self.r_edit)
            lay.addWidget(self.r_img)
            note = QLabel("เอกสารที่เป็นภาพสแกนไม่มีตัวอักษรจริง ให้เลือกแบบ “เหมือนต้นฉบับ”")
            note.setStyleSheet(f"color:{MUTED};")
            note.setWordWrap(True)
            lay.addWidget(note)
        else:
            lay.addWidget(_title("บันทึกเป็นรูป JPEG", f"เอกสารนี้มี {total} หน้า • หลายหน้าจะได้หลายไฟล์ (ชื่อไฟล์_หน้า001.jpg …)"))
        form = QFormLayout()
        self.range_edit = QLineEdit(preset)
        self.range_edit.setPlaceholderText(f"เว้นว่าง = ทุกหน้า • เช่น {current + 1} หรือ 1-3,5")
        form.addRow("หน้าที่ต้องการ", self.range_edit)
        self.dpi = QComboBox()
        self.quality = QSpinBox()
        if kind == "jpg":
            for d in (96, 150, 200, 300):
                self.dpi.addItem(f"{d} dpi", d)
            self.dpi.setCurrentIndex(2)
            self.quality.setRange(50, 100)
            self.quality.setValue(90)
            self.quality.setSuffix(" %")
            form.addRow("ความละเอียด", self.dpi)
            form.addRow("คุณภาพ", self.quality)
        lay.addLayout(form)
        lay.addWidget(_buttons(self, "บันทึก"))

    def accept(self) -> None:
        try:
            parse_page_range(self.range_edit.text(), self.total)
        except ValueError as e:
            QMessageBox.warning(self, "ช่วงหน้าไม่ถูกต้อง", str(e))
            return
        super().accept()

    def values(self) -> dict:
        return {"pages": parse_page_range(self.range_edit.text(), self.total),
                "editable": self.kind == "docx" and self.r_edit.isChecked(),
                "dpi": int(self.dpi.currentData() or 200), "quality": self.quality.value()}
