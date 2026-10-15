"""ทดสอบ GUI แบบไม่มีจอ: QT_QPA_PLATFORM=offscreen python tests/gui_smoke.py <outdir>
จับภาพหน้าจอเก็บไว้ที่ <outdir> เพื่อตรวจหน้าตา"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app import doctab, printing
from app.theme import apply_app_font, stylesheet
from app.viewer import Tool
from tests.make_samples import make_sample

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pdfstudio_gui")
out.mkdir(parents=True, exist_ok=True)

app = QApplication([])
apply_app_font(app)
app.setStyleSheet(stylesheet())

# ไม่ให้กล่องข้อความบล็อกการทดสอบ
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)  # type: ignore[assignment]
QMessageBox.information = staticmethod(lambda *a, **k: None)  # type: ignore[assignment]
QMessageBox.warning = staticmethod(lambda *a, **k: print("WARN:", a[1:3]))  # type: ignore[assignment]


class FakeTextDialog:
    class DialogCode:
        Accepted = 1

    def __init__(self, parent, title, text="", style=None, sub="", deletable=False):
        self.deleted = False
        from app.textrender import TextStyle
        self._text = text or "ทดสอบใส่ข้อความ ผู้ใหญ่ น้ำ"
        self._style = style or TextStyle(size=18, color="#0B7285")
        if not text:
            self._style.size = 18

    def exec(self):
        return 1

    def text_value(self):
        return self._text if "แก้" not in self._text else self._text

    def style_value(self):
        return self._style


doctab.TextDialog = FakeTextDialog  # type: ignore[assignment]
doctab.TextDialog.DialogCode = FakeTextDialog.DialogCode


def wait(ms=300):
    QTest.qWait(ms)


def shot(widget, name):
    widget.grab().save(str(out / f"{name}.png"))


from app.mainwindow import MainWindow  # noqa: E402

a = make_sample(str(out / "a.pdf"), "Document A", 4)
b = make_sample(str(out / "b.pdf"), "Document B", 2)

win = MainWindow()
win.resize(1360, 860)
win.show()
wait()
shot(win, "01_welcome")

win.open_files([a])
wait(900)
tab = win.current_tab()
assert tab is not None and tab.model.page_count == 4
shot(win, "02_opened")

# ── แท็บริบบิ้น ──
win.ribbon.tabbar.setCurrentIndex(1); wait(100); shot(win, "03_ribbon_edit")
win.ribbon.tabbar.setCurrentIndex(2); wait(100); shot(win, "04_ribbon_pages")
win.ribbon.tabbar.setCurrentIndex(0)

# ── ค้นหา ──
tab.open_search(); tab.search.edit.setText("quick brown"); wait(700)
print("search hits:", len(tab._hits))
assert tab._hits
shot(win, "05_search")
tab.close_search()

# ── เลือกข้อความ + ไฮไลต์ ──
win.set_tool(Tool.SELECT)
pr = tab.view.page_rects[0]
s = tab.view._scale(0)
start = tab.view.canvas.mapFromParent  # noqa
QTest.mousePress(tab.view.canvas, Qt.MouseButton.LeftButton, pos=(pr.topLeft() + QPointF(62 * s, 205 * s)).toPoint())
QTest.mouseMove(tab.view.canvas, (pr.topLeft() + QPointF(250 * s, 208 * s)).toPoint())
QTest.mouseRelease(tab.view.canvas, Qt.MouseButton.LeftButton, pos=(pr.topLeft() + QPointF(250 * s, 208 * s)).toPoint())
wait(200)
print("selected text:", repr(tab.view.selected_text()))
assert tab.view.has_selection()
shot(win, "06_selected")
tab.apply_markup_to_selection("highlight"); wait(400)
assert tab.model.dirty and tab.model.can_undo()

# ── ใส่ข้อความ / ปากกา / ปิดทับ ──
tab.view.tool = Tool.TEXT
tab.on_rect(0, QRectF(60, 560, 360, 40)); wait(300)
tab.view.tool = Tool.PEN
tab.on_ink(0, [(300.0, 640.0), (340.0, 690.0), (380.0, 650.0), (430.0, 700.0)]); wait(200)
tab.view.tool = Tool.REDACT
tab.on_rect(0, QRectF(55, 330, 300, 20)); wait(200)
tab.view.tool = Tool.EDIT_TEXT
tab.on_rect(0, QRectF(55, 120, 350, 30)); wait(300)
win.set_tool(Tool.SELECT)
wait(500)
shot(win, "07_edited")

# ── จัดการหน้า ──
tab.go_to_page(1)
tab.rotate(90); wait(300)
assert tab.model.doc[1].rotation == 90
tab.insert_blank(); wait(200); assert tab.model.page_count == 5
tab.duplicate(); wait(200); assert tab.model.page_count == 6
tab.thumbs.item(3).setSelected(True)
tab.delete_pages(); wait(200); print("pages after delete:", tab.model.page_count)
tab.move(1); wait(200)
shot(win, "08_pages")
for _ in range(3):
    win.undo(); wait(100)
win.redo(); wait(100)
print("undo/redo ok, pages:", tab.model.page_count)

# ── ซูมโหมดต่างๆ ──
tab.view.fit_page(); wait(400); shot(win, "09_fitpage")
tab.view.set_zoom(2.2); wait(400); shot(win, "10_zoom")
tab.view.fit_width(); wait(200)

# ── บันทึก / พิมพ์เป็น PDF ──
saved = out / "saved.pdf"
tab.model.save(str(saved)); assert saved.exists()
pdf_out = out / "printed.pdf"
pr_ = QPrinter(QPrinter.PrinterMode.HighResolution)
pr_.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
pr_.setOutputFileName(str(pdf_out))
printing.paint_pages(pr_, tab.model.doc, list(range(tab.model.page_count)), dpi=120)
chk = pymupdf.open(pdf_out)
print("printed pages:", chk.page_count)
assert chk.page_count == tab.model.page_count

# ── เปิดอีกไฟล์ (แท็บที่ 2) ──
win.open_files([b]); wait(500)
assert win.tabs.count() == 2
shot(win, "11_two_tabs")
win.close_tab(1)
wait(100)

# ── ปิดแท็บแล้วกลับหน้าต้อนรับ ──
tab.model._set_dirty(False)
win.close_tab(0); wait(200)
shot(win, "12_back_to_welcome")
print("GUI SMOKE OK ->", out)
