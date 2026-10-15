"""หน้าต่างโต้ตอบ: ใส่/แก้ข้อความ, รวมไฟล์, แยกหน้า, แทรก PDF, ส่งออกภาพ, เกี่ยวกับ"""
from __future__ import annotations

import os
from pathlib import Path

import pymupdf
from PySide6.QtCore import QFileInfo, QSettings, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QFontDatabase, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import ops
from .config import APP_NAME, APP_VERSION, COPYRIGHT, ORG_NAME
from .fontpick import FontCombo, SizeCombo
from .icons import icon
from .textrender import TextStyle, default_thai_font
from .theme import ACCENT, MUTED
from .utils import format_size, parse_page_range, thai_date, thai_date_short
from .widgets import SWATCHES_TEXT, ColorRow


def _buttons(dlg: QDialog, ok_text: str = "ตกลง", cancel_text: str = "ยกเลิก") -> QDialogButtonBox:
    box = QDialogButtonBox()
    ok = box.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
    ok.setObjectName("Primary")
    ok.setDefault(True)
    box.addButton(cancel_text, QDialogButtonBox.ButtonRole.RejectRole)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    return box


def _title(text: str, sub: str = "") -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 4)
    v.setSpacing(2)
    t = QLabel(text)
    t.setStyleSheet("font-size:14pt;font-weight:700;")
    v.addWidget(t)
    if sub:
        s = QLabel(sub)
        s.setStyleSheet(f"color:{MUTED};")
        s.setWordWrap(True)
        v.addWidget(s)
    return w


def ask_password(parent, filename: str) -> str | None:
    pw, ok = QInputDialog.getText(
        parent, "ไฟล์นี้มีรหัสผ่าน", f"ใส่รหัสผ่านสำหรับ\n{filename}", QLineEdit.EchoMode.Password
    )
    return pw if ok else None


# ───────────────────────── ใส่ / แก้ข้อความ ─────────────────────────
class TextDialog(QDialog):
    def __init__(self, parent, title: str, text: str = "", style: TextStyle | None = None, sub: str = "",
                 deletable: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self.deleted = False
        st = style or TextStyle()
        if not st.family:
            st.family = default_thai_font()
        self._style = st

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(_title(title, sub))

        row = QHBoxLayout()
        row.setSpacing(8)
        self.font_box = FontCombo(st.family)
        self.size_box = SizeCombo(st.size)
        row.addWidget(self.font_box, 1)
        row.addWidget(self.size_box)
        row.addWidget(QLabel("pt"))
        self.b_bold = self._toggle("format-bold", "ตัวหนา", st.bold)
        self.b_italic = self._toggle("format-italic", "ตัวเอียง", st.italic)
        self.b_under = self._toggle("format-underline", "ขีดเส้นใต้", st.underline)
        for b in (self.b_bold, self.b_italic, self.b_under):
            row.addWidget(b)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        lab = QLabel("สี")
        lab.setStyleSheet(f"color:{MUTED};")
        row2.addWidget(lab)
        self.colors = ColorRow(SWATCHES_TEXT, st.color)
        row2.addWidget(self.colors)
        row2.addSpacing(10)
        self.aligns: dict[str, QToolButton] = {}
        for key, ic, tip in (("left", "format-align-left", "ชิดซ้าย"), ("center", "format-align-center", "กึ่งกลาง"), ("right", "format-align-right", "ชิดขวา")):
            b = self._toggle(ic, tip, st.align == key)
            b.setAutoExclusive(True)
            b.clicked.connect(lambda _=False, k=key: self._set_align(k))
            self.aligns[key] = b
            row2.addWidget(b)
        row2.addStretch(1)
        date_btn = QToolButton()
        date_btn.setText(" แทรกวันที่")
        date_btn.setIcon(icon("calendar-today"))
        date_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        date_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m = QMenu(date_btn)
        m.addAction(f"{thai_date()}  (วัน เดือน พ.ศ.)").triggered.connect(lambda: self._insert(thai_date()))
        m.addAction(f"{thai_date_short()}  (วว/ดด/พ.ศ.)").triggered.connect(lambda: self._insert(thai_date_short()))
        import datetime as _dt
        m.addAction(f"{_dt.date.today():%d/%m/%Y}  (ค.ศ.)").triggered.connect(lambda: self._insert(f"{_dt.date.today():%d/%m/%Y}"))
        date_btn.setMenu(m)
        row2.addWidget(date_btn)
        lay.addLayout(row2)

        self.edit = QPlainTextEdit()
        self.edit.setPlainText(text)
        self.edit.setMinimumHeight(150)
        self.edit.setPlaceholderText("พิมพ์ข้อความที่ต้องการ… (กด Enter เพื่อขึ้นบรรทัดใหม่)")
        lay.addWidget(self.edit, 1)
        btns = _buttons(self, "ตกลง")
        if deletable:
            d = btns.addButton("ลบข้อความนี้", QDialogButtonBox.ButtonRole.DestructiveRole)
            d.setObjectName("Danger")
            d.clicked.connect(self._delete)
        lay.addWidget(btns)

        self.font_box.changed.connect(self._sync)
        self.size_box.changed.connect(self._sync)
        self.colors.colorChanged.connect(self._sync)
        for b in (self.b_bold, self.b_italic, self.b_under):
            b.toggled.connect(self._sync)
        self._align = st.align
        self._sync()
        self.edit.setFocus()
        self.edit.selectAll()

    def _delete(self) -> None:
        self.deleted = True
        self.accept()

    def _toggle(self, ic: str, tip: str, on: bool) -> QToolButton:
        b = QToolButton()
        b.setIcon(icon(ic))
        b.setToolTip(tip)
        b.setCheckable(True)
        b.setChecked(on)
        b.setIconSize(QSize(20, 20))
        return b

    def _set_align(self, k: str) -> None:
        self._align = k
        self._sync()

    def _insert(self, s: str) -> None:
        self.edit.insertPlainText(s)
        self.edit.setFocus()

    def _sync(self, *_):
        st = self.style_value()
        f = st.qfont()
        # แสดงตัวอย่างในช่องพิมพ์ให้ใกล้เคียงของจริง (pt → px ที่ 96 dpi)
        f.setPointSizeF(max(8.0, min(st.size, 40.0)))
        self.edit.setFont(f)
        self.edit.setStyleSheet(f"QPlainTextEdit{{color:{st.color};}}")
        opt = self.edit.document().defaultTextOption()
        opt.setAlignment({"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter, "right": Qt.AlignmentFlag.AlignRight}[self._align])
        self.edit.document().setDefaultTextOption(opt)

    def style_value(self) -> TextStyle:
        return TextStyle(
            family=self.font_box.family(),
            size=self.size_box.value(),
            color=self.colors.color().name(),
            bold=self.b_bold.isChecked(),
            italic=self.b_italic.isChecked(),
            underline=self.b_under.isChecked(),
            align=self._align,
        )

    def text_value(self) -> str:
        return self.edit.toPlainText()


# ───────────────────────── รวมไฟล์ ─────────────────────────
class MergeDialog(QDialog):
    COLS = ["ลำดับ", "ชื่อไฟล์", "จำนวนหน้า", "ช่วงหน้าที่ใช้ (เว้นว่าง = ทั้งหมด)", "ขนาด"]

    def __init__(self, parent, initial: list[str] | None = None, start_dir: str = ""):
        super().__init__(parent)
        self.setWindowTitle("รวมไฟล์ PDF")
        self.resize(900, 560)
        self.setAcceptDrops(True)
        self.start_dir = start_dir
        self.result_path: str | None = None
        self._passwords: dict[str, str] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(_title("รวมไฟล์ PDF", "เพิ่มไฟล์ (PDF หรือรูปภาพ) แล้วลากแถวเพื่อจัดลำดับ — ดับเบิลคลิกช่อง “ช่วงหน้า” เพื่อเลือกเฉพาะบางหน้า เช่น 1-3, 5"))

        body = QHBoxLayout()
        body.setSpacing(12)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLS))
        self.tree.setHeaderLabels(self.COLS)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.itemDoubleClicked.connect(self._dbl)
        h = self.tree.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.model().rowsMoved.connect(lambda *a: self._renumber())
        body.addWidget(self.tree, 1)

        side = QVBoxLayout()
        side.setSpacing(8)
        self.b_add = self._btn("plus", "เพิ่มไฟล์…", self._add_dialog, primary=False)
        self.b_up = self._btn("arrow-up", "เลื่อนขึ้น", lambda: self._move(-1))
        self.b_down = self._btn("arrow-down", "เลื่อนลง", lambda: self._move(1))
        self.b_rm = self._btn("delete-outline", "เอาออก", self._remove)
        self.b_clear = self._btn("close", "ล้างทั้งหมด", self._clear)
        for b in (self.b_add, self.b_up, self.b_down, self.b_rm, self.b_clear):
            side.addWidget(b)
        side.addStretch(1)
        body.addLayout(side)
        lay.addLayout(body, 1)

        opts = QHBoxLayout()
        self.chk_bm = QCheckBox("สร้างบุ๊กมาร์กตามชื่อไฟล์")
        self.chk_open = QCheckBox("เปิดไฟล์ที่รวมแล้วทันที")
        self.chk_open.setChecked(True)
        opts.addWidget(self.chk_bm)
        opts.addWidget(self.chk_open)
        opts.addStretch(1)
        self.summary = QLabel("")
        self.summary.setStyleSheet(f"color:{MUTED};")
        opts.addWidget(self.summary)
        lay.addLayout(opts)

        self.box = _buttons(self, "รวมไฟล์และบันทึก…")
        self.box.accepted.disconnect()
        self.box.accepted.connect(self._do_merge)
        self.ok_btn = self.box.buttons()[0]
        lay.addWidget(self.box)

        for p in initial or []:
            self.add_file(p)
        self._refresh()

    def _btn(self, ic: str, text: str, slot, primary: bool = False) -> QPushButton:
        b = QPushButton(" " + text)
        b.setIcon(icon(ic))
        b.setMinimumWidth(130)
        b.clicked.connect(slot)
        return b

    # ── รายการไฟล์ ──
    def add_file(self, path: str) -> bool:
        path = str(path)
        pw = self._passwords.get(path)
        try:
            try:
                doc = ops.open_any(path, pw)
            except PermissionError:
                pw = ask_password(self, Path(path).name)
                if pw is None:
                    return False
                doc = ops.open_any(path, pw)
            n = doc.page_count
            doc.close()
        except PermissionError:
            QMessageBox.warning(self, "รหัสผ่านไม่ถูกต้อง", f"เปิดไฟล์ไม่ได้: {Path(path).name}")
            return False
        except Exception as e:
            QMessageBox.warning(self, "เปิดไฟล์ไม่ได้", f"{Path(path).name}\n\n{e}")
            return False
        if pw:
            self._passwords[path] = pw
        it = QTreeWidgetItem(["", Path(path).name, str(n), "", format_size(os.path.getsize(path))])
        it.setData(1, Qt.ItemDataRole.UserRole, path)
        it.setData(2, Qt.ItemDataRole.UserRole, n)
        it.setToolTip(1, path)
        it.setIcon(1, icon("file-pdf-box", "#E03131", "#E03131"))
        it.setTextAlignment(0, Qt.AlignmentFlag.AlignCenter)
        it.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)
        it.setTextAlignment(3, Qt.AlignmentFlag.AlignCenter)
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsDropEnabled | Qt.ItemFlag.ItemIsEditable)
        self.tree.addTopLevelItem(it)
        self._refresh()
        return True

    def _add_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "เลือกไฟล์ที่ต้องการรวม", self.start_dir,
            "PDF และรูปภาพ (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;PDF (*.pdf);;ทุกไฟล์ (*.*)",
        )
        if files:
            self.start_dir = str(Path(files[0]).parent)
            for f in files:
                self.add_file(f)

    def _dbl(self, item: QTreeWidgetItem, col: int) -> None:
        if col == 3:
            self.tree.editItem(item, 3)

    def _renumber(self) -> None:
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setText(0, str(i + 1))

    def _move(self, d: int) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        rows = sorted(self.tree.indexOfTopLevelItem(i) for i in items)
        if (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == self.tree.topLevelItemCount() - 1):
            return
        order = rows if d < 0 else reversed(rows)
        for r in order:
            it = self.tree.takeTopLevelItem(r)
            self.tree.insertTopLevelItem(r + d, it)
            it.setSelected(True)
        self._renumber()

    def _remove(self) -> None:
        for it in self.tree.selectedItems():
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(it))
        self._refresh()

    def _clear(self) -> None:
        self.tree.clear()
        self._refresh()

    def _refresh(self) -> None:
        self._renumber()
        n = self.tree.topLevelItemCount()
        pages = sum(int(self.tree.topLevelItem(i).data(2, Qt.ItemDataRole.UserRole)) for i in range(n))
        self.summary.setText(f"{n} ไฟล์ • {pages} หน้า (ก่อนเลือกช่วง)" if n else "ยังไม่มีไฟล์ — กด “เพิ่มไฟล์” หรือลากไฟล์มาวาง")
        self.ok_btn.setEnabled(n >= 2)
        self.ok_btn.setToolTip("" if n >= 2 else "ต้องมีอย่างน้อย 2 ไฟล์")

    # ── ลากไฟล์มาวาง ──
    def dragEnterEvent(self, ev):  # noqa: N802
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):  # noqa: N802
        for u in ev.mimeData().urls():
            f = u.toLocalFile()
            if f and Path(f).suffix.lower() in {".pdf", *ops.IMAGE_EXTS}:
                self.add_file(f)
        ev.acceptProposedAction()

    # ── รวม ──
    def items(self) -> list[ops.MergeItem]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            path = it.data(1, Qt.ItemDataRole.UserRole)
            out.append(ops.MergeItem(path, it.text(3).strip(), self._passwords.get(path)))
        return out

    def _do_merge(self) -> None:
        items = self.items()
        for k, it in enumerate(items):  # ตรวจช่วงหน้าก่อน
            n = int(self.tree.topLevelItem(k).data(2, Qt.ItemDataRole.UserRole))
            try:
                parse_page_range(it.page_range, n)
            except ValueError as e:
                QMessageBox.warning(self, "ช่วงหน้าไม่ถูกต้อง", f"{Path(it.path).name}\n\n{e}")
                return
        first = Path(items[0].path)
        suggested = str(first.with_name(first.stem + "_รวม.pdf"))
        out, _ = QFileDialog.getSaveFileName(self, "บันทึกไฟล์ที่รวมแล้ว", suggested, "PDF (*.pdf)")
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"
        from PySide6.QtWidgets import QApplication, QProgressDialog
        prog = QProgressDialog("กำลังรวมไฟล์…", "ยกเลิก", 0, len(items), self)
        prog.setWindowTitle("รวมไฟล์ PDF")
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(0)

        def cb(i: int, total: int, name: str) -> bool:
            prog.setValue(i)
            prog.setLabelText(f"กำลังรวม ({i + 1}/{total}): {name}")
            QApplication.processEvents()
            return not prog.wasCanceled()

        try:
            pages = ops.merge_files(items, out, bookmarks=self.chk_bm.isChecked(), progress=cb)
        except InterruptedError:
            return
        except Exception as e:
            prog.close()
            QMessageBox.critical(self, "รวมไฟล์ไม่สำเร็จ", str(e))
            return
        prog.close()
        self.result_path = out
        self.result_pages = pages
        self.accept()


# ───────────────────────── แยกหน้า ─────────────────────────
class SplitDialog(QDialog):
    def __init__(self, parent, total: int, preset: str = ""):
        super().__init__(parent)
        self.total = total
        self.setWindowTitle("แยกหน้าออกเป็นไฟล์ใหม่")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(_title("แยกหน้าออกเป็นไฟล์ใหม่", f"เอกสารนี้มี {total} หน้า"))
        self.r_one = QRadioButton("ดึงหน้าที่เลือกเป็น 1 ไฟล์")
        self.r_one.setChecked(True)
        self.r_each = QRadioButton("แยกทีละหน้า (ได้หลายไฟล์ ไฟล์ละ 1 หน้า)")
        self.edit = QLineEdit(preset)
        self.edit.setPlaceholderText("เช่น 1-3, 5, 8-  (เว้นว่าง = ทุกหน้า)")
        lay.addWidget(QLabel("หน้าที่ต้องการ"))
        lay.addWidget(self.edit)
        lay.addWidget(self.r_one)
        lay.addWidget(self.r_each)
        lay.addSpacing(6)
        lay.addWidget(_buttons(self, "ถัดไป…"))

    def values(self) -> tuple[list[int], bool]:
        return parse_page_range(self.edit.text(), self.total), self.r_each.isChecked()

    def accept(self) -> None:
        try:
            self.values()
        except ValueError as e:
            QMessageBox.warning(self, "ช่วงหน้าไม่ถูกต้อง", str(e))
            return
        super().accept()


# ───────────────────────── แทรก PDF จากไฟล์อื่น ─────────────────────────
class InsertPdfDialog(QDialog):
    def __init__(self, parent, current_page: int, total: int, start_dir: str = ""):
        super().__init__(parent)
        self.setWindowTitle("แทรกหน้าจากไฟล์ PDF อื่น")
        self.setMinimumWidth(560)
        self.start_dir = start_dir
        self.src_path = ""
        self.src_pages = 0
        self.password: str | None = None
        self.total, self.current = total, current_page
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(_title("แทรกหน้าจากไฟล์อื่น"))
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("เลือกไฟล์ PDF หรือรูปภาพ…")
        b = QPushButton("เลือกไฟล์…")
        b.clicked.connect(self._browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(b)
        lay.addLayout(row)
        self.info = QLabel("")
        self.info.setStyleSheet(f"color:{MUTED};")
        lay.addWidget(self.info)
        form = QFormLayout()
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("เว้นว่าง = ทุกหน้า เช่น 1-3, 5")
        self.pos = QComboBox()
        self.pos.addItem("ก่อนหน้าแรก", 0)
        self.pos.addItem(f"หลังหน้าปัจจุบัน (หน้า {current_page + 1})", current_page + 1)
        self.pos.addItem("ท้ายเอกสาร", total)
        self.pos.setCurrentIndex(1)
        form.addRow("หน้าที่จะแทรก", self.range_edit)
        form.addRow("ตำแหน่ง", self.pos)
        lay.addLayout(form)
        self.box = _buttons(self, "แทรก")
        self.ok = self.box.buttons()[0]
        self.ok.setEnabled(False)
        lay.addWidget(self.box)

    def _browse(self) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self, "เลือกไฟล์ที่จะแทรก", self.start_dir,
            "PDF และรูปภาพ (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;ทุกไฟล์ (*.*)",
        )
        if not f:
            return
        try:
            try:
                d = ops.open_any(f)
            except PermissionError:
                pw = ask_password(self, Path(f).name)
                if pw is None:
                    return
                d = ops.open_any(f, pw)
                self.password = pw
            self.src_pages = d.page_count
            d.close()
        except Exception as e:
            QMessageBox.warning(self, "เปิดไฟล์ไม่ได้", str(e))
            return
        self.src_path = f
        self.path_edit.setText(f)
        self.info.setText(f"ไฟล์นี้มี {self.src_pages} หน้า • {format_size(os.path.getsize(f))}")
        self.ok.setEnabled(True)

    def accept(self) -> None:
        try:
            parse_page_range(self.range_edit.text(), self.src_pages)
        except ValueError as e:
            QMessageBox.warning(self, "ช่วงหน้าไม่ถูกต้อง", str(e))
            return
        super().accept()

    def values(self) -> tuple[str, str | None, list[int], int]:
        return (
            self.src_path,
            self.password,
            parse_page_range(self.range_edit.text(), self.src_pages),
            int(self.pos.currentData()),
        )


# ───────────────────────── ส่งออกเป็นรูปภาพ ─────────────────────────
class ExportImageDialog(QDialog):
    def __init__(self, parent, total: int, preset: str = ""):
        super().__init__(parent)
        self.total = total
        self.setWindowTitle("ส่งออกหน้าเป็นรูปภาพ")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(_title("ส่งออกหน้าเป็นรูปภาพ", f"เอกสารนี้มี {total} หน้า"))
        form = QFormLayout()
        self.range_edit = QLineEdit(preset)
        self.range_edit.setPlaceholderText("เว้นว่าง = ทุกหน้า")
        self.fmt = QComboBox()
        self.fmt.addItems(["PNG", "JPG"])
        self.dpi = QComboBox()
        for d in (72, 96, 150, 200, 300, 600):
            self.dpi.addItem(f"{d} dpi", d)
        self.dpi.setCurrentIndex(2)
        form.addRow("หน้าที่ต้องการ", self.range_edit)
        form.addRow("รูปแบบไฟล์", self.fmt)
        form.addRow("ความละเอียด", self.dpi)
        lay.addLayout(form)
        lay.addWidget(_buttons(self, "เลือกโฟลเดอร์…"))

    def accept(self) -> None:
        try:
            parse_page_range(self.range_edit.text(), self.total)
        except ValueError as e:
            QMessageBox.warning(self, "ช่วงหน้าไม่ถูกต้อง", str(e))
            return
        super().accept()

    def values(self) -> tuple[list[int], str, int]:
        return parse_page_range(self.range_edit.text(), self.total), self.fmt.currentText().lower(), int(self.dpi.currentData())


# ───────────────────────── เกี่ยวกับ ─────────────────────────
# ───────────────────────── ลายน้ำ ─────────────────────────
class WatermarkDialog(QDialog):
    PRESETS = ["ลับ", "ห้ามเผยแพร่", "สำเนา", "ฉบับร่าง", "ใช้ภายในเท่านั้น", "CONFIDENTIAL", "DRAFT", "COPY"]

    def __init__(self, parent, doc: pymupdf.Document, current: int, start_dir: str = "", default_style: TextStyle | None = None):
        super().__init__(parent)
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QSlider

        self.setWindowTitle("ใส่ลายน้ำ")
        self.setMinimumWidth(820)
        self._doc, self._cur, self._dir = doc, current, start_dir
        self._image: bytes | None = None
        st = default_style or TextStyle()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._update_preview)

        root = QHBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(20)
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(_title("ใส่ลายน้ำ", "ข้อความหรือรูปโปร่งแสงวางทับเอกสาร เช่น “ลับ” “ฉบับร่าง” หรือโลโก้บริษัท"))

        kind = QHBoxLayout()
        self.r_text = QRadioButton("ข้อความ")
        self.r_image = QRadioButton("รูปภาพ / โลโก้")
        self.r_text.setChecked(True)
        kind.addWidget(self.r_text)
        kind.addWidget(self.r_image)
        kind.addStretch(1)
        left.addLayout(kind)

        # ── ข้อความ ──
        self.box_text = QWidget()
        tv = QVBoxLayout(self.box_text)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(8)
        self.text_box = QComboBox()
        self.text_box.setEditable(True)
        self.text_box.addItems(self.PRESETS)
        self.text_box.setCurrentText(self.PRESETS[0])
        tv.addWidget(self.text_box)
        row = QHBoxLayout()
        self.font_box = FontCombo(st.family)
        self.size_box = SizeCombo(72)
        self.b_bold = QToolButton()
        self.b_bold.setIcon(icon("format-bold"))
        self.b_bold.setCheckable(True)
        self.b_bold.setChecked(True)
        self.b_bold.setToolTip("ตัวหนา")
        row.addWidget(self.font_box, 1)
        row.addWidget(self.size_box)
        row.addWidget(QLabel("pt"))
        row.addWidget(self.b_bold)
        tv.addLayout(row)
        crow = QHBoxLayout()
        lab = QLabel("สี")
        lab.setStyleSheet(f"color:{MUTED};")
        crow.addWidget(lab)
        self.colors = ColorRow(["#808080", "#E03131", "#1C7ED6", "#2F9E44", "#F59F00", "#000000"], "#808080")
        crow.addWidget(self.colors)
        crow.addStretch(1)
        tv.addLayout(crow)
        left.addWidget(self.box_text)

        # ── รูป ──
        self.box_img = QWidget()
        iv = QVBoxLayout(self.box_img)
        iv.setContentsMargins(0, 0, 0, 0)
        irow = QHBoxLayout()
        self.btn_img = QPushButton("  เลือกไฟล์รูป…")
        self.btn_img.setIcon(icon("image-plus-outline"))
        self.btn_img.clicked.connect(self._pick_image)
        self.lbl_img = QLabel("ยังไม่ได้เลือกรูป (แนะนำ PNG พื้นใส)")
        self.lbl_img.setStyleSheet(f"color:{MUTED};")
        irow.addWidget(self.btn_img)
        irow.addWidget(self.lbl_img, 1)
        iv.addLayout(irow)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("ขนาด (% ของความกว้างหน้า)"))
        self.img_size = QSlider(Qt.Orientation.Horizontal)
        self.img_size.setRange(10, 100)
        self.img_size.setValue(50)
        self.img_size_lbl = QLabel("50%")
        self.img_size_lbl.setFixedWidth(40)
        self.img_size.valueChanged.connect(lambda v: self.img_size_lbl.setText(f"{v}%"))
        srow.addWidget(self.img_size, 1)
        srow.addWidget(self.img_size_lbl)
        iv.addLayout(srow)
        self.box_img.setVisible(False)
        left.addWidget(self.box_img)

        # ── ร่วม ──
        form = QFormLayout()
        form.setSpacing(8)
        self.op = QSlider(Qt.Orientation.Horizontal)
        self.op.setRange(5, 100)
        self.op.setValue(25)
        self.op_lbl = QLabel("25%")
        self.op_lbl.setFixedWidth(40)
        self.op.valueChanged.connect(lambda v: self.op_lbl.setText(f"{v}%"))
        orow = QHBoxLayout()
        orow.addWidget(self.op, 1)
        orow.addWidget(self.op_lbl)
        form.addRow("ความโปร่งแสง (ทึบ)", orow)
        self.angle = QComboBox()
        self.angle.setEditable(True)
        self.angle.setFixedWidth(120)
        self.angle.addItems(["0", "15", "30", "45", "60", "90", "-15", "-30", "-45", "-60", "-90"])
        self.angle.setCurrentText("45")
        self.angle.lineEdit().setValidator(QIntValidator(-180, 180, self))
        self.angle.setToolTip("มุมเอียง (องศา): 45 = เฉียงขึ้นขวา, 0 = แนวนอน")
        arow = QHBoxLayout()
        arow.addWidget(self.angle)
        arow.addWidget(QLabel("องศา"))
        arow.addStretch(1)
        form.addRow("มุมเอียง", arow)
        self.layout_box = QComboBox()
        self.layout_box.addItems(["วางกึ่งกลางหน้า", "ซ้ำเต็มหน้า"])
        form.addRow("การวาง", self.layout_box)
        self.layer_box = QComboBox()
        self.layer_box.addItems(["ทับด้านหน้าเนื้อหา", "อยู่ด้านหลังเนื้อหา"])
        form.addRow("ชั้น", self.layer_box)
        left.addLayout(form)

        pg = QHBoxLayout()
        self.p_all = QRadioButton("ทุกหน้า")
        self.p_cur = QRadioButton(f"หน้าปัจจุบัน ({current + 1})")
        self.p_rng = QRadioButton("ระบุหน้า")
        self.p_all.setChecked(True)
        self.p_edit = QLineEdit()
        self.p_edit.setPlaceholderText(f"เช่น 1-3, 5 (ทั้งหมด {doc.page_count} หน้า)")
        self.p_edit.setEnabled(False)
        self.p_rng.toggled.connect(self.p_edit.setEnabled)
        for w in (self.p_all, self.p_cur, self.p_rng):
            pg.addWidget(w)
        pg.addWidget(self.p_edit, 1)
        left.addLayout(pg)
        left.addStretch(1)
        left.addWidget(_buttons(self, "ใส่ลายน้ำ"))
        root.addLayout(left, 1)

        # ── ตัวอย่าง ──
        right = QVBoxLayout()
        cap = QLabel("ตัวอย่าง")
        cap.setStyleSheet(f"color:{MUTED};font-weight:600;")
        right.addWidget(cap)
        self.preview = QLabel()
        self.preview.setFixedSize(280, 380)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:#E3E1EF;border-radius:10px;")
        right.addWidget(self.preview)
        right.addStretch(1)
        root.addLayout(right)

        self.r_text.toggled.connect(self._mode)
        for sig in (self.text_box.currentTextChanged, self.font_box.changed, self.size_box.changed, self.colors.colorChanged,
                    self.b_bold.toggled, self.img_size.valueChanged, self.op.valueChanged, self.angle.currentTextChanged,
                    self.layout_box.currentIndexChanged, self.layer_box.currentIndexChanged):
            sig.connect(self._queue)
        self._mode()

    def _mode(self) -> None:
        t = self.r_text.isChecked()
        self.box_text.setVisible(t)
        self.box_img.setVisible(not t)
        self.angle.setCurrentText("45" if t else "0")
        self._queue()

    def _queue(self, *_):
        self._timer.start()

    def _pick_image(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "เลือกรูปลายน้ำ", self._dir, "รูปภาพ (*.png *.jpg *.jpeg *.bmp *.webp)")
        if f:
            try:
                self._image = Path(f).read_bytes()
            except OSError as e:
                QMessageBox.warning(self, "เปิดไฟล์ไม่ได้", str(e))
                return
            self.lbl_img.setText(Path(f).name)
            self._queue()

    def _angle(self) -> float:
        try:
            return float(self.angle.currentText())
        except ValueError:
            return 0.0

    def kwargs(self) -> dict:
        kw = dict(opacity=self.op.value() / 100.0, angle=self._angle(),
                  tile=self.layout_box.currentIndex() == 1, behind=self.layer_box.currentIndex() == 1)
        if self.r_image.isChecked():
            kw.update(image=self._image, img_frac=self.img_size.value() / 100.0)
        else:
            kw.update(text=self.text_box.currentText(), style=TextStyle(
                family=self.font_box.family(), size=self.size_box.value(), color=self.colors.color().name(),
                bold=self.b_bold.isChecked(), align="center"))
        return kw

    def pages(self) -> list[int]:
        n = self._doc.page_count
        if self.p_cur.isChecked():
            return [self._cur]
        if self.p_rng.isChecked():
            return parse_page_range(self.p_edit.text(), n)
        return list(range(n))

    def _update_preview(self) -> None:
        from PySide6.QtGui import QImage, QPixmap

        try:
            kw = self.kwargs()
            if self.r_image.isChecked() and not self._image:
                kw = None
        except Exception:
            kw = None
        try:
            tmp = pymupdf.open()
            tmp.insert_pdf(self._doc, from_page=self._cur, to_page=self._cur)
            if kw is not None and (kw.get("image") or str(kw.get("text", "")).strip()):
                ops.add_watermark(tmp, [0], **kw)
            page = tmp[0]
            z = min(272 / page.rect.width, 372 / page.rect.height)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            tmp.close()
            self.preview.setPixmap(QPixmap.fromImage(img))
        except Exception as e:
            self.preview.setText(str(e))

    def showEvent(self, ev):  # noqa: N802
        super().showEvent(ev)
        self._update_preview()

    def accept(self) -> None:
        if self.r_image.isChecked() and not self._image:
            QMessageBox.warning(self, "ลายน้ำ", "กรุณาเลือกไฟล์รูปก่อน")
            return
        if self.r_text.isChecked() and not self.text_box.currentText().strip():
            QMessageBox.warning(self, "ลายน้ำ", "กรุณาพิมพ์ข้อความลายน้ำ")
            return
        try:
            if not self.pages():
                raise ValueError("ไม่ได้เลือกหน้า")
        except Exception as e:
            QMessageBox.warning(self, "ระบุหน้าไม่ถูกต้อง", str(e))
            return
        super().accept()


# ───────────────────────── ตั้งรหัสผ่านเอกสาร ─────────────────────────
class PasswordDialog(QDialog):
    """ตั้งรหัสผ่านเปิดไฟล์ (AES-256) ให้เอกสารที่เปิดอยู่ หรือหลายไฟล์พร้อมกัน"""

    def __init__(self, parent, has_doc: bool, doc_name: str = "", start_dir: str = ""):
        super().__init__(parent)
        self.setWindowTitle("ตั้งรหัสผ่านเอกสาร")
        self.setMinimumWidth(560)
        self._dir = start_dir
        self.files: list[str] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(_title("ตั้งรหัสผ่านเอกสาร", "ผู้ที่ไม่มีรหัสผ่านจะเปิดไฟล์ไม่ได้ — เข้ารหัสแบบ AES-256 และบันทึกเป็นไฟล์ใหม่ (ไฟล์ต้นฉบับไม่ถูกแก้)"))

        self.r_doc = QRadioButton(f"เอกสารที่เปิดอยู่ ({doc_name})" if has_doc else "เอกสารที่เปิดอยู่")
        self.r_many = QRadioButton("เลือกไฟล์ PDF หลายไฟล์จากเครื่อง")
        self.r_doc.setEnabled(has_doc)
        (self.r_doc if has_doc else self.r_many).setChecked(True)
        lay.addWidget(self.r_doc)
        lay.addWidget(self.r_many)

        self.box_files = QWidget()
        fv = QVBoxLayout(self.box_files)
        fv.setContentsMargins(24, 0, 0, 0)
        self.list = QTreeWidget()
        self.list.setHeaderHidden(True)
        self.list.setRootIsDecorated(False)
        self.list.setMinimumHeight(110)
        fv.addWidget(self.list)
        frow = QHBoxLayout()
        b_add = QPushButton("  เพิ่มไฟล์…")
        b_add.setIcon(icon("file-plus-outline"))
        b_add.clicked.connect(self._add_files)
        b_del = QPushButton("เอาออก")
        b_del.clicked.connect(self._remove_files)
        frow.addWidget(b_add)
        frow.addWidget(b_del)
        frow.addStretch(1)
        fv.addLayout(frow)
        lay.addWidget(self.box_files)

        form = QFormLayout()
        form.setSpacing(8)
        self.pw1 = QLineEdit()
        self.pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw1.setPlaceholderText("รหัสผ่านสำหรับเปิดไฟล์ (อย่างน้อย 4 ตัวอักษร)")
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2.setPlaceholderText("พิมพ์รหัสผ่านอีกครั้งเพื่อยืนยัน")
        self.show_pw = QCheckBox("แสดงรหัสผ่าน")
        self.show_pw.toggled.connect(self._toggle_echo)
        form.addRow("รหัสผ่าน", self.pw1)
        form.addRow("ยืนยัน", self.pw2)
        form.addRow("", self.show_pw)
        lay.addLayout(form)

        self.perm_box = QWidget()
        pv = QVBoxLayout(self.perm_box)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(6)
        cap = QLabel("จำกัดสิทธิ์ผู้เปิดไฟล์ (ไม่บังคับ)")
        cap.setStyleSheet(f"color:{MUTED};font-weight:600;")
        pv.addWidget(cap)
        prow = QHBoxLayout()
        self.c_print = QCheckBox("ห้ามพิมพ์")
        self.c_copy = QCheckBox("ห้ามคัดลอกข้อความ")
        self.c_edit = QCheckBox("ห้ามแก้ไข")
        for c in (self.c_print, self.c_copy, self.c_edit):
            c.toggled.connect(self._perm_changed)
            prow.addWidget(c)
        prow.addStretch(1)
        pv.addLayout(prow)
        self.owner = QLineEdit()
        self.owner.setEchoMode(QLineEdit.EchoMode.Password)
        self.owner.setPlaceholderText("รหัสผู้ดูแล — ใช้ปลดข้อจำกัด (ต้องไม่ซ้ำรหัสผ่านเปิดไฟล์)")
        self.owner.setEnabled(False)
        pv.addWidget(self.owner)
        note = QLabel("ข้อจำกัดสิทธิ์เป็นเพียงข้อตกลงที่โปรแกรมอ่าน PDF ส่วนใหญ่ปฏิบัติตาม แต่บางโปรแกรมอาจไม่เคารพ "
                      "— ส่วนรหัสผ่านเปิดไฟล์ป้องกันได้จริง\nโปรดจดรหัสผ่านไว้ หากลืมจะกู้คืนไฟล์ไม่ได้")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{MUTED};font-size:9pt;")
        pv.addWidget(note)
        lay.addWidget(self.perm_box)
        lay.addWidget(_buttons(self, "ตั้งรหัสผ่าน"))
        self.r_many.toggled.connect(self._mode)
        self._mode()

    def _mode(self) -> None:
        self.box_files.setVisible(self.r_many.isChecked())
        self.adjustSize()

    def _toggle_echo(self, on: bool) -> None:
        m = QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        for e in (self.pw1, self.pw2, self.owner):
            e.setEchoMode(m)

    def _perm_changed(self) -> None:
        self.owner.setEnabled(self.c_print.isChecked() or self.c_copy.isChecked() or self.c_edit.isChecked())

    def _add_files(self) -> None:
        fs, _ = QFileDialog.getOpenFileNames(self, "เลือกไฟล์ PDF", self._dir, "PDF (*.pdf)")
        for f in fs:
            if f not in self.files:
                self.files.append(f)
                self.list.addTopLevelItem(QTreeWidgetItem([f]))
            self._dir = str(Path(f).parent)

    def _remove_files(self) -> None:
        for it in self.list.selectedItems():
            self.files.remove(it.text(0))
            self.list.takeTopLevelItem(self.list.indexOfTopLevelItem(it))

    @property
    def many(self) -> bool:
        return self.r_many.isChecked()

    def values(self) -> dict:
        return dict(user_pw=self.pw1.text(), owner_pw=self.owner.text() if self.owner.isEnabled() else "",
                    no_print=self.c_print.isChecked(), no_copy=self.c_copy.isChecked(), no_edit=self.c_edit.isChecked())

    def accept(self) -> None:
        pw = self.pw1.text()
        if len(pw) < 4:
            QMessageBox.warning(self, "รหัสผ่าน", "รหัสผ่านต้องยาวอย่างน้อย 4 ตัวอักษร")
            return
        if pw != self.pw2.text():
            QMessageBox.warning(self, "รหัสผ่าน", "รหัสผ่านทั้งสองช่องไม่ตรงกัน")
            return
        if self.owner.isEnabled():
            if not self.owner.text():
                QMessageBox.warning(self, "รหัสผู้ดูแล", "เมื่อจำกัดสิทธิ์ ต้องตั้งรหัสผู้ดูแลด้วย")
                return
            if self.owner.text() == pw:
                QMessageBox.warning(self, "รหัสผู้ดูแล", "รหัสผู้ดูแลต้องไม่ซ้ำกับรหัสผ่านเปิดไฟล์")
                return
        if self.many and not self.files:
            QMessageBox.warning(self, "ตั้งรหัสผ่าน", "ยังไม่ได้เลือกไฟล์")
            return
        super().accept()


def show_about(parent) -> None:
    QMessageBox.about(
        parent,
        f"เกี่ยวกับ {APP_NAME}",
        f"<h3>{APP_NAME} <span style='color:{MUTED};font-weight:400'>v{APP_VERSION}</span></h3>"
        "<p>โปรแกรมดู แก้ไข รวมไฟล์ และพิมพ์ PDF สำหรับใช้งานภายในองค์กร</p>"
        f"<p><b>{ORG_NAME}</b><br>{COPYRIGHT}</p>"
        f"<p style='color:{MUTED}'>สร้างด้วย Python • PySide6 (Qt) • PyMuPDF • ฟอนต์ Prompt (SIL Open Font License)</p>",
    )
