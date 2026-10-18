"""ทดสอบโหมดนำเสนอ: QT_QPA_PLATFORM=offscreen python tests/test_round4.py <outdir>"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
exec(open(Path(__file__).with_name("test_objects.py")).read().split("# ── 1) ใส่ข้อความ")[0])

from PySide6.QtCore import QPointF
from app.presenter import PresentationWindow, PresentOptions, PresentOptionsDialog

# หน้า 1/2/3 ต่างสีชัดเจน เพื่อตรวจการผสมภาพ
colors = [(220, 40, 40), (40, 160, 60), (40, 70, 220)]
d = pymupdf.open()
for c in colors:
    pg = d.new_page(width=800, height=450)
    pg.draw_rect(pg.rect, color=None, fill=tuple(x / 255 for x in c))
data = d.tobytes()

def pix(win, x=None, y=None):
    img = win.grab().toImage()
    x = img.width() // 2 if x is None else x
    y = img.height() // 2 if y is None else y
    c = img.pixelColor(x, y)
    return c.red(), c.green(), c.blue()

def alive(w):
    try:
        return w.isVisible()
    except RuntimeError:
        return False

def key(w, k, mods=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(w, k, mods); 

opts = PresentOptions("fade", 600, 0, False)
w = PresentationWindow(data, 0, opts); w.resize(960, 540); w.start(); wait(200)
assert w.isFullScreen() or w.isVisible()
r0 = pix(w); assert r0[0] > 180 and r0[1] < 80, r0                      # หน้า 1 แดง
# เฟด: กลางทางต้องเป็นสีผสมแดง+เขียว
key(w, Qt.Key.Key_Right); wait(300)
mid = pix(w)
assert w._anim is not None or w._t < 1.0 or mid != r0
wait(800)
r1 = pix(w); assert r1[1] > 120 and r1[0] < 90, r1                      # หน้า 2 เขียว
assert w.index == 1
# ผสมจริง: หยุดแอนิเมชันที่ t=0.5 แล้วเช็กค่าสี
w._finish_anim(); w.opts.duration_ms = 600
w.index = 1; w._from = w._render(1); w._to = w._render(2); w._t = 0.5; w._anim = object()  # type: ignore
w._anim = type("A", (), {"stop": lambda s: None, "deleteLater": lambda s: None})()
mix = pix(w); assert 90 < mix[1] < 140 and 100 < mix[2] < 180, f"เฟดที่ 50% ต้องผสมเขียว+น้ำเงิน {mix}"
w._finish_anim(); w.index = 1; w.update(); wait(50)
print("fade OK", r0, "->", mix, "->", r1)

# สไลด์: ที่ 50% ครึ่งซ้ายเป็นหน้าเดิม ครึ่งขวาเป็นหน้าใหม่
w.opts.transition = "slide"
w.index = 1
w._from = w._render(1); w._to = w._render(2); w._dir = 1; w._t = 0.5
w._anim = type("A", (), {"stop": lambda s: None, "deleteLater": lambda s: None})()
left, right = pix(w, w.width() // 4), pix(w, w.width() * 3 // 4)
assert left[1] > 120 and right[2] > 150, (left, right)
w._finish_anim(); w.update()
print("slide OK", left, right)

# ปุ่มต่าง ๆ
w.opts.transition = "none"; w.goto(0); assert w.index == 0
key(w, Qt.Key.Key_Space); assert w.index == 1
key(w, Qt.Key.Key_Left); assert w.index == 0
key(w, Qt.Key.Key_End); assert w.index == 2
key(w, Qt.Key.Key_Home); assert w.index == 0
key(w, Qt.Key.Key_3); key(w, Qt.Key.Key_Return); assert w.index == 2, w.index
key(w, Qt.Key.Key_B); assert pix(w) == (0, 0, 0); key(w, Qt.Key.Key_B); assert pix(w)[2] > 150
key(w, Qt.Key.Key_W); assert pix(w) == (255, 255, 255); key(w, Qt.Key.Key_W)
key(w, Qt.Key.Key_L); assert w._laser
key(w, Qt.Key.Key_L)
# จบการนำเสนอ → คลิก/คีย์ถัดไปอีกครั้งจึงออก
key(w, Qt.Key.Key_Right); assert w._ended and w.isVisible()
shot_img = w.grab(); shot_img.save(str(out / "60_end_screen.png"))
key(w, Qt.Key.Key_Left); assert not w._ended
QTest.mouseClick(w, Qt.MouseButton.LeftButton)       # คลิกซ้าย = ถัดไป
QTest.mouseClick(w, Qt.MouseButton.LeftButton); assert w._ended
QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(10, 10)); wait(50)
assert not alive(w), "คลิกตอนจบต้องออกจากโหมดนำเสนอ"
print("keys/mouse/end OK")

# วนกลับ + เปลี่ยนหน้าอัตโนมัติ
w2 = PresentationWindow(data, 0, PresentOptions("none", 0, 1, True)); w2.resize(640, 360)
seen = [0]
orig_goto = w2.goto
w2.goto = lambda i, d=None: (seen.append(min(max(i, 0), 2)), orig_goto(i, d))[1]   # type: ignore
w2.opts.auto_sec = 0.1; w2.start(); w2._auto.start(100)
wait(900)
assert seen[:5] == [0, 1, 2, 0, 1] or (set(seen) == {0, 1, 2} and 0 in seen[1:]), seen
w2.close()
print("auto-advance + loop OK", seen[:7])


# ── ปากกา / ไฮไลต์ / ซูม ──
from PySide6.QtCore import QPoint as _P
wp = PresentationWindow(data, 0, PresentOptions("none", 0, 0, False)); wp.resize(960, 540); wp.start(); wait(150)
key(wp, Qt.Key.Key_D); assert wp._tool == "pen"
from PySide6.QtGui import QMouseEvent as _ME
from PySide6.QtCore import QEvent as _E
def drag(w, pts):
    LB, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    mk = lambda t, p, b, bs: _ME(t, QPointF(p[0], p[1]), QPointF(p[0], p[1]), b, bs, Qt.KeyboardModifier.NoModifier)
    w.mousePressEvent(mk(_E.Type.MouseButtonPress, pts[0], LB, LB))
    for q in pts[1:]:
        w.mouseMoveEvent(mk(_E.Type.MouseMove, q, NB, LB))
    w.mouseReleaseEvent(mk(_E.Type.MouseButtonRelease, pts[-1], LB, NB))
    wait(30)
drag(wp, [(100, 100), (200, 140), (300, 100), (400, 140)])
assert wp.index == 0 and len(wp._ink.get(0, [])) == 1 and len(wp._ink[0][0][2]) == 4, "วาดปากกาต้องไม่เปลี่ยนหน้า"
wp.undo_stroke(); assert not wp._ink[0]
key(wp, Qt.Key.Key_C)                                  # สีน้ำเงิน เห็นชัดบนหน้าแดง
drag(wp, [(100, 200), (400, 200)])
c = pix(wp, 250, 200); assert c[2] > 180 and c[0] < 100, f"เส้นปากกาสีน้ำเงินต้องเห็นกลางเส้น {c}"
wp.goto(1); wait(30); assert not wp._ink.get(1); wp.goto(0); wait(30)
assert len(wp._ink[0]) == 1                          # เส้นยังอยู่เมื่อกลับมาหน้าเดิม
key(wp, Qt.Key.Key_E); assert 0 not in wp._ink
key(wp, Qt.Key.Key_H); assert wp._tool == "hl"; key(wp, Qt.Key.Key_H); assert wp._tool is None
# ซูม
key(wp, Qt.Key.Key_Z); assert wp._zoom > 1.0
wp.set_zoom(3.0, QPointF(480, 270)); wait(30)
c = pix(wp); assert c[0] > 180 and c[1] < 80, c      # ยังเห็นหน้าแดง ไม่ดำ
p0 = QPointF(wp._pan); drag(wp, [(300, 300), (340, 330)])
assert wp.index == 0 and wp._pan != p0, "ตอนซูมลากเมาส์เพื่อเลื่อนดู ไม่เปลี่ยนหน้า"
wp.set_zoom(1.0); assert wp._zoom == 1.0 and wp._pan == QPointF(0, 0)
wp.set_zoom(2.0); wp.goto(1); assert wp._zoom == 1.0, "เปลี่ยนหน้าแล้วรีเซ็ตซูม"
key(wp, Qt.Key.Key_Escape); wait(30)
print("pen/zoom OK")
# เลือกจอ
d2 = PresentOptionsDialog(win, PresentOptions(screen=0)); assert d2.values().screen == 0

# Esc ออก + ตั้งค่าบันทึก/โหลด
w3 = PresentationWindow(data, 2, PresentOptions()); w3.start(); closed = []
w3.closed_callbacks.append(lambda: closed.append(1)); key(w3, Qt.Key.Key_Escape); wait(50)
assert closed == [1] and not alive(w3)
dlg = PresentOptionsDialog(win, PresentOptions("slide", 700, 5, True)); dlg.show(); wait(100)
o = dlg.values(); assert (o.transition, o.duration_ms, o.auto_sec, o.loop) == ("slide", 700, 5, True)
shot(dlg, "61_present_settings")
import app.presenter as pm
pm.SETTINGS_ORG, pm.SETTINGS_APP = "GovernixTest", "PresentTest"
o.save(); l = PresentOptions.load(); assert (l.transition, l.duration_ms, l.auto_sec, l.loop) == ("slide", 700, 5, True)
print("settings OK")

# ผ่านแท็บเอกสารจริง: วัตถุที่วางไว้ต้องแสดงตอนนำเสนอ
tab.model.objects.clear()
tab.model.objects.append(objmod.make_image(0, Image.new("RGB", (80, 80), (255, 0, 255)).tobytes() and (out / "sig.png").read_bytes(), 300, 300, 200, v.sizes[0])) if False else None
from PIL import Image as _I
import io as _io
b = _io.BytesIO(); _I.new("RGB", (100, 100), (255, 0, 255)).save(b, "PNG")
o = objmod.make_image(0, b.getvalue(), v.sizes[0][0] / 2, v.sizes[0][1] / 2, 200, v.sizes[0]); tab.model.objects.append(o)
tab._commit_objects([0])
pm.PresentOptions.load = classmethod(lambda cls: PresentOptions("none", 0, 0, False))  # type: ignore
tab.present(False); wait(300)
pw = tab._presenter; assert pw is not None and pw.index == 0
c = pix(pw); assert c[0] > 200 and c[1] < 60 and c[2] > 200, f"รูปที่วางไว้ต้องอยู่กลางหน้าตอนนำเสนอ {c}"
tab.present(True); assert tab._presenter is pw          # เปิดซ้อนไม่ได้
key(pw, Qt.Key.Key_Escape); wait(50); assert tab._presenter is None and not alive(pw)
v.go_to_page(1); wait(200); tab.present(True); wait(200); assert tab._presenter.index == 1
key(tab._presenter, Qt.Key.Key_Escape); wait(50)
win.ribbon.tabbar.setCurrentIndex(0); wait(150); shot(win, "62_ribbon_present")
print("present from tab OK")
print("ROUND 4 TESTS OK ->", out)
