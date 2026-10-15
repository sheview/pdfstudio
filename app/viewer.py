"""ตัวแสดงผล PDF แบบเลื่อนต่อเนื่อง + เครื่องมือเมาส์ (เลือกข้อความ, ไฮไลต์, ลากกรอบ, วาด)"""
from __future__ import annotations

import bisect
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum

import pymupdf
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTextBoundaryFinder, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QFrame, QScrollArea, QWidget

from .theme import ACCENT, VIEW_BG

MARGIN = 28
GAP = 18
MIN_ZOOM, MAX_ZOOM = 0.1, 8.0
ACTUAL_ZOOM = 96 / 72   # "100%" = ขนาดจริงบนหน้าจอ 96 dpi (ตรงกับ Adobe Reader)
MAX_RENDER_PIXELS = 18_000_000
CACHE_BUDGET = 420 * 1024 * 1024


class Tool(str, Enum):
    SELECT = "select"
    HAND = "hand"
    HIGHLIGHT = "highlight"
    UNDERLINE = "underline"
    STRIKE = "strike"
    TEXT = "text"
    EDIT_TEXT = "edit_text"
    IMAGE = "image"
    PEN = "pen"
    ERASE = "erase"
    REDACT = "redact"


TEXT_TOOLS = {Tool.SELECT, Tool.HIGHLIGHT, Tool.UNDERLINE, Tool.STRIKE}
RECT_TOOLS = {Tool.TEXT, Tool.EDIT_TEXT, Tool.IMAGE, Tool.ERASE, Tool.REDACT}


# ───────────────────────── ดัชนีตัวอักษรของหน้า ─────────────────────────
@dataclass
class Ch:
    c: str
    u: pymupdf.Rect      # พิกัดก่อนหมุน (ใช้เขียนมาร์กอัป)
    v: QRectF            # พิกัดหลังหมุน (ใช้แสดงผล/หาตำแหน่งเมาส์)
    line: int


@dataclass
class PageText:
    chars: list[Ch] = field(default_factory=list)
    lines: list[tuple[int, int, QRectF]] = field(default_factory=list)  # (start, end, vbox)

    @classmethod
    def build(cls, page: pymupdf.Page) -> "PageText":
        pt = cls()
        rm = page.rotation_matrix
        try:
            d = page.get_text("rawdict")
        except Exception:
            return pt
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                start = len(pt.chars)
                lid = len(pt.lines)
                vbox: QRectF | None = None
                for span in line["spans"]:
                    for ch in span["chars"]:
                        u = pymupdf.Rect(ch["bbox"])
                        vr = (u * rm)
                        vr.normalize()
                        v = QRectF(vr.x0, vr.y0, vr.width, vr.height)
                        pt.chars.append(Ch(ch["c"], u, v, lid))
                        vbox = v if vbox is None else vbox.united(v)
                if len(pt.chars) > start and vbox is not None:
                    pt.lines.append((start, len(pt.chars), vbox))
        return pt

    @staticmethod
    def _dist(r: QRectF, p: QPointF) -> float:
        dx = max(r.left() - p.x(), 0.0, p.x() - r.right())
        dy = max(r.top() - p.y(), 0.0, p.y() - r.bottom())
        return dx * dx + dy * dy

    def hit(self, p: QPointF) -> int | None:
        if not self.lines:
            return None
        best = min(self.lines, key=lambda ln: self._dist(ln[2], p))
        s, e, _ = best
        bi, bd = s, 1e18
        for i in range(s, e):
            d = self._dist(self.chars[i].v, p)
            if d < bd:
                bi, bd = i, d
                if d == 0:
                    break
        return bi

    def text(self, a: int, b: int) -> str:
        out: list[str] = []
        last = None
        for ch in self.chars[a:b]:
            if last is not None and ch.line != last:
                out.append("\n")
            out.append(ch.c)
            last = ch.line
        return "".join(out)

    def line_boxes(self, a: int, b: int, vis: bool) -> list:
        """รวมกรอบตัวอักษรที่เลือกเป็นกรอบรายบรรทัด"""
        boxes: dict[int, object] = {}
        for ch in self.chars[a:b]:
            r = ch.v if vis else ch.u
            if ch.line in boxes:
                cur = boxes[ch.line]
                boxes[ch.line] = cur.united(r) if vis else (cur | r)  # type: ignore[operator]
            else:
                boxes[ch.line] = QRectF(r) if vis else pymupdf.Rect(r)
        return list(boxes.values())

    def word_range(self, idx: int) -> tuple[int, int]:
        ch = self.chars[idx]
        s, e, _ = self.lines[ch.line]
        try:
            text = "".join(c.c for c in self.chars[s:e])
            f = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Word, text)
            pos = idx - s
            f.setPosition(pos)
            a = pos if f.isAtBoundary() else f.toPreviousBoundary()
            f.setPosition(pos)
            b = f.toNextBoundary()
            if a < 0 or b < 0 or b <= a:
                return s, e
            return s + a, s + b
        except Exception:
            return s, e


# ───────────────────────── ตัวแสดงผล ─────────────────────────
class _Canvas(QWidget):
    def __init__(self, view: "PdfView"):
        super().__init__()
        self.setObjectName("Canvas")
        self.view = view
        self.setMouseTracking(False)

    def paintEvent(self, ev):  # noqa: N802
        self.view._paint(self, ev)

    def mousePressEvent(self, ev):  # noqa: N802
        self.view._press(ev)

    def mouseMoveEvent(self, ev):  # noqa: N802
        self.view._move(ev)

    def mouseReleaseEvent(self, ev):  # noqa: N802
        self.view._release(ev)

    def mouseDoubleClickEvent(self, ev):  # noqa: N802
        self.view._double_click(ev)

    def wheelEvent(self, ev):  # noqa: N802
        if not self.view._wheel(ev):
            ev.ignore()

    def contextMenuEvent(self, ev):  # noqa: N802
        self.view._context(ev)


class PdfView(QScrollArea):
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    selectionChanged = Signal(bool)
    rectDrawn = Signal(int, QRectF)        # หน้า, กรอบ (พิกัด pt หลังหมุน)
    inkDrawn = Signal(int, list)           # หน้า, จุด [(x, y)]
    markupReady = Signal(str)              # highlight | underline | strike
    contextRequested = Signal(QPoint, int, bool)
    fitModeChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Viewer")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.canvas = _Canvas(self)
        self.setWidget(self.canvas)
        self.setWidgetResizable(False)

        self.doc: pymupdf.Document | None = None
        self.sizes: list[tuple[float, float]] = []
        self.zoom = 1.0
        self.fit_mode = "width"       # width | page | custom
        self.tool = Tool.SELECT
        self.markup_color = QColor("#FFEB3B")
        self.pen_color = QColor("#E03131")
        self.pen_width = 2.5

        self.page_rects: list[QRectF] = []
        self.tops: list[float] = []
        self._cache: "OrderedDict[int, QPixmap]" = OrderedDict()
        self._cache_bytes = 0
        self._cache_key: tuple | None = None
        self._pending: list[int] = []
        self._render_scheduled = False
        self._text_cache: dict[int, PageText] = {}
        self._current = 0

        # สถานะเมาส์
        self._drag_page: int | None = None
        self._drag_start = QPointF()
        self._drag_now = QPointF()
        self._sel: tuple[int, int, int] | None = None     # (page, a, b) a<b ครึ่งเปิด
        self._anchor: int | None = None
        self._ink: list[QPointF] = []
        self._pan_origin: QPoint | None = None
        self._rubber: QRectF | None = None

        # ค้นหา
        self.hits: dict[int, list[QRectF]] = {}
        self.current_hit: tuple[int, int] | None = None

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._apply_cursor()

    # ───────── เอกสาร / เลย์เอาต์ ─────────
    def set_document(self, doc: pymupdf.Document | None, reset_view: bool = True) -> None:
        self.doc = doc
        self.clear_selection()
        self.hits.clear()
        self.current_hit = None
        self.reload(reset_view=reset_view)

    def reload(self, reset_view: bool = False) -> None:
        """เรียกหลังเนื้อหา/จำนวนหน้า/การหมุนเปลี่ยน"""
        self._cache.clear()
        self._cache_bytes = 0
        self._pending.clear()
        self._text_cache.clear()
        self._sel = None
        self.sizes = []
        if self.doc is not None:
            for i in range(self.doc.page_count):
                r = self.doc[i].rect
                self.sizes.append((max(r.width, 1.0), max(r.height, 1.0)))
        keep = self.verticalScrollBar().value()
        if self.fit_mode != "custom" and self.sizes:
            self._fit(self.fit_mode, emit=False)
        self._relayout()
        if not reset_view:
            self.verticalScrollBar().setValue(keep)
        else:
            self.verticalScrollBar().setValue(0)
        self._current = -1
        self._on_scroll()
        self.canvas.update()

    def invalidate(self, pages) -> None:
        """ล้างภาพที่แคชไว้เฉพาะหน้าที่เปลี่ยน (ไม่เปลี่ยนเลย์เอาต์)"""
        for i in pages:
            pm = self._cache.pop(i, None)
            if pm is not None:
                self._cache_bytes -= pm.width() * pm.height() * 4
            self._text_cache.pop(i, None)
            if i not in self._pending:
                self._pending.append(i)
        self._sel = None
        self._schedule()
        self.canvas.update()

    def _viewport_w(self) -> int:
        return max(self.viewport().width(), 200)

    def _relayout(self) -> None:
        n = len(self.sizes)
        z = self.zoom
        pw = [max(8, round(w * z)) for w, _ in self.sizes]
        ph = [max(8, round(h * z)) for _, h in self.sizes]
        content_w = (max(pw) if pw else 0) + 2 * MARGIN
        total_h = sum(ph) + GAP * max(n - 1, 0) + 2 * MARGIN
        cw = max(content_w, self._viewport_w())
        self.page_rects = []
        self.tops = []
        y = float(MARGIN)
        for i in range(n):
            x = (cw - pw[i]) / 2.0
            self.page_rects.append(QRectF(round(x), y, pw[i], ph[i]))
            self.tops.append(y)
            y += ph[i] + GAP
        self.canvas.setFixedSize(int(cw), int(max(total_h, 100)))
        self.canvas.update()

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        if not self.sizes:
            return
        QTimer.singleShot(0, self._after_resize)

    def _after_resize(self) -> None:
        if self.fit_mode != "custom":
            self._fit(self.fit_mode, emit=True)
        else:
            self._relayout()

    # ───────── ซูม ─────────
    def _fit(self, mode: str, emit: bool = True) -> None:
        if not self.sizes:
            return
        vw = self._viewport_w() - 2 * MARGIN
        if mode == "width":
            z = vw / max(w for w, _ in self.sizes)
        else:
            idx = max(self._current, 0) if 0 <= self._current < len(self.sizes) else 0
            w, h = self.sizes[idx]
            vh = max(self.viewport().height(), 200) - 2 * MARGIN
            z = min(vw / w, vh / h)
        self._apply_zoom(z, keep_anchor=True)
        if emit:
            self.zoomChanged.emit(self.zoom)

    def _apply_zoom(self, z: float, keep_anchor: bool = True, anchor: QPointF | None = None) -> None:
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        if abs(z - self.zoom) < 1e-4 and self.page_rects:
            return
        vbar, hbar = self.verticalScrollBar(), self.horizontalScrollBar()
        vp = self.viewport()
        old_h = max(self.canvas.height(), 1)
        old_w = max(self.canvas.width(), 1)
        ay = anchor.y() if anchor is not None else vbar.value() + vp.height() / 2
        ax = anchor.x() if anchor is not None else hbar.value() + vp.width() / 2
        ry, rx = ay / old_h, ax / old_w
        at_top = vbar.value() <= 2 and anchor is None
        off_y = ay - vbar.value()
        off_x = ax - hbar.value()
        self.zoom = z
        self._cache.clear()
        self._cache_bytes = 0
        self._pending.clear()
        self._relayout()
        if keep_anchor:
            if at_top:
                vbar.setValue(0)
            else:
                vbar.setValue(int(ry * self.canvas.height() - off_y))
            hbar.setValue(int(rx * self.canvas.width() - off_x))

    def set_zoom(self, z: float, anchor: QPointF | None = None) -> None:
        self.fit_mode = "custom"
        self.fitModeChanged.emit("custom")
        self._apply_zoom(z, anchor=anchor)
        self.zoomChanged.emit(self.zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * 1.2)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / 1.2)

    def fit_width(self) -> None:
        self.fit_mode = "width"
        self.fitModeChanged.emit("width")
        self._fit("width")

    def fit_page(self) -> None:
        self.fit_mode = "page"
        self.fitModeChanged.emit("page")
        self._fit("page")

    def actual_size(self) -> None:
        self.set_zoom(ACTUAL_ZOOM)

    # ───────── หน้า ─────────
    @property
    def page_count(self) -> int:
        return len(self.sizes)

    @property
    def current_page(self) -> int:
        return max(self._current, 0)

    def page_at_y(self, y: float) -> int:
        if not self.tops:
            return 0
        i = bisect.bisect_right(self.tops, y) - 1
        return max(0, min(i, len(self.tops) - 1))

    def go_to_page(self, i: int, emit: bool = True) -> None:
        if not self.page_rects:
            return
        i = max(0, min(i, len(self.page_rects) - 1))
        self.verticalScrollBar().setValue(int(self.tops[i] - GAP))
        if emit:
            self._on_scroll()

    def scroll_to_rect(self, page: int, rect: QRectF) -> None:
        if not (0 <= page < len(self.page_rects)):
            return
        pr = self.page_rects[page]
        s = pr.width() / self.sizes[page][0]
        cx = pr.left() + rect.center().x() * s
        cy = pr.top() + rect.center().y() * s
        self.ensureVisible(int(cx), int(cy), 120, 140)

    def _on_scroll(self, *_):
        if not self.page_rects:
            return
        y = self.verticalScrollBar().value() + self.viewport().height() * 0.35
        i = self.page_at_y(y)
        if i != self._current:
            self._current = i
            self.pageChanged.emit(i)
        self.canvas.update()

    # ───────── วาดภาพ ─────────
    def _visible_range(self, y0: float, y1: float) -> tuple[int, int]:
        if not self.page_rects:
            return 0, -1
        a = self.page_at_y(y0)
        b = self.page_at_y(y1)
        return a, b

    def _pixmap(self, i: int) -> QPixmap | None:
        key = (round(self.zoom, 4), round(self.canvas.devicePixelRatioF(), 2))
        if key != self._cache_key:
            self._cache.clear()
            self._cache_bytes = 0
            self._cache_key = key
        pm = self._cache.get(i)
        if pm is not None:
            self._cache.move_to_end(i)
            return pm
        if i not in self._pending:
            self._pending.append(i)
        self._schedule()
        return None

    def _schedule(self) -> None:
        if not self._render_scheduled:
            self._render_scheduled = True
            QTimer.singleShot(0, self._render_next)

    def _render_next(self) -> None:
        self._render_scheduled = False
        if self.doc is None or not self._pending:
            return
        vbar = self.verticalScrollBar()
        a, b = self._visible_range(vbar.value() - 40, vbar.value() + self.viewport().height() + 40)
        cand = [i for i in self._pending if a <= i <= b]
        if not cand:
            # ไม่อยู่ในจอแล้ว (ยกเว้นหน้าถัดไป/ก่อนหน้าที่โหลดล่วงหน้า)
            cand = [i for i in self._pending if a - 1 <= i <= b + 1]
        if not cand:
            self._pending.clear()
            return
        i = min(cand, key=lambda k: abs(k - self._current))
        self._pending.remove(i)
        try:
            self._cache_put(i, self._render(i))
            self.canvas.update(self.page_rects[i].toAlignedRect().adjusted(-4, -4, 4, 4))
        except Exception:
            pass
        if self._pending:
            self._schedule()
        else:
            # โหลดล่วงหน้าหน้าถัดไป/ก่อนหน้า
            for k in (b + 1, a - 1):
                if 0 <= k < len(self.page_rects) and k not in self._cache:
                    self._pending.append(k)
            if self._pending:
                self._schedule()

    def _render(self, i: int) -> QPixmap:
        assert self.doc is not None
        page = self.doc[i]
        r = self.page_rects[i]
        dpr = self.canvas.devicePixelRatioF()
        wpx, hpx = r.width() * dpr, r.height() * dpr
        if wpx * hpx > MAX_RENDER_PIXELS:
            k = (MAX_RENDER_PIXELS / (wpx * hpx)) ** 0.5
            wpx, hpx, dpr = wpx * k, hpx * k, dpr * k
        wpx, hpx = max(1, round(wpx)), max(1, round(hpx))
        mat = pymupdf.Matrix(wpx / page.rect.width, hpx / page.rect.height)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
        qp = QPixmap.fromImage(img)
        qp.setDevicePixelRatio(qp.width() / r.width())
        return qp

    def _cache_put(self, i: int, pm: QPixmap) -> None:
        self._cache[i] = pm
        self._cache_bytes += pm.width() * pm.height() * 4
        vbar = self.verticalScrollBar()
        a, b = self._visible_range(vbar.value(), vbar.value() + self.viewport().height())
        while self._cache_bytes > CACHE_BUDGET and len(self._cache) > 3:
            for k in list(self._cache.keys()):
                if not (a - 1 <= k <= b + 1):
                    old = self._cache.pop(k)
                    self._cache_bytes -= old.width() * old.height() * 4
                    break
            else:
                break

    def _paint(self, w: QWidget, ev) -> None:
        p = QPainter(w)
        p.fillRect(ev.rect(), QColor(VIEW_BG))
        if not self.page_rects:
            return
        a, b = self._visible_range(ev.rect().top(), ev.rect().bottom())
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        for i in range(a, b + 1):
            r = self.page_rects[i]
            if not r.intersects(QRectF(ev.rect())):
                continue
            # เงา
            p.setPen(Qt.PenStyle.NoPen)
            for grow, alpha, dy in ((7, 8, 4), (4, 14, 3), (2, 22, 2)):
                p.setBrush(QColor(20, 30, 60, alpha))
                p.drawRoundedRect(r.adjusted(-grow + 1, -grow + dy, grow - 1, grow + dy - 1), 3, 3)
            p.fillRect(r, QColor("white"))
            pm = self._pixmap(i)
            if pm is not None:
                p.drawPixmap(r.toRect(), pm)
            else:
                p.setPen(QColor("#9AA3B5"))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, "กำลังโหลด…")
            self._paint_overlays(p, i, r)

    def _scale(self, i: int) -> float:
        return self.page_rects[i].width() / self.sizes[i][0]

    def _to_canvas(self, i: int, r: QRectF) -> QRectF:
        pr, s = self.page_rects[i], self._scale(i)
        return QRectF(pr.left() + r.left() * s, pr.top() + r.top() * s, r.width() * s, r.height() * s)

    def _paint_overlays(self, p: QPainter, i: int, pr: QRectF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        # ผลค้นหา
        for k, hr in enumerate(self.hits.get(i, [])):
            cur = self.current_hit == (i, k)
            p.setBrush(QColor(255, 140, 0, 110) if cur else QColor(255, 235, 59, 120))
            p.drawRoundedRect(self._to_canvas(i, hr).adjusted(-1, -1, 1, 1), 2, 2)
        # ข้อความที่เลือก
        if self._sel and self._sel[0] == i:
            pt = self._text(i)
            p.setBrush(QColor(59, 91, 219, 80))
            for box in pt.line_boxes(self._sel[1], self._sel[2], vis=True):
                p.drawRect(self._to_canvas(i, box))
        # กรอบที่กำลังลาก
        if self._rubber is not None and self._drag_page == i:
            rr = self._to_canvas(i, self._rubber)
            col = QColor(ACCENT)
            fill = QColor(0, 0, 0, 90) if self.tool == Tool.REDACT else QColor(col.red(), col.green(), col.blue(), 35)
            p.setBrush(fill)
            p.setPen(QPen(col, 1.4, Qt.PenStyle.DashLine))
            p.drawRect(rr)
        # เส้นปากกาที่กำลังวาด
        if self._ink and self._drag_page == i and len(self._ink) > 1:
            pr_, s = self.page_rects[i], self._scale(i)
            path = QPainterPath(QPointF(pr_.left() + self._ink[0].x() * s, pr_.top() + self._ink[0].y() * s))
            for q in self._ink[1:]:
                path.lineTo(pr_.left() + q.x() * s, pr_.top() + q.y() * s)
            p.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(self.pen_color, self.pen_width * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPath(path)

    # ───────── เมาส์ ─────────
    def _text(self, i: int) -> PageText:
        pt = self._text_cache.get(i)
        if pt is None and self.doc is not None:
            pt = PageText.build(self.doc[i])
            self._text_cache[i] = pt
        return pt or PageText()

    def _locate(self, pos: QPointF, prefer: int | None = None) -> tuple[int, QPointF] | None:
        if not self.page_rects:
            return None
        if prefer is not None:
            i = prefer
        else:
            i = self.page_at_y(pos.y())
            if not self.page_rects[i].adjusted(-MARGIN, -GAP, MARGIN, GAP / 2).contains(pos):
                return None
        pr, s = self.page_rects[i], self._scale(i)
        return i, QPointF((pos.x() - pr.left()) / s, (pos.y() - pr.top()) / s)

    def set_tool(self, tool: Tool) -> None:
        self.tool = tool
        self._rubber = None
        self._ink = []
        if tool not in TEXT_TOOLS:
            self.clear_selection()
        self._apply_cursor()

    def _apply_cursor(self) -> None:
        t = self.tool
        if t == Tool.HAND:
            c = Qt.CursorShape.OpenHandCursor
        elif t in TEXT_TOOLS:
            c = Qt.CursorShape.IBeamCursor
        elif t in RECT_TOOLS or t == Tool.PEN:
            c = Qt.CursorShape.CrossCursor
        else:
            c = Qt.CursorShape.ArrowCursor
        self.canvas.setCursor(QCursor(c))

    def _press(self, ev) -> None:
        if ev.button() != Qt.MouseButton.LeftButton or self.doc is None:
            return
        pos = ev.position()
        self.setFocus()
        if self.tool == Tool.HAND:
            self._pan_origin = ev.globalPosition().toPoint()
            self.canvas.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            return
        loc = self._locate(pos)
        if loc is None:
            self.clear_selection()
            return
        i, pt = loc
        self._drag_page, self._drag_start, self._drag_now = i, pt, pt
        if self.tool in TEXT_TOOLS:
            idx = self._text(i).hit(pt)
            self._anchor = idx
            self.clear_selection(emit=False)
            self.selectionChanged.emit(False)
        elif self.tool == Tool.PEN:
            self._ink = [pt]
        else:
            self._rubber = QRectF(pt, pt)

    def _move(self, ev) -> None:
        if self._pan_origin is not None:
            d = ev.globalPosition().toPoint() - self._pan_origin
            self._pan_origin = ev.globalPosition().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            return
        if self._drag_page is None:
            return
        i = self._drag_page
        loc = self._locate(ev.position(), prefer=i)
        if loc is None:
            return
        _, pt = loc
        self._drag_now = pt
        pos = ev.position().toPoint()
        self.ensureVisible(pos.x(), pos.y(), 24, 24)
        if self.tool in TEXT_TOOLS:
            if self._anchor is None:
                return
            pt_idx = self._text(i).hit(pt)
            if pt_idx is None:
                return
            a, b = sorted((self._anchor, pt_idx))
            self._sel = (i, a, b + 1)
            self.canvas.update()
        elif self.tool == Tool.PEN:
            self._ink.append(pt)
            self.canvas.update()
        else:
            self._rubber = QRectF(self._drag_start, pt).normalized()
            self.canvas.update()

    def _release(self, ev) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        if self._pan_origin is not None:
            self._pan_origin = None
            self._apply_cursor()
            return
        i = self._drag_page
        if i is None:
            return
        self._drag_page = None
        if self.tool in TEXT_TOOLS:
            has = self._sel is not None and self._sel[2] > self._sel[1]
            self.selectionChanged.emit(has)
            if has and self.tool in (Tool.HIGHLIGHT, Tool.UNDERLINE, Tool.STRIKE):
                self.markupReady.emit(self.tool.value)
        elif self.tool == Tool.PEN:
            pts = [(q.x(), q.y()) for q in self._ink]
            self._ink = []
            if len(pts) >= 2:
                self.inkDrawn.emit(i, pts)
            self.canvas.update()
        else:
            r = self._rubber
            self._rubber = None
            self.canvas.update()
            if r is None:
                return
            if r.width() < 4 and r.height() < 4:
                if self.tool != Tool.TEXT:
                    return
                pw = self.sizes[i][0]
                r = QRectF(r.x(), r.y(), min(260.0, max(pw - r.x() - 10, 60.0)), 30.0)
            elif r.width() < 4 or r.height() < 4:
                return
            self.rectDrawn.emit(i, r)

    def _double_click(self, ev) -> None:
        if self.tool not in TEXT_TOOLS or self.doc is None:
            return
        loc = self._locate(ev.position())
        if loc is None:
            return
        i, pt = loc
        pt_text = self._text(i)
        idx = pt_text.hit(pt)
        if idx is None:
            return
        a, b = pt_text.word_range(idx)
        self._sel = (i, a, b)
        self.canvas.update()
        has = b > a
        self.selectionChanged.emit(has)
        if has and self.tool in (Tool.HIGHLIGHT, Tool.UNDERLINE, Tool.STRIKE):
            self.markupReady.emit(self.tool.value)

    def _wheel(self, ev) -> bool:
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = ev.angleDelta().y() / 120.0
            if steps:
                self.set_zoom(self.zoom * (1.15 ** steps), anchor=ev.position())
            return True
        return False

    def _context(self, ev) -> None:
        loc = self._locate(QPointF(ev.pos()))
        page = loc[0] if loc else self._current
        self.contextRequested.emit(ev.globalPos(), page, self.has_selection())

    # ───────── การเลือกข้อความ ─────────
    def has_selection(self) -> bool:
        return bool(self._sel and self._sel[2] > self._sel[1])

    def clear_selection(self, emit: bool = True) -> None:
        had = self._sel is not None
        self._sel = None
        self.canvas.update()
        if had and emit:
            self.selectionChanged.emit(False)

    def selected_text(self) -> str:
        if not self.has_selection():
            return ""
        i, a, b = self._sel  # type: ignore[misc]
        return self._text(i).text(a, b)

    def selection_quads(self) -> tuple[int, list[pymupdf.Quad]] | None:
        if not self.has_selection():
            return None
        i, a, b = self._sel  # type: ignore[misc]
        boxes = self._text(i).line_boxes(a, b, vis=False)
        return i, [r.quad for r in boxes]

    def copy_selection(self) -> bool:
        t = self.selected_text()
        if t:
            QGuiApplication.clipboard().setText(t)
            return True
        return False

    def select_all_current(self) -> None:
        if self.doc is None:
            return
        i = self.current_page
        n = len(self._text(i).chars)
        if n:
            self._sel = (i, 0, n)
            self.canvas.update()
            self.selectionChanged.emit(True)

    # ───────── ค้นหา ─────────
    def search(self, needle: str) -> list[tuple[int, int]]:
        """ค้นหาทั้งเอกสาร คืนรายการ (หน้า, ลำดับ) ตามลำดับการอ่าน"""
        self.hits.clear()
        self.current_hit = None
        order: list[tuple[int, int]] = []
        if self.doc is not None and needle.strip():
            for i in range(self.doc.page_count):
                page = self.doc[i]
                try:
                    found = page.search_for(needle)
                except Exception:
                    found = []
                if found:
                    rm = page.rotation_matrix
                    rects = []
                    for r in found:
                        v = pymupdf.Rect(r) * rm
                        v.normalize()
                        rects.append(QRectF(v.x0, v.y0, v.width, v.height))
                    self.hits[i] = rects
                    order.extend((i, k) for k in range(len(rects)))
        self.canvas.update()
        return order

    def show_hit(self, hit: tuple[int, int] | None) -> None:
        self.current_hit = hit
        if hit is not None:
            i, k = hit
            self.scroll_to_rect(i, self.hits[i][k])
        self.canvas.update()

    def clear_search(self) -> None:
        self.hits.clear()
        self.current_hit = None
        self.canvas.update()

    # ───────── ส่งออกภาพหน้าจอ (สำหรับทดสอบ) ─────────
    def snapshot(self) -> QPixmap:
        return self.viewport().grab()
