"""หน้าต่างหลัก: ริบบิ้นคำสั่ง, แท็บเอกสาร, แถบสถานะ"""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QIntValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import APP_NAME, MAX_RECENT, SETTINGS_APP, SETTINGS_ORG
from .dialogs import MergeDialog, ask_password, show_about
from .doctab import DocTab
from .icons import icon
from .model import PdfModel
from .textrender import TextStyle, default_thai_font
from .theme import ACCENT, MUTED
from .viewer import ACTUAL_ZOOM, Tool
from .widgets import OptionsBar, Ribbon, WelcomePage

PDF_FILTER = "PDF และรูปภาพ (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;PDF (*.pdf);;ทุกไฟล์ (*.*)"
ACCEPT_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


class MainWindow(QMainWindow):
    def __init__(self, files: list[str] | None = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.resize(1360, 860)
        self.setMinimumSize(980, 620)
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        # สถานะเครื่องมือ
        self.tool = Tool.SELECT
        self.markup_color = QColor(self.settings.value("markup_color", "#FFEB3B"))
        self.line_color = QColor(self.settings.value("line_color", "#E03131"))
        self.pen_color = QColor(self.settings.value("pen_color", "#E03131"))
        self.pen_width = float(self.settings.value("pen_width", 2.5))
        self.text_style = self._load_text_style()
        self.doc_actions: list[QAction] = []
        self.tool_actions: dict[Tool, QAction] = {}

        self._build_actions()
        self._build_ui()
        self._build_statusbar()
        self._build_shortcuts()
        self.update_state()
        self.welcome.set_recent(self.recent_files())
        g = self.settings.value("geometry")
        if g:
            self.restoreGeometry(g)
        if files:
            self.open_files(files)

    # ───────────────────────── การตั้งค่า ─────────────────────────
    def _load_text_style(self) -> TextStyle:
        try:
            d = json.loads(self.settings.value("text_style", "{}"))
            st = TextStyle(**{k: v for k, v in d.items() if k in {f.name for f in dataclasses.fields(TextStyle)}})
        except Exception:
            st = TextStyle()
        if not st.family:
            st.family = default_thai_font()
        return st

    def text_style_copy(self) -> TextStyle:
        return dataclasses.replace(self.text_style)

    def remember_text_style(self, st: TextStyle) -> None:
        self.text_style = dataclasses.replace(st)
        self.settings.setValue("text_style", json.dumps(dataclasses.asdict(st)))

    def start_dir(self) -> str:
        d = self.settings.value("last_dir", "")
        if d and os.path.isdir(d):
            return d
        docs = Path.home() / "Documents"
        return str(docs if docs.exists() else Path.home())

    def remember_dir(self, path: str) -> None:
        self.settings.setValue("last_dir", str(Path(path).parent))

    def recent_files(self) -> list[str]:
        r = self.settings.value("recent", [])
        if isinstance(r, str):
            r = [r]
        return [p for p in (r or []) if os.path.exists(p)]

    def remember_recent(self, path: str) -> None:
        self.remember_dir(path)
        r = [p for p in self.recent_files() if os.path.normcase(p) != os.path.normcase(path)]
        r.insert(0, path)
        self.settings.setValue("recent", r[:MAX_RECENT])
        self.welcome.set_recent(self.recent_files())

    # ───────────────────────── สร้างคำสั่ง ─────────────────────────
    def _act(self, text: str, ic: str, slot, shortcut=None, tip: str | None = None,
             checkable: bool = False, doc: bool = True, primary: bool = False) -> QAction:
        a = QAction(icon(ic, "white" if primary else "#3A4257", "white" if primary else ACCENT), text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut) if isinstance(shortcut, str) else shortcut)
        sc = a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        a.setToolTip((tip or text) + (f"  ({sc})" if sc else ""))
        a.setCheckable(checkable)
        a.setProperty("primary", primary)
        a.triggered.connect(lambda _=False, f=slot: f())
        self.addAction(a)
        if doc:
            self.doc_actions.append(a)
        return a

    def _tool_act(self, tool: Tool, text: str, ic: str, tip: str, shortcut=None) -> QAction:
        a = self._act(text, ic, lambda t=tool: self.set_tool(t), shortcut, tip, checkable=True)
        self.tool_group.addAction(a)
        self.tool_actions[tool] = a
        return a

    def _build_actions(self) -> None:
        T = self._tab_call
        # ไฟล์
        self.act_open = self._act("เปิดไฟล์", "folder-open-outline", self.open_dialog, "Ctrl+O", "เปิดไฟล์ PDF หรือรูปภาพ", doc=False)
        self.act_save = self._act("บันทึก", "content-save-outline", T("save"), "Ctrl+S", "บันทึกไฟล์")
        self.act_save_as = self._act("บันทึกเป็น", "content-save-edit-outline", T("save_as"), "Ctrl+Shift+S", "บันทึกเป็นไฟล์ใหม่")
        self.act_close = self._act("ปิดไฟล์", "close-box-outline", self.close_current, "Ctrl+W", "ปิดไฟล์ที่เปิดอยู่")
        self.act_print = self._act("พิมพ์", "printer-outline", T("print_"), "Ctrl+P", "พิมพ์เอกสาร")
        self.act_preview = self._act("ตัวอย่างพิมพ์", "printer-eye", T("print_preview"), None, "ดูตัวอย่างก่อนพิมพ์")
        self.act_merge = self._act("รวมไฟล์", "file-document-multiple-outline", self.merge, "Ctrl+M",
                                   "รวมหลายไฟล์ PDF เป็นไฟล์เดียว", doc=False, primary=True)
        self.act_undo = self._act("ย้อนกลับ", "undo", self.undo, "Ctrl+Z", "ย้อนกลับการแก้ไขล่าสุด")
        self.act_redo = self._act("ทำซ้ำ", "redo", self.redo, "Ctrl+Y", "ทำซ้ำสิ่งที่ย้อนกลับ")
        # มุมมอง
        self.act_zoom_in = self._act("ซูมเข้า", "magnify-plus-outline", T("view.zoom_in"), "Ctrl+=", "ซูมเข้า")
        self.act_zoom_out = self._act("ซูมออก", "magnify-minus-outline", T("view.zoom_out"), "Ctrl+-", "ซูมออก")
        self.act_fit_width = self._act("พอดีกว้าง", "arrow-expand-horizontal", T("view.fit_width"), "Ctrl+0", "ปรับให้พอดีความกว้างหน้าจอ")
        self.act_fit_page = self._act("พอดีหน้า", "fit-to-page-outline", T("view.fit_page"), "Ctrl+9", "ปรับให้เห็นทั้งหน้า")
        self.act_actual = self._act("ขนาดจริง", "numeric-1-box-outline", T("view.actual_size"), "Ctrl+1", "แสดงที่ 100%")
        self.act_find = self._act("ค้นหา", "text-search", T("open_search"), "Ctrl+F", "ค้นหาข้อความในเอกสาร")
        self.act_thumbs = self._act("ภาพย่อ", "page-layout-sidebar-left", self.toggle_thumbs, "F4", "แสดง/ซ่อนแผงภาพย่อ", checkable=True)
        self.act_thumbs.setChecked(True)
        # เลือก/คัดลอก
        self.act_copy = self._act("คัดลอกข้อความ", "content-copy", self.copy, "Ctrl+C", "คัดลอกข้อความที่เลือก")
        self.act_select_all = self._act("เลือกทั้งหน้า", "select-all", self.select_all, "Ctrl+A", "เลือกข้อความทั้งหน้า")
        self.act_highlight_sel = self._act("ไฮไลต์ข้อความที่เลือก", "marker", lambda: self._tab_call("apply_markup_to_selection")("highlight"))
        self.act_underline_sel = self._act("ขีดเส้นใต้ข้อความที่เลือก", "format-underline", lambda: self._tab_call("apply_markup_to_selection")("underline"))
        self.act_strike_sel = self._act("ขีดฆ่าข้อความที่เลือก", "format-strikethrough", lambda: self._tab_call("apply_markup_to_selection")("strike"))
        # เครื่องมือ
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.act_t_select = self._tool_act(Tool.SELECT, "เลือก", "cursor-text", "เลือก/คัดลอกข้อความ", "V")
        self.act_t_hand = self._tool_act(Tool.HAND, "เลื่อน", "hand-back-right-outline", "ลากเพื่อเลื่อนหน้า (มือ)", "H")
        self.act_t_hl = self._tool_act(Tool.HIGHLIGHT, "ไฮไลต์", "marker", "ไฮไลต์ข้อความ", "1")
        self.act_t_ul = self._tool_act(Tool.UNDERLINE, "ขีดเส้นใต้", "format-underline", "ขีดเส้นใต้ข้อความ", "2")
        self.act_t_st = self._tool_act(Tool.STRIKE, "ขีดฆ่า", "format-strikethrough", "ขีดฆ่าข้อความ", "3")
        self.act_t_text = self._tool_act(Tool.TEXT, "ใส่ข้อความ", "format-text-variant", "ใส่ข้อความใหม่ลงบนหน้า", "T")
        self.act_t_img = self._tool_act(Tool.IMAGE, "แทรกรูป", "image-plus-outline", "แทรกรูปภาพ/ลายเซ็น", "I")
        self.act_t_pen = self._tool_act(Tool.PEN, "วาดเส้น", "draw", "วาดเส้นอิสระ/เซ็นชื่อ", "P")
        self.act_t_edit = self._tool_act(Tool.EDIT_TEXT, "แก้ข้อความ", "text-box-edit-outline", "แก้ไขข้อความเดิมในเอกสาร", "E")
        self.act_t_erase = self._tool_act(Tool.ERASE, "ลบ/ปิดทับ", "eraser", "ลบเนื้อหาในกรอบ (เทสีพื้นหลัง)", "X")
        self.act_t_redact = self._tool_act(Tool.REDACT, "ปิดข้อมูลลับ", "card-account-details-star-outline", "ลบข้อมูลถาวรและปิดด้วยแถบดำ", "R")
        self.act_t_select.setChecked(True)
        # หน้า
        self.act_rotate_left = self._act("หมุนซ้าย", "rotate-left", lambda: self._tab_call("rotate")(-90), "Ctrl+L", "หมุนหน้าที่เลือกทวนเข็มนาฬิกา")
        self.act_rotate_right = self._act("หมุนขวา", "rotate-right", lambda: self._tab_call("rotate")(90), "Ctrl+R", "หมุนหน้าที่เลือกตามเข็มนาฬิกา")
        self.act_delete = self._act("ลบหน้า", "delete-outline", T("delete_pages"), "Ctrl+Del", "ลบหน้าที่เลือก")
        self.act_insert_blank = self._act("แทรกหน้าว่าง", "file-plus-outline", T("insert_blank"), None, "แทรกหน้าว่างหลังหน้าที่เลือก")
        self.act_duplicate = self._act("ทำสำเนาหน้า", "content-duplicate", T("duplicate"), None, "ทำสำเนาหน้าที่เลือก")
        self.act_move_up = self._act("เลื่อนขึ้น", "arrow-up-bold-outline", lambda: self._tab_call("move")(-1), None, "เลื่อนหน้าที่เลือกขึ้น")
        self.act_move_down = self._act("เลื่อนลง", "arrow-down-bold-outline", lambda: self._tab_call("move")(1), None, "เลื่อนหน้าที่เลือกลง")
        self.act_insert_pdf = self._act("แทรกจากไฟล์", "file-import-outline", T("insert_pdf"), None, "แทรกหน้าจากไฟล์ PDF/รูปภาพอื่น")
        self.act_split = self._act("แยกหน้า", "file-export-outline", T("split_pages"), None, "แยกบางหน้าออกเป็นไฟล์ใหม่")
        self.act_export_img = self._act("ส่งออกเป็นรูป", "image-multiple-outline", T("export_images"), None, "ส่งออกหน้าเป็นไฟล์รูปภาพ")
        self.act_about = self._act("เกี่ยวกับ", "information-outline", lambda: show_about(self), None, "เกี่ยวกับโปรแกรม", doc=False)

    def _tab_call(self, name: str):
        """คืนฟังก์ชันที่เรียกเมธอดของแท็บปัจจุบัน (รองรับ 'view.xxx')"""
        def run(*args):
            tab = self.current_tab()
            if tab is None:
                return None
            obj = tab
            for part in name.split("."):
                obj = getattr(obj, part)
            return obj(*args)
        return run

    # ───────────────────────── สร้างหน้าจอ ─────────────────────────
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.ribbon = Ribbon()
        A = self
        self.ribbon.add_tab("หน้าแรก", [
            ("ไฟล์", [A.act_open, A.act_save, A.act_save_as, A.act_close]),
            ("พิมพ์", [A.act_print, A.act_preview]),
            ("รวม", [A.act_merge]),
            ("ประวัติ", [A.act_undo, A.act_redo]),
            ("มุมมอง", [A.act_zoom_in, A.act_zoom_out, A.act_fit_width, A.act_fit_page, A.act_find, A.act_thumbs]),
        ])
        self.ribbon.add_tab("แก้ไข", [
            ("เครื่องมือ", [A.act_t_select, A.act_t_hand]),
            ("มาร์กอัป", [A.act_t_hl, A.act_t_ul, A.act_t_st]),
            ("แทรก", [A.act_t_text, A.act_t_img, A.act_t_pen]),
            ("แก้ไข / ลบ", [A.act_t_edit, A.act_t_erase, A.act_t_redact]),
            ("ประวัติ", [A.act_undo, A.act_redo]),
        ])
        self.ribbon.add_tab("จัดการหน้า", [
            ("หมุน", [A.act_rotate_left, A.act_rotate_right]),
            ("จัดหน้า", [A.act_insert_blank, A.act_duplicate, A.act_delete, A.act_move_up, A.act_move_down]),
            ("ไฟล์อื่น", [A.act_insert_pdf, A.act_split, A.act_export_img]),
            ("รวม", [A.act_merge]),
        ])
        about = QToolButton()
        about.setDefaultAction(self.act_about)
        about.setIconSize(QSize(22, 22))
        self.ribbon.top_right.addWidget(about)
        lay.addWidget(self.ribbon)

        self.options = OptionsBar()
        self.options.markup.set_color(self.markup_color)
        self.options.line.set_color(self.line_color)
        self.options.pen.set_color(self.pen_color)
        self.options.width.setValue(self.pen_width)
        self.options.markupColorChanged.connect(lambda c: self._set_color("markup_color", c))
        self.options.lineColorChanged.connect(lambda c: self._set_color("line_color", c))
        self.options.penColorChanged.connect(lambda c: self._set_color("pen_color", c))
        self.options.penWidthChanged.connect(self._set_pen_width)
        lay.addWidget(self.options)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.welcome = WelcomePage()
        self.welcome.openRequested.connect(self.open_dialog)
        self.welcome.mergeRequested.connect(self.merge)
        self.welcome.recentRequested.connect(lambda p: self.open_files([p]))
        self.stack.addWidget(self.welcome)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("DocTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.stack.addWidget(self.tabs)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.msg = QLabel("พร้อมใช้งาน")
        self.msg.setStyleSheet(f"color:{MUTED}; padding-left:10px;")
        sb.addWidget(self.msg, 1)

        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 2, 12, 2)
        h.setSpacing(6)
        lbl = QLabel("หน้า")
        lbl.setStyleSheet(f"color:{MUTED};")
        self.page_spin = QLineEdit("1")
        self.page_spin.setValidator(QIntValidator(1, 99999))
        self.page_spin.setFixedWidth(56)
        self.page_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_spin.editingFinished.connect(self._page_entered)
        self.page_total = QLabel("/ 0")
        self.page_total.setStyleSheet(f"color:{MUTED};")
        for w in (lbl, self.page_spin, self.page_total):
            h.addWidget(w)
        h.addSpacing(18)
        zo = self._small_btn("minus", "ซูมออก", self.act_zoom_out)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.valueChanged.connect(lambda v: self._tab_call("view.set_zoom")(v / 75.0))
        zi = self._small_btn("plus", "ซูมเข้า", self.act_zoom_in)
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setFixedWidth(46)
        self.zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fw = self._small_btn("arrow-expand-horizontal", "พอดีกว้าง", self.act_fit_width)
        fp = self._small_btn("fit-to-page-outline", "พอดีหน้า", self.act_fit_page)
        for w in (zo, self.zoom_slider, zi, self.zoom_lbl, fw, fp):
            h.addWidget(w)
        sb.addPermanentWidget(box)

    def _page_entered(self) -> None:
        t = self.current_tab()
        if t and self.page_spin.text().isdigit():
            n = max(1, min(int(self.page_spin.text()), t.model.page_count))
            t.go_to_page(n - 1)
            self.page_spin.setText(str(n))
            t.view.setFocus()

    def _small_btn(self, ic: str, tip: str, action: QAction) -> QToolButton:
        b = QToolButton()
        b.setIcon(icon(ic))
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.clicked.connect(action.trigger)
        return b

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.on_escape)
        QShortcut(QKeySequence("Ctrl+Tab"), self, activated=lambda: self._cycle_tab(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, activated=lambda: self._cycle_tab(-1))

    # ───────────────────────── แท็บ ─────────────────────────
    def current_tab(self) -> DocTab | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, DocTab) and self.stack.currentWidget() is self.tabs else None

    def all_tabs(self) -> list[DocTab]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]  # type: ignore[misc]

    def _cycle_tab(self, d: int) -> None:
        n = self.tabs.count()
        if n > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + d) % n)

    def add_tab(self, model: PdfModel) -> DocTab:
        tab = DocTab(model, self)
        i = self.tabs.addTab(tab, "")
        tab.titleChanged.connect(lambda t=tab: self._refresh_tab_title(t))
        tab.stateChanged.connect(self.update_state)
        tab.message.connect(self.show_message)
        self._refresh_tab_title(tab)
        self.stack.setCurrentWidget(self.tabs)
        self.tabs.setCurrentIndex(i)
        return tab

    def _refresh_tab_title(self, tab: DocTab) -> None:
        i = self.tabs.indexOf(tab)
        if i < 0:
            return
        self.tabs.setTabText(i, tab.title())
        self.tabs.setTabToolTip(i, tab.model.path or "ยังไม่ได้บันทึก")
        if tab is self.current_tab():
            self._update_window_title()

    def _update_window_title(self) -> None:
        t = self.current_tab()
        self.setWindowTitle(f"{t.title()} — {APP_NAME}" if t else APP_NAME)

    def _on_tab_changed(self, _=None) -> None:
        t = self.current_tab()
        if t:
            t.apply_tool_state()
        self.update_state()

    def close_tab(self, index: int) -> None:
        tab = self.tabs.widget(index)
        if not isinstance(tab, DocTab) or not tab.maybe_save():
            return
        self.tabs.removeTab(index)
        tab.deleteLater()
        if self.tabs.count() == 0:
            self.stack.setCurrentWidget(self.welcome)
            self.welcome.set_recent(self.recent_files())
        self.update_state()

    def close_current(self) -> None:
        if self.tabs.count():
            self.close_tab(self.tabs.currentIndex())

    # ───────────────────────── เปิดไฟล์ ─────────────────────────
    def open_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "เปิดไฟล์", self.start_dir(), PDF_FILTER)
        if files:
            self.open_files(files)

    def open_files(self, paths: list[str]) -> None:
        for p in paths:
            p = str(Path(p))
            if not os.path.exists(p):
                QMessageBox.warning(self, "ไม่พบไฟล์", p)
                continue
            for i, t in enumerate(self.all_tabs()):
                if t.model.path and os.path.normcase(os.path.abspath(t.model.path)) == os.path.normcase(os.path.abspath(p)):
                    self.stack.setCurrentWidget(self.tabs)
                    self.tabs.setCurrentIndex(i)
                    break
            else:
                model = self._load_model(p)
                if model is not None:
                    self.add_tab(model)
                    if model.path:
                        self.remember_recent(model.path)

    def _load_model(self, path: str) -> PdfModel | None:
        pw = None
        for _ in range(3):
            try:
                return PdfModel.open_path(path, pw)
            except PermissionError:
                pw = ask_password(self, Path(path).name)
                if pw is None:
                    return None
            except Exception as e:
                QMessageBox.warning(self, "เปิดไฟล์ไม่ได้", f"{Path(path).name}\n\nไฟล์อาจเสียหายหรือไม่ใช่ไฟล์ PDF\n({e})")
                return None
        QMessageBox.warning(self, "รหัสผ่านไม่ถูกต้อง", "ใส่รหัสผ่านผิดหลายครั้ง")
        return None

    def merge(self) -> None:
        initial: list[str] = []
        t = self.current_tab()
        if t and t.model.path and not t.model.dirty:
            initial.append(t.model.path)
        dlg = MergeDialog(self, initial, self.start_dir())
        if dlg.exec() == MergeDialog.DialogCode.Accepted and dlg.result_path:
            self.remember_dir(dlg.result_path)
            self.show_message(f"รวมไฟล์สำเร็จ ({dlg.result_pages} หน้า): {dlg.result_path}")
            if dlg.chk_open.isChecked():
                self.open_files([dlg.result_path])

    # ───────────────────────── คำสั่งทั่วไป ─────────────────────────
    def undo(self) -> None:
        t = self.current_tab()
        if t:
            t.model.undo()

    def redo(self) -> None:
        t = self.current_tab()
        if t:
            t.model.redo()

    def copy(self) -> None:
        t = self.current_tab()
        if t and t.view.copy_selection():
            self.show_message("คัดลอกข้อความแล้ว")

    def select_all(self) -> None:
        t = self.current_tab()
        if t:
            t.view.select_all_current()

    def toggle_thumbs(self) -> None:
        on = self.act_thumbs.isChecked()
        for t in self.all_tabs():
            t.thumb_panel.setVisible(on)

    def on_escape(self) -> None:
        t = self.current_tab()
        if not t:
            return
        if t.search_wrap.isVisible():
            t.close_search()
        elif self.tool != Tool.SELECT or t.view.has_selection():
            t.view.clear_selection()
            self.set_tool(Tool.SELECT)

    def show_message(self, text: str) -> None:
        self.msg.setText(text)

    # ───────────────────────── เครื่องมือ ─────────────────────────
    def set_tool(self, tool: Tool) -> None:
        self.tool = tool
        self.tool_actions[tool].setChecked(True)
        self.options.set_tool(tool.value)
        for t in self.all_tabs():
            t.view.set_tool(tool)
        self.update_state()

    def _set_color(self, attr: str, c: QColor) -> None:
        setattr(self, attr, QColor(c))
        self.settings.setValue(attr, c.name())
        for t in self.all_tabs():
            t.apply_tool_state()

    def _set_pen_width(self, w: float) -> None:
        self.pen_width = w
        self.settings.setValue("pen_width", w)
        for t in self.all_tabs():
            t.apply_tool_state()

    # ───────────────────────── อัปเดตสถานะปุ่ม ─────────────────────────
    def update_state(self) -> None:
        t = self.current_tab()
        has = t is not None
        for a in self.doc_actions:
            a.setEnabled(has)
        self.options.setVisible(has)
        self._update_window_title()
        if not has:
            self.page_spin.setEnabled(False)
            self.zoom_slider.setEnabled(False)
            self.zoom_lbl.setText("")
            self.page_total.setText("/ 0")
            return
        m, v = t.model, t.view
        self.act_undo.setEnabled(m.can_undo())
        self.act_redo.setEnabled(m.can_redo())
        sel = v.has_selection()
        for a in (self.act_copy, self.act_highlight_sel, self.act_underline_sel, self.act_strike_sel):
            a.setEnabled(sel)
        self.act_save.setEnabled(True)
        sp = self.page_spin
        sp.setEnabled(True)
        if not sp.hasFocus():
            sp.setText(str(v.current_page + 1))
        self.page_total.setText(f"/ {m.page_count}")
        pct = max(10, min(400, round(v.zoom * 75)))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setEnabled(True)
        self.zoom_slider.setValue(pct)
        self.zoom_slider.blockSignals(False)
        self.zoom_lbl.setText(f"{pct}%")
        self.act_thumbs.setChecked(t.thumb_panel.isVisible())

    # ───────────────────────── ลากไฟล์มาวาง ─────────────────────────
    def _urls_ok(self, ev) -> bool:
        return ev.mimeData().hasUrls() and any(
            Path(u.toLocalFile()).suffix.lower() in ACCEPT_EXT for u in ev.mimeData().urls() if u.isLocalFile()
        )

    def dragEnterEvent(self, ev):  # noqa: N802
        if self._urls_ok(ev):
            ev.acceptProposedAction()
            if self.stack.currentWidget() is self.welcome:
                self.welcome.set_drag(True)

    def dragLeaveEvent(self, ev):  # noqa: N802
        self.welcome.set_drag(False)

    def dropEvent(self, ev):  # noqa: N802
        self.welcome.set_drag(False)
        files = [u.toLocalFile() for u in ev.mimeData().urls()
                 if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in ACCEPT_EXT]
        if files:
            ev.acceptProposedAction()
            self.open_files(files)

    # ───────────────────────── ปิดโปรแกรม ─────────────────────────
    def closeEvent(self, ev):  # noqa: N802
        for t in self.all_tabs():
            self.tabs.setCurrentWidget(t)
            if not t.maybe_save():
                ev.ignore()
                return
        self.settings.setValue("geometry", self.saveGeometry())
        ev.accept()
