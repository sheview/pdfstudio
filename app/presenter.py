"""โหมดนำเสนอ: เต็มจอ เปลี่ยนหน้าทีละหน้าพร้อมเอฟเฟกต์ (เฟด / สไลด์ / เลื่อนขึ้น)"""
from __future__ import annotations

import ctypes
import sys
from collections import OrderedDict
from dataclasses import dataclass

import pymupdf
from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QRectF, QSettings, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import SETTINGS_APP, SETTINGS_ORG
from .dialogs import _buttons, _title
from .theme import MUTED

TRANSITIONS = [("เฟด (ค่อย ๆ จางเปลี่ยนหน้า)", "fade"), ("สไลด์ (เลื่อนซ้าย-ขวา)", "slide"),
               ("เลื่อนขึ้น", "slide_up"), ("ไม่มีเอฟเฟกต์", "none")]


@dataclass
class PresentOptions:
    transition: str = "fade"
    duration_ms: int = 450
    auto_sec: int = 0            # 0 = เปลี่ยนหน้าเองด้วยมือ
    loop: bool = False
    screen: int = -1             # -1 = จอเดียวกับหน้าต่างโปรแกรม

    @classmethod
    def load(cls) -> "PresentOptions":
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        return cls(str(s.value("present/transition", "fade")), int(s.value("present/duration", 450)),
                   int(s.value("present/auto", 0)), str(s.value("present/loop", "false")).lower() == "true",
                   int(s.value("present/screen", -1)))

    def save(self) -> None:
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        s.setValue("present/transition", self.transition)
        s.setValue("present/duration", self.duration_ms)
        s.setValue("present/auto", self.auto_sec)
        s.setValue("present/loop", "true" if self.loop else "false")
        s.setValue("present/screen", self.screen)


class PresentOptionsDialog(QDialog):
    def __init__(self, parent, opts: PresentOptions):
        super().__init__(parent)
        self.setWindowTitle("ตั้งค่าการนำเสนอ")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(_title("ตั้งค่าการนำเสนอ", "เริ่มนำเสนอด้วย F5 (จากหน้าแรก) หรือ Shift+F5 (จากหน้าปัจจุบัน)"))
        form = QFormLayout()
        self.tr = QComboBox()
        for name, key in TRANSITIONS:
            self.tr.addItem(name, key)
        self.tr.setCurrentIndex(max(0, self.tr.findData(opts.transition)))
        self.dur = QSpinBox()
        self.dur.setRange(100, 2000)
        self.dur.setSingleStep(50)
        self.dur.setSuffix(" มิลลิวินาที")
        self.dur.setValue(opts.duration_ms)
        self.auto = QSpinBox()
        self.auto.setRange(0, 600)
        self.auto.setSuffix(" วินาที")
        self.auto.setSpecialValueText("ปิด (กดเปลี่ยนหน้าเอง)")
        self.auto.setValue(opts.auto_sec)
        self.scr = QComboBox()
        self.scr.addItem("จอเดียวกับโปรแกรม", -1)
        for i, sc in enumerate(QApplication.screens()):
            g = sc.geometry()
            self.scr.addItem(f"จอ {i + 1}  ({g.width()}×{g.height()})", i)
        self.scr.setCurrentIndex(max(0, self.scr.findData(opts.screen)))
        self.loop = QCheckBox("วนกลับหน้าแรกเมื่อจบ")
        self.loop.setChecked(opts.loop)
        form.addRow("เอฟเฟกต์เปลี่ยนหน้า", self.tr)
        form.addRow("ความเร็วเอฟเฟกต์", self.dur)
        form.addRow("เปลี่ยนหน้าอัตโนมัติ", self.auto)
        form.addRow("แสดงนำเสนอบนจอ", self.scr)
        form.addRow("", self.loop)
        lay.addLayout(form)
        keys = QLabel("ปุ่มลัดตอนนำเสนอ:  → ↓ Space คลิก = หน้าถัดไป   ← ↑ Backspace คลิกขวา = ย้อนกลับ   Home/End = หน้าแรก/สุดท้าย\n"
                      "เลขหน้า + Enter = ไปหน้านั้น   B = จอดำ   W = จอขาว   L = เลเซอร์พอยน์เตอร์   Esc = ออก\n"
                      "D = ปากกา   H = ไฮไลต์   C = เปลี่ยนสี   U = ลบเส้นล่าสุด   E = ลบเส้นทั้งหน้า\n"
                      "Z หรือ Ctrl+ล้อเมาส์ = ซูม (ลากเพื่อเลื่อนดู)   + / − = ปรับซูม   F = รีเซ็ตซูม")
        keys.setStyleSheet(f"color:{MUTED};")
        keys.setWordWrap(True)
        lay.addWidget(keys)
        lay.addWidget(_buttons(self, "บันทึก"))

    def values(self) -> PresentOptions:
        return PresentOptions(self.tr.currentData(), self.dur.value(), self.auto.value(), self.loop.isChecked(), self.scr.currentData())


def _keep_awake(on: bool) -> None:
    """กันจอดับ/สกรีนเซฟเวอร์ระหว่างนำเสนอ (Windows)"""
    if sys.platform != "win32":
        return
    try:
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ((ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED) if on else 0))
    except Exception:
        pass


class PresentationWindow(QWidget):
    def __init__(self, pdf_bytes: bytes, start: int, opts: PresentOptions, screen=None, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("นำเสนอ")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet("background:black;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.doc = pymupdf.open("pdf", pdf_bytes)
        self.n = self.doc.page_count
        self.opts = opts
        self.index = min(max(start, 0), self.n - 1)
        self._cache: "OrderedDict[tuple[int, int, int], QPixmap]" = OrderedDict()
        self._anim: QVariantAnimation | None = None
        self._from: QPixmap | None = None
        self._to: QPixmap | None = None
        self._dir = 1
        self._t = 1.0
        self._black = False
        self._white = False
        self._laser = False
        self._mouse = QPoint(-100, -100)
        self._digits = ""
        self._ended = False
        self._tool: str | None = None            # None | "pen" | "hl"
        self._ink: dict[int, list] = {}          # หน้า → [(tool, QColor, [QPointF ในพิกัดฐาน])]
        self._cur: list | None = None
        self._ci = 0
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._drag: tuple[QPoint, QPointF] | None = None
        self._moved = False
        self._zpix: tuple | None = None
        self._hud_text = ""
        self._hud_timer = QTimer(self)
        self._hud_timer.setSingleShot(True)
        self._hud_timer.setInterval(1400)
        self._hud_timer.timeout.connect(self._clear_hud)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.setInterval(2200)
        self._cursor_timer.timeout.connect(self._hide_cursor)
        self._auto = QTimer(self)
        self._auto.timeout.connect(self.next)
        if screen is not None:
            self.setScreen(screen)
        self.closed_callbacks: list = []

    # ── วงจรชีวิต ──
    def start(self) -> None:
        _keep_awake(True)
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        self.setFocus()
        self._cursor_timer.start()
        if self.opts.auto_sec > 0:
            self._auto.start(int(self.opts.auto_sec * 1000))
        self._show_hud(f"{self.index + 1} / {self.n}")

    def closeEvent(self, ev):  # noqa: N802
        _keep_awake(False)
        self._auto.stop()
        if self._anim is not None:
            self._anim.stop()
        self.unsetCursor()
        try:
            self.doc.close()
        except Exception:
            pass
        for cb in self.closed_callbacks:
            cb()
        super().closeEvent(ev)

    # ── เรนเดอร์หน้า ──
    def _render(self, i: int) -> QPixmap:
        dpr = self.devicePixelRatioF()
        W, H = max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr))
        key = (i, W, H)
        pm = self._cache.get(key)
        if pm is not None:
            self._cache.move_to_end(key)
            return pm
        page = self.doc[i]
        r = page.rect
        s = min(W / r.width, H / r.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
        canvas = QPixmap(W, H)
        canvas.fill(QColor("black"))
        p = QPainter(canvas)
        p.drawImage((W - img.width()) // 2, (H - img.height()) // 2, img)
        p.end()
        canvas.setDevicePixelRatio(dpr)
        self._cache[key] = canvas
        while len(self._cache) > 6:
            self._cache.popitem(last=False)
        return canvas

    # ── ซูม ──
    PEN_COLORS = [QColor(230, 40, 40), QColor(40, 110, 240), QColor(30, 170, 80), QColor(250, 250, 250), QColor(20, 20, 20)]

    def _layout(self, i: int):
        """สเกลฐาน + ตำแหน่งหน้าในพิกัดฐาน (พิกเซลตรรกะ)"""
        r = self.doc[i].rect
        s = min(self.width() / r.width, self.height() / r.height)
        return s, (self.width() - r.width * s) / 2, (self.height() - r.height * s) / 2

    def _to_base(self, pos) -> QPointF:
        return QPointF((pos.x() - self._pan.x()) / self._zoom, (pos.y() - self._pan.y()) / self._zoom)

    def _clamp_pan(self) -> None:
        z = self._zoom
        self._pan = QPointF(min(0.0, max(self.width() * (1 - z), self._pan.x())),
                            min(0.0, max(self.height() * (1 - z), self._pan.y())))

    def set_zoom(self, z: float, anchor: QPointF | None = None) -> None:
        z = min(6.0, max(1.0, z))
        a = anchor if anchor is not None else QPointF(self.width() / 2, self.height() / 2)
        base = QPointF((a.x() - self._pan.x()) / self._zoom, (a.y() - self._pan.y()) / self._zoom)
        self._zoom = z
        self._pan = QPointF(a.x() - base.x() * z, a.y() - base.y() * z)
        self._clamp_pan()
        self._zpix = None
        self._show_hud(f"ซูม {int(z * 100)}%" if z > 1.0 else "ซูม 100%")

    def _render_zoom(self) -> QPixmap:
        """เรนเดอร์เฉพาะส่วนที่เห็นของหน้าที่ซูม ให้คมที่ความละเอียดจอ"""
        key = (self.index, self._zoom, self._pan.x(), self._pan.y(), self.width(), self.height())
        if self._zpix is not None and self._zpix[0] == key:
            return self._zpix[1]
        dpr = self.devicePixelRatioF()
        s, ox, oy = self._layout(self.index)
        z = self._zoom
        # ส่วนที่มองเห็นในพิกัดฐาน → พิกัดหน้า PDF
        vx0, vy0 = -self._pan.x() / z, -self._pan.y() / z
        vx1, vy1 = vx0 + self.width() / z, vy0 + self.height() / z
        page = self.doc[self.index]
        clip = pymupdf.Rect((vx0 - ox) / s, (vy0 - oy) / s, (vx1 - ox) / s, (vy1 - oy) / s) & page.rect
        canvas = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
        canvas.fill(QColor("black"))
        if not clip.is_empty:
            m = s * z * dpr
            pix = page.get_pixmap(matrix=pymupdf.Matrix(m, m), clip=clip, alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            px = (ox + clip.x0 * s) * z + self._pan.x()
            py = (oy + clip.y0 * s) * z + self._pan.y()
            qp = QPainter(canvas)
            qp.drawImage(int(round(px * dpr)), int(round(py * dpr)), img)
            qp.end()
        canvas.setDevicePixelRatio(dpr)
        self._zpix = (key, canvas)
        return canvas

    # ── ปากกา ──
    def _set_tool(self, tool: str | None) -> None:
        self._tool = None if tool == self._tool else tool
        if self._tool:
            self._laser = False
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            self._show_hud("ปากกา (D)" if self._tool == "pen" else "ไฮไลต์ (H)")
        else:
            self.unsetCursor()
            self._cursor_timer.start()
            self._show_hud("ปิดปากกา")
        self.update()

    def _tool_color(self) -> QColor:
        c = QColor(self.PEN_COLORS[self._ci % len(self.PEN_COLORS)])
        if self._tool == "hl":
            c = QColor(255, 235, 40) if self._ci % len(self.PEN_COLORS) == 0 else c
            c.setAlpha(110)
        return c

    def undo_stroke(self) -> None:
        strokes = self._ink.get(self.index)
        if strokes:
            strokes.pop()
            self.update()

    def clear_ink(self) -> None:
        if self._ink.pop(self.index, None) is not None:
            self.update()
            self._show_hud("ลบเส้นทั้งหน้าแล้ว")

    def _paint_ink(self, p: QPainter) -> None:
        strokes = list(self._ink.get(self.index, []))
        if self._cur is not None:
            strokes.append(self._cur)
        if not strokes:
            return
        p.save()
        p.translate(self._pan)
        p.scale(self._zoom, self._zoom)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for tool, col, pts in strokes:
            pen = QPen(col, 22 if tool == "hl" else 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap if tool == "pen" else Qt.PenCapStyle.FlatCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            if len(pts) == 1:
                p.drawPoint(pts[0])
            else:
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a, b)
        p.restore()

    def _prefetch(self) -> None:
        for j in (self.index + 1, self.index - 1):
            if 0 <= j < self.n:
                self._render(j)

    # ── เปลี่ยนหน้า ──
    def goto(self, i: int, direction: int | None = None) -> None:
        i = min(max(i, 0), self.n - 1)
        if self._anim is not None:                      # กดซ้ำระหว่างเอฟเฟกต์ → จบเอฟเฟกต์ทันทีแล้วไปต่อ
            self._finish_anim()
        self._ended = False
        if i != self.index:
            self._zoom, self._pan, self._zpix, self._cur = 1.0, QPointF(0, 0), None, None
        if i == self.index:
            self.update()
            return
        d = direction if direction is not None else (1 if i > self.index else -1)
        self._from = self._render(self.index)
        self.index = i
        self._to = self._render(i)
        self._dir = d
        self._black = self._white = False
        self._show_hud(f"{i + 1} / {self.n}")
        if self.opts.transition == "none" or self.opts.duration_ms <= 0:
            self._from = self._to = None
            self._t = 1.0
            self.update()
        else:
            self._t = 0.0
            self._anim = QVariantAnimation(self)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.setDuration(self.opts.duration_ms)
            self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self._anim.valueChanged.connect(self._on_anim)
            self._anim.finished.connect(self._finish_anim)
            self._anim.start()
        self._prefetch()
        if self.opts.auto_sec > 0:
            self._auto.start(int(self.opts.auto_sec * 1000))

    def _on_anim(self, v) -> None:
        self._t = float(v)
        self.update()

    def _finish_anim(self) -> None:
        if self._anim is not None:
            a, self._anim = self._anim, None
            a.stop()
            a.deleteLater()
        self._from = self._to = None
        self._t = 1.0
        self.update()

    def next(self) -> None:
        if self.index >= self.n - 1:
            if self.opts.loop:
                self.goto(0, 1)
            elif not self._ended:
                self._ended = True
                self._auto.stop()
                self.update()
            else:
                self.close()
            return
        self.goto(self.index + 1, 1)

    def prev(self) -> None:
        if self._ended:
            self._ended = False
            self.update()
            return
        self.goto(self.index - 1, -1)

    # ── วาด ──
    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("black"))
        W, H = self.width(), self.height()
        if self._white:
            p.fillRect(self.rect(), QColor("white"))
        elif not self._black:
            if self._ended:
                p.setPen(QColor("#B8B5D0"))
                f = QFont(self.font()); f.setPointSizeF(20); p.setFont(f)
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "จบการนำเสนอ\n\nคลิกหรือกด Esc เพื่อออก")
            elif self._anim is not None and self._from is not None and self._to is not None:
                t = self._t
                tr = self.opts.transition
                if tr == "fade":
                    p.setOpacity(1.0)
                    p.drawPixmap(0, 0, self._from)
                    p.setOpacity(t)
                    p.drawPixmap(0, 0, self._to)
                    p.setOpacity(1.0)
                elif tr == "slide":
                    off = int(W * t) * self._dir
                    p.drawPixmap(-off, 0, self._from)
                    p.drawPixmap(W * self._dir - off, 0, self._to)
                else:  # slide_up
                    off = int(H * t) * self._dir
                    p.drawPixmap(0, -off, self._from)
                    p.drawPixmap(0, H * self._dir - off, self._to)
            else:
                p.drawPixmap(0, 0, self._render_zoom() if self._zoom > 1.0 else self._render(self.index))
                self._paint_ink(p)
        if self._laser and self._mouse.x() >= 0:
            g = QRadialGradient(self._mouse, 20)
            g.setColorAt(0.0, QColor(255, 40, 40, 255))
            g.setColorAt(0.35, QColor(255, 40, 40, 200))
            g.setColorAt(1.0, QColor(255, 40, 40, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(self._mouse, 20, 20)
        if self._hud_text:
            f = QFont(self.font()); f.setPointSizeF(12); p.setFont(f)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(self._hud_text) + 28
            r = QRectF(W - tw - 22, H - 52, tw, 34)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(20, 18, 40, 190))
            p.drawRoundedRect(r, 17, 17)
            p.setPen(QColor("white"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._hud_text)
        p.end()

    def resizeEvent(self, ev):  # noqa: N802
        self._cache.clear()
        super().resizeEvent(ev)

    # ── HUD / เมาส์ ──
    def _show_hud(self, text: str) -> None:
        self._hud_text = text
        self._hud_timer.start()
        self.update()

    def _clear_hud(self) -> None:
        self._hud_text = ""
        self.update()

    def _hide_cursor(self) -> None:
        if not self._laser and self._tool is None:
            self.setCursor(QCursor(Qt.CursorShape.BlankCursor))

    def mouseMoveEvent(self, ev):  # noqa: N802
        self._mouse = ev.position().toPoint()
        if self._cur is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self._cur[2].append(self._to_base(self._mouse))
            self.update()
            return
        if self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            d = self._mouse - self._drag[0]
            if abs(d.x()) + abs(d.y()) > 4:
                self._moved = True
            if self._moved:
                self._pan = QPointF(self._drag[1].x() + d.x(), self._drag[1].y() + d.y())
                self._clamp_pan()
                self._zpix = None
                self.update()
            return
        if self._laser:
            self.setCursor(QCursor(Qt.CursorShape.BlankCursor))
            self.update()
        elif self._tool is None:
            self.unsetCursor()
            self._cursor_timer.start()

    def mousePressEvent(self, ev):  # noqa: N802
        pos = ev.position().toPoint()
        self._mouse = pos
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._tool and not self._ended and not self._black and not self._white and self._anim is None:
                self._cur = (self._tool, self._tool_color(), [self._to_base(pos)])
                self._cur = list(self._cur)
                return
            if self._zoom > 1.0:
                self._drag, self._moved = (pos, QPointF(self._pan)), False
                return
            self.next()
        elif ev.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.BackButton):
            self.prev()

    def mouseReleaseEvent(self, ev):  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._cur is not None:
                self._ink.setdefault(self.index, []).append(tuple(self._cur))
                self._cur = None
                self.update()
            self._drag = None

    def wheelEvent(self, ev):  # noqa: N802
        d = ev.angleDelta().y()
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self._zoom * (1.25 if d > 0 else 0.8), ev.position())
            return
        if d < 0:
            self.next()
        elif d > 0:
            self.prev()

    # ── คีย์ ──
    def keyPressEvent(self, ev):  # noqa: N802
        k = ev.key()
        if Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
            self._digits = (self._digits + chr(k))[-4:]
            self._show_hud(f"ไปหน้า {self._digits} ↵")
            return
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._digits:
            n, self._digits = int(self._digits), ""
            self.goto(n - 1)
            return
        self._digits = ""
        if k == Qt.Key.Key_Escape:
            self.close()
        elif k in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_N):
            self.next()
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backspace, Qt.Key.Key_P):
            self.prev()
        elif k == Qt.Key.Key_Home:
            self.goto(0, -1)
        elif k == Qt.Key.Key_End:
            self.goto(self.n - 1, 1)
        elif k == Qt.Key.Key_B:
            self._black, self._white = not self._black, False
            self.update()
        elif k == Qt.Key.Key_W:
            self._white, self._black = not self._white, False
            self.update()
        elif k == Qt.Key.Key_D:
            self._set_tool("pen")
        elif k == Qt.Key.Key_H:
            self._set_tool("hl")
        elif k == Qt.Key.Key_C:
            self._ci = (self._ci + 1) % len(self.PEN_COLORS)
            self._show_hud("เปลี่ยนสีปากกาแล้ว")
        elif k == Qt.Key.Key_U:
            self.undo_stroke()
        elif k == Qt.Key.Key_E:
            self.clear_ink()
        elif k == Qt.Key.Key_Z:
            self.set_zoom(1.0 if self._zoom > 1.0 else 2.5, QPointF(self._mouse) if self._mouse.x() >= 0 else None)
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.set_zoom(self._zoom * 1.25)
        elif k == Qt.Key.Key_Minus:
            self.set_zoom(self._zoom * 0.8)
        elif k == Qt.Key.Key_F:
            self.set_zoom(1.0)
        elif k == Qt.Key.Key_L:
            self._set_tool(None) if self._tool else None
            self._laser = not self._laser
            self.setCursor(QCursor(Qt.CursorShape.BlankCursor)) if self._laser else self.unsetCursor()
            self._show_hud("เลเซอร์พอยน์เตอร์ " + ("เปิด" if self._laser else "ปิด"))
        else:
            super().keyPressEvent(ev)
