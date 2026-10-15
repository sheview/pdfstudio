"""วิดเจ็ตสำเร็จรูป: ริบบิ้น, แถบสี, ภาพย่อ, ช่องค้นหา, หน้าต้อนรับ"""
from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QImage, QPainter, QPen, QPixmap
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
    QPushButton,
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
        name = QLabel("PDF <span style='font-weight:400;color:#697386'>Governix</span>")
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
        self.stack.setFixedHeight(96)
        root.addWidget(self.stack)
        self.tabbar.currentChanged.connect(self.stack.setCurrentIndex)

    def add_tab(self, title: str, groups: list[tuple[str, list[QAction | str]]]) -> None:
        """groups = [(ชื่อกลุ่ม, [action | "primary:ชื่อ"...])] — ใส่ action ที่ setProperty('primary', True) เพื่อทำปุ่มเด่น"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(12, 6, 12, 4)
        h.setSpacing(0)
        for gtitle, actions in groups:
            frame = QFrame()
            frame.setObjectName("RibbonGroup")
            v = QVBoxLayout(frame)
            v.setContentsMargins(6, 0, 6, 0)
            v.setSpacing(0)
            row = QHBoxLayout()
            row.setSpacing(2)
            for a in actions:
                btn = QToolButton()
                btn.setObjectName("RibbonPrimary" if a.property("primary") else "RibbonBtn")
                btn.setDefaultAction(a)
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                btn.setIconSize(QSize(28, 28))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                row.addWidget(btn)
            v.addLayout(row)
            lab = QLabel(gtitle)
            lab.setObjectName("RibbonGroupLabel")
            lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            v.addWidget(lab)
            h.addWidget(frame)
        h.addStretch(1)
        self.tabbar.addTab(title)
        self.stack.addWidget(page)


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
    reordered = Signal(list)
    deleteRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Thumbs")
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(THUMB_W, THUMB_CELL_H))
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setSpacing(0)

    def dropEvent(self, ev):  # noqa: N802
        super().dropEvent(ev)
        order = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        if order != sorted(order):
            QTimer.singleShot(0, lambda: self.reordered.emit(order))

    def keyPressEvent(self, ev):  # noqa: N802
        if ev.key() == Qt.Key.Key_Delete:
            self.deleteRequested.emit()
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
        t = QLabel("ยินดีต้อนรับสู่ PDF Governix")
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
