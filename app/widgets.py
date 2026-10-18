"""วิดเจ็ตสำเร็จรูป: ริบบิ้น, แถบสี, ภาพย่อ, ช่องค้นหา, หน้าต้อนรับ"""
from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import APP_NAME, COPYRIGHT
from .icons import icon
from .theme import ACCENT, BORDER, BORDER_STRONG, MUTED

SWATCHES_MARKUP = ["#FFEB3B", "#A5F28B", "#7DD3FC", "#F9A8D4", "#FDBA74", "#C4B5FD"]
SWATCHES_PEN = ["#E03131", "#1C7ED6", "#2F9E44", "#F59F00", "#212529", "#7048E8"]
SWATCHES_TEXT = ["#000000", "#E03131", "#1C7ED6", "#2F9E44", "#F59F00", "#7048E8"]


# ───────────────────────── แถบเลือกสี ─────────────────────────
class ColorRow(QWidget):
    colorChanged = Signal(QColor)

    def __init__(self, colors: list[str], current: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._buttons: list[tuple[QToolButton, str]] = []
        for c in colors:
            lay.addWidget(self._make(c))
        self.custom = QToolButton()
        self.custom.setIcon(icon("palette-outline"))
        self.custom.setToolTip("เลือกสีอื่น…")
        self.custom.clicked.connect(self._pick)
        lay.addWidget(self.custom)
        self._current = QColor(current)
        self.set_color(current)

    def _make(self, c: str) -> QToolButton:
        b = QToolButton()
        b.setObjectName("Swatch")
        b.setCheckable(True)
        b.setStyleSheet(f"QToolButton#Swatch{{background:{c};}}")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False, col=c: self.set_color(col, emit=True))
        self._buttons.append((b, c))
        return b

    def set_color(self, color: str | QColor, emit: bool = False) -> None:
        q = QColor(color)
        self._current = q
        for b, c in self._buttons:
            b.setChecked(QColor(c).name().lower() == q.name().lower())
        if emit:
            self.colorChanged.emit(q)

    def color(self) -> QColor:
        return QColor(self._current)

    def _pick(self) -> None:
        c = QColorDialog.getColor(self._current, self.window(), "เลือกสี")
        if c.isValid():
            self.set_color(c, emit=True)


class _HScroll(QScrollArea):
    resized = Signal()
    """พื้นที่เลื่อนแนวนอนสำหรับริบบิ้น — โปร่งใส แถบเลื่อนบาง ลูกกลิ้งเมาส์เลื่อนซ้าย-ขวา"""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget#RibbonPage{background:transparent;}"
                           "QScrollBar:horizontal{height:8px;background:transparent;margin:0 12px;}"
                           "QScrollBar::handle:horizontal{background:#C9CCE0;border-radius:4px;min-width:40px;}"
                           "QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;}"
                           "QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{background:transparent;}")
        self.viewport().setAutoFillBackground(False)

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        self.resized.emit()

    def wheelEvent(self, ev):  # noqa: N802
        bar = self.horizontalScrollBar()
        d = ev.angleDelta().y() or ev.angleDelta().x()
        bar.setValue(bar.value() - d)
        ev.accept()


# ───────────────────────── ริบบิ้น ─────────────────────────
class Ribbon(QWidget):
    """แถบคำสั่งแบบแท็บ + กลุ่มปุ่ม (คล้าย Office)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Header")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(16, 6, 16, 0)
        top.setSpacing(6)
        logo = QLabel()
        logo.setPixmap(icon("file-pdf-box", ACCENT, ACCENT).pixmap(30, 30))
        top.addWidget(logo)
        name = QLabel("Governix <span style='font-weight:400;color:#697386'>PDF</span>")
        name.setObjectName("Logo")
        name.setTextFormat(Qt.TextFormat.RichText)
        top.addWidget(name)
        self.tabbar = QTabBar()
        self.tabbar.setObjectName("RibbonTabs")
        self.tabbar.setDrawBase(False)
        self.tabbar.setExpanding(False)
        self.tabbar.setCursor(Qt.CursorShape.PointingHandCursor)
        top.addWidget(self.tabbar)
        top.addStretch(1)
        self.top_right = QHBoxLayout()
        top.addLayout(self.top_right)
        root.addLayout(top)

        self.stack = QStackedWidget()
        self.stack.setObjectName("RibbonBody")
        self.stack.setFixedHeight(106)
        root.addWidget(self.stack)
        self.tabbar.currentChanged.connect(self.stack.setCurrentIndex)
        self.tabbar.currentChanged.connect(lambda _i: self._relayout_all())
        self._tabs: list[dict] = []

    def add_tab(self, title: str, groups: list[tuple[str, list[QAction | str]]]) -> None:
        """groups = [(ชื่อกลุ่ม, [action | "primary:ชื่อ"...])] — ใส่ action ที่ setProperty('primary', True) เพื่อทำปุ่มเด่น"""
        page = QWidget()
        page.setObjectName("RibbonPage")
        h = QHBoxLayout(page)
        h.setContentsMargins(12, 6, 12, 4)
        h.setSpacing(0)
        info = {"area": None, "items": [], "frames": [], "more": None}
        for gtitle, actions in groups:
            frame = QFrame()
            frame.setObjectName("RibbonGroup")
            v = QVBoxLayout(frame)
            v.setContentsMargins(6, 0, 6, 0)
            v.setSpacing(0)
            row = QHBoxLayout()
            row.setSpacing(2)
            gitems = []
            for a in actions:
                low = isinstance(a, tuple)          # ("low", action) = เมนูรอง ย้ายเข้า "เพิ่มเติม" เมื่อจอแคบ
                if low:
                    a = a[1]
                btn = QToolButton()
                btn.setObjectName("RibbonPrimary" if a.property("primary") else "RibbonBtn")
                btn.setDefaultAction(a)
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                btn.setIconSize(QSize(28, 28))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)   # ไม่บีบจนข้อความถูกตัด/ทับกัน
                f = QFont(QApplication.font())
                f.setPointSizeF(9.5)      # ขนาดตัวอักษรตาม stylesheet ของปุ่มริบบิ้น (ยังไม่ถูก apply ตอนสร้าง)
                f.setWeight(QFont.Weight.DemiBold)
                tw = QFontMetrics(f).horizontalAdvance(a.text().replace("&", "")) * 1.04
                btn.setFixedWidth(max(66, int(tw) + 20))
                row.addWidget(btn)
                gitems.append({"btn": btn, "action": a, "low": low, "w": btn.width() or max(66, int(tw) + 20)})
                info["items"].append(gitems[-1])
            info["frames"].append((frame, gitems))
            v.addLayout(row)
            lab = QLabel(gtitle)
            lab.setObjectName("RibbonGroupLabel")
            lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            v.addWidget(lab)
            h.addWidget(frame)
        # ปุ่ม "เพิ่มเติม" รวมเมนูรองเมื่อจอแคบ
        more = QToolButton()
        more.setObjectName("RibbonBtn")
        more.setText("เพิ่มเติม")
        more.setIcon(icon("dots-horizontal", ACCENT, ACCENT))
        more.setIconSize(QSize(28, 28))
        more.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        more.setFixedWidth(76)
        more.setMenu(QMenu(more))
        more.setStyleSheet("QToolButton::menu-indicator{image:none;}")
        more.hide()
        h.addWidget(more)
        info["more"] = more
        h.addStretch(1)
        # จอเล็ก: เลื่อนริบบิ้นแนวนอนแทนการบีบปุ่มให้ทับกัน (ลูกกลิ้งเมาส์เลื่อนได้)
        area = _HScroll()
        area.setWidget(page)
        info["area"] = area
        info["page"] = page
        self._tabs.append(info)
        area.resized.connect(self._relayout_all)
        self.tabbar.addTab(title)
        self.stack.addWidget(area)

    def _relayout_all(self) -> None:
        for info in self._tabs:
            self._relayout(info)

    def _relayout(self, info: dict) -> None:
        """จอแคบ: เก็บปุ่มรอง (low) ที่อยู่ขวาสุดเข้าเมนู "เพิ่มเติม" ทีละปุ่มจนพอดี"""
        avail = info["area"].viewport().width()
        if avail < 100:                      # แท็บยังไม่ถูกแสดง / ยังไม่มีขนาดจริง
            return
        page, more = info["page"], info["more"]

        def measure() -> int:
            """คำนวณความกว้างรวมเอง (cache ของ layout ไม่อัปเดตทันทีหลังซ่อนปุ่ม)"""
            total = 54                                   # margin ซ้าย-ขวาของหน้าริบบิ้น
            for fr, gitems in info["frames"]:
                vis = [g["btn"].width() for g in gitems if not g["btn"].isHidden()]
                if not vis:
                    continue
                lab = fr.findChild(QLabel)
                total += max(sum(vis) + 2 * (len(vis) - 1), lab.sizeHint().width() if lab else 0) + 13
            if not more.isHidden():
                total += more.width() + 8
            return total

        def compact(on: bool) -> None:
            style = Qt.ToolButtonStyle.ToolButtonIconOnly if on else Qt.ToolButtonStyle.ToolButtonTextUnderIcon
            for it in info["items"]:
                it["btn"].setToolButtonStyle(style)
                it["btn"].setFixedWidth(46 if on else it["w"])
            more.setToolButtonStyle(style)
            more.setFixedWidth(46 if on else 76)

        compact(False)
        for it in info["items"]:
            it["btn"].show()
        for frame, _ in info["frames"]:
            frame.show()
        more.hide()
        hidden: list = []
        if measure() > avail:
            more.show()
            for it in reversed(info["items"]):
                if not it["low"]:
                    continue
                it["btn"].hide()
                hidden.append(it)
                for frame, gitems in info["frames"]:
                    if all(g["btn"].isHidden() for g in gitems):
                        frame.hide()
                if measure() <= avail:
                    break
            if measure() > avail:                 # ยังแคบอยู่ → เหลือแต่ไอคอน (วางเมาส์ดูชื่อได้)
                compact(True)
            if not hidden:
                more.hide()
        menu = more.menu()
        menu.clear()
        for it in reversed(hidden):          # เรียงตามลำดับเดิมบนริบบิ้น
            menu.addAction(it["action"])
        more.setVisible(bool(hidden))


# ───────────────────────── แถบตัวเลือกเครื่องมือ ─────────────────────────
class OptionsBar(QWidget):
    markupColorChanged = Signal(QColor)
    lineColorChanged = Signal(QColor)
    penColorChanged = Signal(QColor)
    penWidthChanged = Signal(float)

    HINTS = {
        "select": "ลากคลุมข้อความเพื่อคัดลอก • คลิกรูป/กล่องข้อความเพื่อเลือก ลากย้าย ลากมุมปรับขนาด กด Delete ลบ",
        "hand": "ลากเพื่อเลื่อนหน้าเอกสาร • หมุนลูกกลิ้งเมาส์เพื่อเลื่อน • Ctrl + ลูกกลิ้ง เพื่อซูม",
        "highlight": "ลากคลุมข้อความที่ต้องการไฮไลต์ — ทำเครื่องหมายทันทีเมื่อปล่อยเมาส์",
        "underline": "ลากคลุมข้อความที่ต้องการขีดเส้นใต้",
        "strike": "ลากคลุมข้อความที่ต้องการขีดฆ่า",
        "text": "คลิกหรือลากกรอบเพื่อวางข้อความ • วางแล้วลากย้ายได้ ลากมุมย่อ/ขยาย ดับเบิลคลิกเพื่อแก้ไข",
        "edit_text": "คลิกที่ย่อหน้าเดิมเพื่อแก้/ลบ (หรือลากกรอบเลือกเฉพาะส่วน) • ผลที่ได้เป็นกล่องข้อความ ย้าย/แก้ต่อได้",
        "image": "คลิกตำแหน่งที่ต้องการวางรูป/ลายเซ็น • วางแล้วลากย้าย ลากมุมปรับขนาด (กด Shift ที่มุม = ยืดอิสระ)",
        "pen": "กดค้างแล้วลากเพื่อวาดเส้นอิสระ — ใช้เซ็นชื่อหรือวงกลมจุดสำคัญ",
        "erase": "ลากกรอบคลุมส่วนที่ต้องการลบ — เนื้อหาในกรอบจะถูกลบออกจริงแล้วเทสีพื้นหลัง",
        "redact": "ลากกรอบคลุมข้อมูลลับ — ลบเนื้อหาออกถาวรและปิดด้วยแถบสีดำ",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OptionsBar")
        self.setFixedHeight(42)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)
        self.icon_lbl = QLabel()
        lay.addWidget(self.icon_lbl)
        self.hint = QLabel()
        self.hint.setObjectName("OptionsLabel")
        lay.addWidget(self.hint)
        lay.addStretch(1)

        self.markup_lbl = QLabel("สี:")
        self.markup_lbl.setObjectName("OptionsLabel")
        self.markup = ColorRow(SWATCHES_MARKUP, SWATCHES_MARKUP[0])
        self.markup.colorChanged.connect(self.markupColorChanged)
        self.line_lbl = QLabel("สี:")
        self.line_lbl.setObjectName("OptionsLabel")
        self.line = ColorRow(SWATCHES_PEN, SWATCHES_PEN[0])
        self.line.colorChanged.connect(self.lineColorChanged)
        self.pen_lbl = QLabel("สี:")
        self.pen_lbl.setObjectName("OptionsLabel")
        self.pen = ColorRow(SWATCHES_PEN, SWATCHES_PEN[0])
        self.pen.colorChanged.connect(self.penColorChanged)
        self.width_lbl = QLabel("ความหนา:")
        self.width_lbl.setObjectName("OptionsLabel")
        self.width = QDoubleSpinBox()
        self.width.setRange(0.5, 20)
        self.width.setSingleStep(0.5)
        self.width.setValue(2.5)
        self.width.setSuffix(" pt")
        self.width.setFixedWidth(88)
        self.width.valueChanged.connect(self.penWidthChanged)
        for w in (self.markup_lbl, self.markup, self.line_lbl, self.line, self.pen_lbl, self.pen, self.width_lbl, self.width):
            lay.addWidget(w)
        self.set_tool("select")

    def set_tool(self, key: str) -> None:
        self.hint.setText(self.HINTS.get(key, ""))
        self.icon_lbl.setPixmap(icon("information-outline", MUTED, MUTED).pixmap(18, 18))
        m = key == "highlight"
        ln = key in ("underline", "strike")
        p = key == "pen"
        for w in (self.markup_lbl, self.markup):
            w.setVisible(m)
        for w in (self.line_lbl, self.line):
            w.setVisible(ln)
        for w in (self.pen_lbl, self.pen, self.width_lbl, self.width):
            w.setVisible(p)


# ───────────────────────── ภาพย่อหน้า ─────────────────────────
THUMB_W, THUMB_H = 128, 176
THUMB_LABEL_H = 22
THUMB_CELL_H = THUMB_H + THUMB_LABEL_H


class ThumbList(QListWidget):
    """แผงภาพย่อหน้า — ลากสลับ/ย้ายหน้าด้วยเมาส์ (เขียนการลากเองแทน drag&drop ของ Qt เพื่อให้ทำงานเหมือนกันทุกเครื่อง)"""
    reordered = Signal(list, list)          # (ลำดับใหม่ = เลขหน้าเดิมเรียงตามลำดับใหม่, ตำแหน่งใหม่ของหน้าที่ย้าย)
    deleteRequested = Signal()

    DRAG_START_PX = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Thumbs")
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(THUMB_W, THUMB_CELL_H))
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QListWidget.DragDropMode.NoDragDrop)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setSpacing(0)
        self._press: QPoint | None = None
        self._press_row = -1
        self._dragging = False
        self._insert: int | None = None          # ตำแหน่งแทรก 0..n (ก่อนแถวที่ n)
        self._scroll = QTimer(self)
        self._scroll.setInterval(30)
        self._scroll.timeout.connect(self._auto_scroll)
        self._scroll_dir = 0

    # ── คำนวณตำแหน่งแทรกจากตำแหน่งเมาส์ ──
    def _insert_index(self, pos: QPoint) -> int:
        n = self.count()
        if n == 0:
            return 0
        it = self.itemAt(pos)
        if it is not None:
            r = self.visualItemRect(it)
            row = self.row(it)
            return row if pos.y() < r.center().y() else row + 1
        last = self.visualItemRect(self.item(n - 1))
        return n if pos.y() > last.bottom() else 0

    def mousePressEvent(self, ev):  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._press = ev.position().toPoint()
            it = self.itemAt(self._press)
            self._press_row = self.row(it) if it is not None else -1
            self._dragging = False
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):  # noqa: N802
        if self._press is not None and (ev.buttons() & Qt.MouseButton.LeftButton) and self._press_row >= 0:
            pos = ev.position().toPoint()
            if not self._dragging and (pos - self._press).manhattanLength() >= self.DRAG_START_PX:
                if not self.item(self._press_row).isSelected():       # ลากหน้าที่ยังไม่ได้เลือก → เลือกเฉพาะหน้านั้น
                    self.clearSelection()
                    self.item(self._press_row).setSelected(True)
                self._dragging = True
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                self._scroll.start()
            if self._dragging:
                self._insert = self._insert_index(pos)
                h = self.viewport().height()
                self._scroll_dir = -1 if pos.y() < 28 else (1 if pos.y() > h - 28 else 0)
                self.viewport().update()
                return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):  # noqa: N802
        was = self._dragging
        target = self._insert
        self._reset_drag()
        if was and ev.button() == Qt.MouseButton.LeftButton and target is not None:
            self._drop(target)
            return
        super().mouseReleaseEvent(ev)

    def _reset_drag(self) -> None:
        self._press = None
        self._press_row = -1
        self._dragging = False
        self._insert = None
        self._scroll.stop()
        self.viewport().unsetCursor()
        self.viewport().update()

    def _auto_scroll(self) -> None:
        if self._dragging and self._scroll_dir:
            sb = self.verticalScrollBar()
            sb.setValue(sb.value() + self._scroll_dir * 18)
            pos = self.viewport().mapFromGlobal(QCursor.pos())
            self._insert = self._insert_index(pos)
            self.viewport().update()

    def _drop(self, target: int) -> None:
        n = self.count()
        pages = sorted(self.row(it) for it in self.selectedItems())
        if not pages:
            return
        rest = [i for i in range(n) if i not in pages]
        k = sum(1 for i in rest if i < target)
        order = rest[:k] + pages + rest[k:]
        if order == list(range(n)):
            return                                  # วางที่เดิม — ไม่มีอะไรเปลี่ยน
        moved = list(range(k, k + len(pages)))
        self.reordered.emit(order, moved)

    def paintEvent(self, ev):  # noqa: N802
        super().paintEvent(ev)
        if not self._dragging or self._insert is None or self.count() == 0:
            return
        n = self.count()
        i = min(self._insert, n)
        r = self.visualItemRect(self.item(i if i < n else n - 1))
        y = r.top() if i < n else r.bottom()
        p = QPainter(self.viewport())
        col = QColor(ACCENT)
        p.setPen(QPen(col, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(8, y, self.viewport().width() - 8, y)
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPoint(8, y), 4, 4)
        p.drawEllipse(QPoint(self.viewport().width() - 8, y), 4, 4)
        p.end()

    def keyPressEvent(self, ev):  # noqa: N802
        if ev.key() == Qt.Key.Key_Delete:
            self.deleteRequested.emit()
            return
        if ev.key() == Qt.Key.Key_Escape and self._dragging:
            self._reset_drag()
            return
        super().keyPressEvent(ev)

    def selected_pages(self) -> list[int]:
        return sorted(it.data(Qt.ItemDataRole.UserRole) for it in self.selectedItems())


def make_thumb_pixmap(page: pymupdf.Page, number: int, dpr: float = 1.0) -> QPixmap:
    """ภาพย่อ 1 หน้า (กรอบคงที่) พร้อมเลขหน้าด้านล่าง"""
    r = page.rect
    s = min(THUMB_W / r.width, THUMB_H / r.height)
    w, h = max(1, int(r.width * s)), max(1, int(r.height * s))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(s * dpr, s * dpr), alpha=False)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    canvas = QPixmap(int(THUMB_W * dpr), int(THUMB_CELL_H * dpr))
    canvas.setDevicePixelRatio(dpr)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    x, y = (THUMB_W - w) / 2, (THUMB_H - h) / 2
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(20, 30, 60, 28))
    p.drawRoundedRect(int(x) - 1, int(y) + 1, w + 3, h + 3, 3, 3)
    p.drawPixmap(int(x), int(y), pm)
    p.setPen(QPen(QColor(BORDER_STRONG), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(int(x), int(y), w - 1, h - 1)
    p.setPen(QColor(MUTED))
    f = QFont(p.font())
    f.setPointSizeF(9.5)
    p.setFont(f)
    p.drawText(QRectF(0, THUMB_H + 2, THUMB_W, THUMB_LABEL_H - 2), Qt.AlignmentFlag.AlignCenter, str(number))
    p.end()
    return canvas


def make_thumb_placeholder(number: int, dpr: float = 1.0) -> QPixmap:
    canvas = QPixmap(int(THUMB_W * dpr), int(THUMB_CELL_H * dpr))
    canvas.setDevicePixelRatio(dpr)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setPen(QColor(MUTED))
    p.drawText(QRectF(0, THUMB_H + 2, THUMB_W, THUMB_LABEL_H - 2), Qt.AlignmentFlag.AlignCenter, str(number))
    p.end()
    return canvas


# ───────────────────────── แถบค้นหา ─────────────────────────
class SearchBar(QWidget):
    searchRequested = Signal(str)
    nextRequested = Signal()
    prevRequested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        lay.setSpacing(6)
        lay.addWidget(self._lbl(icon("magnify")))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("ค้นหาข้อความในเอกสาร…")
        self.edit.setFixedWidth(260)
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(self._enter)
        lay.addWidget(self.edit)
        self.count = QLabel("")
        self.count.setObjectName("OptionsLabel")
        self.count.setMinimumWidth(70)
        lay.addWidget(self.count)
        self.btn_prev = self._tb("chevron-up", "ก่อนหน้า (Shift+Enter)", self.prevRequested)
        self.btn_next = self._tb("chevron-down", "ถัดไป (Enter)", self.nextRequested)
        close = self._tb("close", "ปิด (Esc)", self.closed)
        for b in (self.btn_prev, self.btn_next, close):
            lay.addWidget(b)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(lambda: self.searchRequested.emit(self.edit.text()))
        self.edit.textChanged.connect(lambda _: self._timer.start())

    def _lbl(self, ic) -> QLabel:
        l = QLabel()
        l.setPixmap(ic.pixmap(18, 18))
        return l

    def _tb(self, name: str, tip: str, sig) -> QToolButton:
        b = QToolButton()
        b.setIcon(icon(name))
        b.setToolTip(tip)
        b.clicked.connect(sig)
        return b

    def _enter(self) -> None:
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.prevRequested.emit()
        else:
            self.nextRequested.emit()

    def focus_edit(self) -> None:
        self.edit.setFocus()
        self.edit.selectAll()

    def set_count(self, cur: int, total: int, text: str) -> None:
        if not text:
            self.count.setText("")
        elif total == 0:
            self.count.setText("ไม่พบ")
        else:
            self.count.setText(f"{cur} / {total}")

    def keyPressEvent(self, ev):  # noqa: N802
        if ev.key() == Qt.Key.Key_Escape:
            self.closed.emit()
            return
        super().keyPressEvent(ev)


# ───────────────────────── หน้าต้อนรับ ─────────────────────────
class WelcomePage(QWidget):
    openRequested = Signal()
    mergeRequested = Signal()
    recentRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Welcome")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch(1)
        self.card = QFrame()
        self.card.setObjectName("WelcomeCard")
        self.card.setProperty("drag", False)
        self.card.setMaximumWidth(760)
        self.card.setMinimumWidth(520)
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(48, 40, 48, 36)
        cl.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icon("file-pdf-box", ACCENT, ACCENT).pixmap(84, 84))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(ic)
        t = QLabel("ยินดีต้อนรับสู่ Governix PDF")
        t.setObjectName("WelcomeTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(t)
        s = QLabel("ดู แก้ไข รวมไฟล์ และพิมพ์ PDF ได้ในที่เดียว\nลากไฟล์ PDF มาวางตรงนี้ หรือกดปุ่มด้านล่างเพื่อเริ่มต้น")
        s.setObjectName("WelcomeSub")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(s)
        cl.addSpacing(14)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addStretch(1)
        b1 = QPushButton("  เปิดไฟล์ PDF")
        b1.setObjectName("BigBtn")
        b1.setIcon(icon("folder-open-outline", "white", "white"))
        b1.setIconSize(QSize(22, 22))
        b1.setCursor(Qt.CursorShape.PointingHandCursor)
        b1.clicked.connect(self.openRequested)
        b2 = QPushButton("  รวมไฟล์ PDF")
        b2.setObjectName("BigBtnAlt")
        b2.setIcon(icon("file-document-multiple-outline"))
        b2.setIconSize(QSize(22, 22))
        b2.setCursor(Qt.CursorShape.PointingHandCursor)
        b2.clicked.connect(self.mergeRequested)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        cl.addLayout(row)
        cl.addSpacing(12)
        self.recent_title = QLabel("ไฟล์ที่เปิดล่าสุด")
        self.recent_title.setObjectName("RecentTitle")
        cl.addWidget(self.recent_title)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(0)
        cl.addLayout(self.recent_box)

        mid = QHBoxLayout()
        mid.addStretch(1)
        mid.addWidget(self.card, 10)
        mid.addStretch(1)
        outer.addLayout(mid)
        outer.addStretch(2)
        foot = QLabel(f"{APP_NAME}  •  {COPYRIGHT}")
        foot.setObjectName("WelcomeFoot")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(foot)

    def set_recent(self, paths: list[str]) -> None:
        while self.recent_box.count():
            it = self.recent_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.recent_title.setVisible(bool(paths))
        for p in paths[:5]:
            name = Path(p).name
            btn = QPushButton(f"{name}   —   {Path(p).parent}")
            btn.setObjectName("Link")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(p)
            btn.clicked.connect(lambda _=False, path=p: self.recentRequested.emit(path))
            fm = btn.fontMetrics()
            btn.setText(fm.elidedText(btn.text(), Qt.TextElideMode.ElideMiddle, 600))
            self.recent_box.addWidget(btn)

    def set_drag(self, on: bool) -> None:
        self.card.setProperty("drag", on)
        self.card.style().unpolish(self.card)
        self.card.style().polish(self.card)
