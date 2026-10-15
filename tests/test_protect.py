"""ทดสอบการตั้งรหัสผ่าน: QT_QPA_PLATFORM=offscreen python tests/test_protect.py <outdir>"""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pymupdf
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import ops
from app.theme import apply_app_font, stylesheet
from tests.make_samples import make_sample

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pdfgov_pw"); out.mkdir(parents=True, exist_ok=True)
app = QApplication([]); apply_app_font(app); app.setStyleSheet(stylesheet())
src = make_sample(str(out / "a.pdf"), "Secret", 2)

# 1) รหัสเปิดไฟล์อย่างเดียว
ops.protect_file(src, out / "p1.pdf", "1234")
d = pymupdf.open(out / "p1.pdf")
assert d.needs_pass and d.is_encrypted
assert not d.authenticate("wrong") and d.authenticate("1234") and d.page_count == 2
assert "Secret" in d[0].get_text()
try:
    ops.open_any(out / "p1.pdf"); raise SystemExit("ต้องขอรหัส")
except PermissionError:
    pass
assert ops.open_any(out / "p1.pdf", "1234").page_count == 2

# 2) จำกัดสิทธิ์ + รหัสผู้ดูแล
ops.protect_file(src, out / "p2.pdf", "user1", "owner1", no_print=True, no_copy=True, no_edit=True)
d = pymupdf.open(out / "p2.pdf"); d.authenticate("user1")
perm = d.permissions
print("perm bits:", perm)
assert not (perm & pymupdf.PDF_PERM_PRINT) and not (perm & pymupdf.PDF_PERM_COPY) and not (perm & pymupdf.PDF_PERM_MODIFY)
d2 = pymupdf.open(out / "p2.pdf"); d2.authenticate("owner1")
assert d2.permissions & pymupdf.PDF_PERM_PRINT

# 3) ข้อจำกัดแต่ไม่ใส่รหัสผู้ดูแล → สุ่มให้
ops.protect_file(src, out / "p3.pdf", "abcd", "", no_print=True)
d = pymupdf.open(out / "p3.pdf"); assert d.authenticate("abcd") and not (d.permissions & pymupdf.PDF_PERM_PRINT)
# 4) รหัสสั้นเกินไป
try:
    ops.protect_file(src, out / "p4.pdf", "12"); raise SystemExit("ควร error")
except ValueError:
    pass
assert not (out / "p4.pdf").exists()
# 5) ไฟล์ที่มีรหัสแล้ว → ข้ามพร้อมข้อยกเว้น
try:
    ops.protect_file(out / "p1.pdf", out / "p5.pdf", "zzzz"); raise SystemExit("ควร error")
except PermissionError:
    pass

# 6) วัตถุลอยถูกฝังก่อนเข้ารหัส + ภาพหน้าต่าง
from app import objects as om
from app.textrender import TextStyle
from app.mainwindow import MainWindow
w = MainWindow(); w.show(); w.open_files([src]); QTest.qWait(400)
t = w.current_tab(); t.add_object(om.make_text(0, 100, 600, 250, "ลายเซ็นก่อนล็อก", TextStyle(size=18)))
with t.model.baked() as bd:
    ops.save_protected(bd, out / "p6.pdf", "9999")
d = pymupdf.open(out / "p6.pdf"); d.authenticate("9999"); assert "ลายเซ็นก่อนล็อก" in d[0].get_text()
from app.dialogs import PasswordDialog
dl = PasswordDialog(w, True, "a.pdf", str(out)); dl.show(); dl.c_print.setChecked(True); QTest.qWait(200)
dl.grab().save(str(out / "pw_dialog.png"))
dl.r_many.setChecked(True); QTest.qWait(200); dl.grab().save(str(out / "pw_dialog_many.png"))
print("PROTECT OK")
