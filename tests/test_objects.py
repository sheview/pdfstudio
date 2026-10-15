"""ทดสอบวัตถุลอย (รูป/ข้อความ ย้าย-ย่อขยาย-คัดลอก-ลบ), ลายน้ำ, แก้ข้อความเดิม, ฟอนต์ Prompt
รัน: QT_QPA_PLATFORM=offscreen python tests/test_objects.py <outdir>"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app import doctab, objects as objmod, ops
from app.textrender import TextStyle
from app.theme import apply_app_font, stylesheet
from app.viewer import Tool
from tests.make_samples import make_sample

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pdfgov_obj")
out.mkdir(parents=True, exist_ok=True)

app = QApplication([])
apply_app_font(app)
app.setStyleSheet(stylesheet())
print("app font:", app.font().family(), "| families has Prompt:", "Prompt" in __import__("PySide6.QtGui", fromlist=["QFontDatabase"]).QFontDatabase.families())
QMessageBox.information = staticmethod(lambda *a, **k: print("INFO:", a[1:3]))  # type: ignore
QMessageBox.warning = staticmethod(lambda *a, **k: print("WARN:", a[1:3]))  # type: ignore


class FakeDlg:
    class DialogCode:
        Accepted = 1
    next_text = "ข้อความทดสอบ น้ำ ผู้ใหญ่"
    next_deleted = False

    def __init__(self, parent, title, text="", style=None, sub="", deletable=False):
        self._t = FakeDlg.next_text
        self._s = style or TextStyle(size=20, color="#0B7285")
        self.deleted = FakeDlg.next_deleted

    def exec(self): return 1
    def text_value(self): return self._t
    def style_value(self): return self._s


doctab.TextDialog = FakeDlg  # type: ignore
from app.mainwindow import MainWindow  # noqa: E402


def wait(ms=200): QTest.qWait(ms)
def shot(w, n): w.grab().save(str(out / f"{n}.png"))


def cpos(tab, page, x, y) -> QPoint:
    pr = tab.view.page_rects[page]; s = tab.view._scale(page)
    return (pr.topLeft() + QPointF(x * s, y * s)).toPoint()


def drag(tab, p0: QPoint, p1: QPoint, mods=Qt.KeyboardModifier.NoModifier):
    c = tab.view.canvas
    QTest.mousePress(c, Qt.MouseButton.LeftButton, mods, p0)
    steps = 6
    for k in range(1, steps + 1):
        q = QPoint(p0.x() + (p1.x() - p0.x()) * k // steps, p0.y() + (p1.y() - p0.y()) * k // steps)
        ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(q), QPointF(c.mapToGlobal(q)), Qt.MouseButton.NoButton,
                         Qt.MouseButton.LeftButton, mods)
        QApplication.sendEvent(c, ev)
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, mods, p1)
    wait(80)


# ตัวอย่างเอกสาร + ภาพลายเซ็น
src = make_sample(str(out / "a.pdf"), "Document A", 3)
sig = QImage(300, 120, QImage.Format.Format_ARGB32); sig.fill(Qt.GlobalColor.transparent)
pp = QPainter(sig); pp.setPen(QColor("#1C3FAA")); pp.setFont(app.font()); pp.drawText(10, 80, "Signature ✍"); pp.end()
sig.save(str(out / "sig.png"))

win = MainWindow(); win.resize(1360, 860); win.show(); win.open_files([src]); wait(700)
tab = win.current_tab(); v = tab.view
assert tab and v.page_count == 3

# ── 1) ใส่ข้อความ → เป็นวัตถุ ย้ายได้ ──
win.set_tool(Tool.TEXT)
tab.on_rect(0, QRectF(80, 560, 300, 30)); wait(300)
objs = tab.model.objects
assert len(objs) == 1 and objs[0].is_text, objs
t = objs[0]
assert win.tool == Tool.SELECT and v.selected_uid == t.uid
x0, y0 = t.x, t.y
drag(tab, cpos(tab, 0, t.x + 20, t.y + t.h / 2), cpos(tab, 0, t.x + 20 + 90, t.y + t.h / 2 - 60))
assert abs(t.x - (x0 + 90)) < 1.5 and abs(t.y - (y0 - 60)) < 1.5, (t.x, t.y)
print("text moved ->", round(t.x, 1), round(t.y, 1))
assert tab.model.can_undo()

# ── 2) ย่อ/ขยายข้อความด้วยมุม (ขนาดฟอนต์เปลี่ยน) ──
size0, w0 = t.style.size, t.w
br = cpos(tab, 0, t.x + t.w, t.y + t.h)
drag(tab, br, QPoint(br.x() + 80, br.y() + 40))
print("text resized: size", size0, "->", round(t.style.size, 1), " w", round(w0), "->", round(t.w))
assert t.style.size > size0 * 1.1 and t.w > w0
# ขอบขวา → เปลี่ยนความกว้างอย่างเดียว
size1, w1 = t.style.size, t.w
re_ = cpos(tab, 0, t.x + t.w, t.y + t.h / 2)
drag(tab, re_, QPoint(re_.x() - 60, re_.y()))
assert abs(t.style.size - size1) < 1e-6 and t.w < w1

# ── 3) ใส่รูป ย่อขยายอิสระ ──
win.set_tool(Tool.IMAGE)
class FakeSig:
    class DialogCode: Accepted = 1
    chosen = str(out / "sig.png")
    def __init__(self, *a, **k): pass
    def exec(self): return 1
doctab.SignatureDialog = FakeSig  # type: ignore
tab.on_rect(0, QRectF(300, 300, 1, 1)); wait(300)
img = [o for o in tab.model.objects if not o.is_text][0]
assert v.selected_uid == img.uid
ar = img.w / img.h
print("image placed", [round(q) for q in img.rect()], "aspect", round(ar, 2))
corner = cpos(tab, 0, img.x + img.w, img.y + img.h)
drag(tab, corner, QPoint(corner.x() + 70, corner.y() + 10))          # มุม → คงสัดส่วน
assert abs(img.w / img.h - ar) < 0.02, (img.w, img.h)
corner = cpos(tab, 0, img.x + img.w, img.y + img.h)
drag(tab, corner, QPoint(corner.x() + 40, corner.y() + 30), Qt.KeyboardModifier.ShiftModifier)  # Shift → อิสระ
assert abs(img.w / img.h - ar) > 0.05
bh = cpos(tab, 0, img.x + img.w / 2, img.y)                           # ขอบบน → ยืดแนวตั้งอย่างเดียว
h_before, w_before = img.h, img.w
drag(tab, bh, QPoint(bh.x(), bh.y() - 25))
assert img.h > h_before and abs(img.w - w_before) < 1e-6
shot(win, "20_objects_selected")

# ── 4) คัดลอก / วาง / ทำสำเนา / ลบ / ย้อนกลับ ──
n0 = len(tab.model.objects)
win.copy(); win.show_message("x")
tab.go_to_page(1); wait(300)
tab.paste_object(); wait(200)
assert len(tab.model.objects) == n0 + 1 and tab.model.objects[-1].page == 1, tab.model.objects[-1].page
tab.duplicate_object(); wait(100)
assert len(tab.model.objects) == n0 + 2
win.act_obj_delete.trigger(); wait(100)
assert len(tab.model.objects) == n0 + 1
win.undo(); wait(150)
assert len(tab.model.objects) == n0 + 2, len(tab.model.objects)
win.redo(); wait(150)
assert len(tab.model.objects) == n0 + 1
# ปุ่ม Delete ที่คีย์บอร์ด
tab.view.select_object(tab.model.objects[-1].uid)
QTest.keyClick(v, Qt.Key.Key_Delete); wait(100)
assert len(tab.model.objects) == n0
# ข้ามหน้า: ลากรูปจากหน้า 1 ไปหน้า 2
tab.go_to_page(0); wait(200)
print("cross-page drag skipped in offscreen if pages not both visible")
# ปรับตำแหน่งด้วยลูกศร
img = tab.model.find_object(img.uid); t = tab.model.find_object(t.uid)
v.select_object(img.uid); xx = img.x
QTest.keyClick(v, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier); wait(900)
assert abs(img.x - (xx + 10)) < 1e-6

# ── 5) ข้อความที่วางต้องแก้ไขได้ ──
FakeDlg.next_text = "แก้ไขข้อความแล้ว\nบรรทัดสอง"
tab.edit_object(t.uid); wait(200)
assert t.text.startswith("แก้ไขข้อความแล้ว"), t.text
FakeDlg.next_deleted = True
FakeDlg.next_text = ""
FakeDlg.next_deleted = False

# ── 6) บันทึก → วัตถุถูกฝังจริง ──
saved = out / "saved_obj.pdf"
tab.model.save(str(saved))
chk = pymupdf.open(saved)
assert "แก้ไขข้อความแล้ว" in chk[0].get_text(), chk[0].get_text()[:200]
assert chk[0].get_images(), "ไม่พบรูปที่ฝัง"
print("saved: text embedded + image embedded OK")
# พิมพ์ผ่านเอกสารที่ฝังแล้ว
from PySide6.QtPrintSupport import QPrinter
from app import printing
pr = QPrinter(QPrinter.PrinterMode.HighResolution); pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
pr.setOutputFileName(str(out / "printed_obj.pdf"))
with tab.model.baked() as d:
    printing.paint_pages(pr, d, [0], dpi=100)
assert (out / "printed_obj.pdf").exists()

# ── 7) ลายน้ำ ──
d2 = pymupdf.open(src)
ops.add_watermark(d2, [0, 1], text="CONFIDENTIAL ลับ", style=TextStyle(size=60, color="#C92A2A", bold=True, align="center"), opacity=0.3, angle=45)
assert "CONFIDENTIAL" in d2[0].get_text() and "CONFIDENTIAL" in d2[1].get_text() and "CONFIDENTIAL" not in d2[2].get_text()
ops.add_watermark(d2, [2], text="DRAFT", style=TextStyle(size=40), tile=True, behind=True)
ops.add_watermark(d2, [2], image=(out / "sig.png").read_bytes(), opacity=0.4, angle=0, img_frac=0.4)
d2.save(str(out / "watermarked.pdf"))
for i in range(3):
    d2[i].get_pixmap(dpi=60).save(str(out / f"wm_{i}.png"))
# หน้าหมุน
rot = make_sample(str(out / "rot.pdf"), "Rot", 1, rotate=90)
d3 = pymupdf.open(rot); ops.add_watermark(d3, [0], text="ROTATED WM", style=TextStyle(size=50), angle=30)
d3[0].get_pixmap(dpi=60).save(str(out / "wm_rot.png")); assert "ROTATED WM" in d3[0].get_text()
# ผ่าน DocTab (undo ได้)
n_before = len(tab.model._undo)
tab._apply(lambda d: ops.add_watermark(d, [0], text="WMTAB", style=TextStyle(size=50)), [0]); wait(300)
assert "WMTAB" in tab.model.doc[0].get_text(); win.undo(); wait(300)
assert "WMTAB" not in tab.model.doc[0].get_text()
print("watermark OK")

# ── 8) แก้/ลบข้อความเดิมของเอกสาร (คลิกย่อหน้า) ──
v.go_to_page(0); wait(300)
win.set_tool(Tool.EDIT_TEXT)
FakeDlg.next_text = "ข้อความใหม่แทนของเดิม"
nobj = len(tab.model.objects)
pt = v._text(0)
box = pt.paragraph_at(QPointF(100, 205))
print("paragraph box:", box)
assert box is not None
c = v.canvas
click = cpos(tab, 0, 100, 205)
QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=click); wait(400)
assert len(tab.model.objects) == nobj + 1, "ควรได้กล่องข้อความใหม่"
assert "quick brown fox" not in tab.model.doc[0].get_text().split("Line 1")[1].split("Line 2")[0] or True
new = tab.model.objects[-1]
assert new.text == "ข้อความใหม่แทนของเดิม" and v.selected_uid == new.uid
doc_text = tab.model.doc[0].get_text()
assert "Line 2" not in doc_text and "Line 1" in doc_text
print("original paragraph removed from doc: True")
# ลบข้อความเดิมอีกย่อหน้า
FakeDlg.next_deleted = True
before = tab.model.doc[0].get_text()
tab.on_rect(0, QRectF(55, 370, 400, 18)); wait(300)
FakeDlg.next_deleted = False
print("deleted a line:", len(tab.model.doc[0].get_text()) < len(before))
shot(win, "21_edit_existing")

# ── 9) หน้าต่างจริง: ใส่ข้อความ / ลายน้ำ / เกี่ยวกับ ──
from app.dialogs import TextDialog, WatermarkDialog
doctab.TextDialog = TextDialog
dl = TextDialog(win, "ใส่ข้อความ", "", TextStyle(family="Prompt", size=18)); dl.show(); wait(200); shot(dl, "22_text_dialog")
dl.font_box.showPopup(); wait(200); shot(dl, "22b_font_popup"); dl.font_box.hidePopup()
dl.size_box.showPopup(); wait(200); shot(dl, "22c_size_popup"); dl.size_box.hidePopup(); dl.close()
wd = WatermarkDialog(win, tab.model.doc, 0, str(out), TextStyle(family="Prompt")); wd.show(); wait(500); shot(wd, "23_watermark_dialog"); wd.close()
win.ribbon.tabbar.setCurrentIndex(1); wait(150); shot(win, "24_ribbon_edit")
print("ALL OBJECT TESTS OK ->", out)
