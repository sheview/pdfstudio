"""ทดสอบรอบ 3: เครื่องคิดเลข / คิดงวดเงิน / QR Code
รัน: QT_QPA_PLATFORM=offscreen python tests/test_round3.py <outdir>"""
from __future__ import annotations

import os
import sys
from decimal import Decimal as D
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

exec(open(Path(__file__).with_name("test_objects.py")).read().split("# ── 1) ใส่ข้อความ")[0])

import numpy as np

from app import calc, calcdialogs, qrtool

# ── 1) ตรรกะคิดเลข ──
cases = {"12,500,000*30%": "3750000", "(1000+250)/4": "312.5", "100+7%": "107", "200-10%": "180",
         "๑๒๓+๔": "127", "2^10": "1024", "10 × 3 ÷ 4": "7.5", "-5+2": "-3"}
for e, want in cases.items():
    assert calc.evaluate(e) == D(want), (e, calc.evaluate(e))
for bad in ("", "1/0", "abc", "__import__('os')", "2**99999", "1+"):
    try:
        calc.evaluate(bad); raise AssertionError(bad)
    except calc.CalcError:
        pass
print("calc evaluate OK")

# ── 2) งวดเงิน: ผลรวมตรงมูลค่าสัญญา (เศษสตางค์ไปที่งวดสุดท้าย), VAT/หัก ณ ที่จ่าย ──
rows, s = calc.compute_installments(D("1000000.01"), [("1", D(33)), ("2", D(33)), ("3", D(34))])
assert s["base"] == D("1000000.01") and s["pct"] == 100 and s["gross"] == D("1000000.01")
rows, s = calc.compute_installments(D("107000"), [("1", D(50)), ("2", D(50))], D(7), True, D(3))
assert s["gross"] == D("107000.00") and s["base"] == D("100000.00") and s["vat"] == D("7000.00") and s["wht"] == D("3000.00")
rows, s = calc.compute_installments(D("100000"), [("1", D(30)), ("2", D(30))], D(7), False)
assert s["remaining_pct"] == 40 and rows[0].gross == D("32100.00")
f = calc.extract_contract_numbers("ค่าจ้างรวม ๑,๒๓๔,๕๖๗.๘๙ บาท\nงวดที่ 1 ร้อยละ 30 ของค่าจ้าง\nงวดที่ 2 ร้อยละ ๔๐\nงวดที่ 3 ชำระ 30% เมื่อตรวจรับ")
assert f.amounts[0][0] == D("1234567.89") and [(n, int(p)) for n, p in f.installments] == [("งวดที่ 1", 30), ("งวดที่ 2", 40), ("งวดที่ 3", 30)], f
print("installments + extraction OK")

# ── 3) หน้าต่างเครื่องคิดเลข ──
cd = calcdialogs.CalculatorDialog(win); cd.show(); wait(100)
cd.expr.setText("12,500,000*30%"); cd.equals()
assert cd.result.text() == "3,750,000" and cd.history.count() == 1
cd.press("C"); cd.expr.setText("107000"); cd.vat(False)
assert cd.result.text() == "100,000", cd.result.text()
shot(cd, "50_calculator")
inserted = []
cd.insertText.connect(inserted.append); cd.insert_result(); assert inserted == ["100,000"]
win._calc_dlg = None; win.show_calculator(); wait(100)
tab.insert_text_value("100,000"); wait(100)
assert any(o.is_text and o.text == "100,000" for o in tab.model.objects)
print("calculator dialog OK")

# ── 4) หน้าต่างคิดงวดเงิน (ดึงจากเอกสารจริง) ──
from app import doctab
text_pdf = tab.model.doc
pg = text_pdf[0]
pg.insert_text((60, 700), "Contract total 2,000,000.00 THB", fontsize=11)
dlg = calcdialogs.InstallmentDialog(win, page_text=lambda: "รวมเป็นเงิน 2,000,000.00 บาท\nงวดที่ 1 ร้อยละ 50\nงวดที่ 2 ร้อยละ 50", selected_text=lambda: "")
dlg.show(); wait(100)
dlg.amount.setText("2,000,000"); dlg.vat.setCurrentIndex(1); wait(50)   # ยังไม่รวม VAT
assert dlg.table.item(0, 4).text() == "1,070,000.00" or dlg.table.item(0, 4).text() == "642,000.00", dlg.table.item(0, 4).text()
dlg._apply_preset_values([D(50), D(50)]); wait(50)
assert dlg.table.item(0, 4).text() == "1,070,000.00", dlg.table.item(0, 4).text()
assert "100%" in dlg.status.text() and "✓" in dlg.status.text()
dlg.wht.setCurrentText("3%"); wait(50)
assert dlg.table.item(0, 5).text() == "30,000.00" and dlg.table.item(0, 6).text() == "1,040,000.00"
dlg.add_row("งวดที่ 3", D(10)); wait(50)
assert "เกินสัญญา 10%" in dlg.status.text(), dlg.status.text()
shot(dlg, "51_installments")
# ส่งออก
dlg.del_row(); wait(30)
clip = []
dlg.copy_table(); txt = QApplication.clipboard().text()
assert txt.splitlines()[0].startswith("งวด\t") and "1,070,000.00" in txt and txt.splitlines()[-1].startswith("รวม\t100%"), txt
got = []
dlg.insertImage.connect(got.append); dlg.insert_table()
assert got and got[0][:4] == b"\x89PNG"
open(out / "table.png", "wb").write(got[0])
n0 = len(tab.model.objects)
tab.insert_png(got[0]); wait(100)
assert len(tab.model.objects) == n0 + 1 and not tab.model.objects[-1].is_text
print("installment dialog OK")

# ── 5) QR Code: สร้างแล้วต้อง decode กลับได้ตรงลิงก์ ──
import cv2
url = "https://example.sharepoint.com/sites/contracts/สัญญา-0001.pdf"
png = qrtool.make_qr_png(qrtool.normalize_url(url))
img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
val, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
assert val == url, val
assert qrtool.normalize_url("example.com/a") == "https://example.com/a"
for bad in ("", "ไม่ใช่ลิงก์ เฉยๆ", "x" * 800):
    try:
        qrtool.normalize_url("https://a.com/" + bad if bad.startswith("x") else bad); raise AssertionError(bad)
    except ValueError:
        pass
qd = qrtool.QrDialog(win); qd.url.setText(url); qd.show(); wait(100); shot(qd, "52_qr_dialog")
class AutoQr(qrtool.QrDialog):
    def exec(self): return 1
doctab.QrDialog = AutoQr
def _vals(self): return qrtool.make_qr_png(url), "สแกนเพื่อดูสัญญา", 100.0
AutoQr.values = _vals
n0 = len(tab.model.objects)
tab.add_qr(); wait(200)
new = tab.model.objects[n0:]
assert len(new) == 2 and not new[0].is_text and new[1].is_text and new[1].text == "สแกนเพื่อดูสัญญา"
assert set(tab.view.selected_uids) == {o.uid for o in new}
# ฝังลงไฟล์แล้ว scan จากภาพที่เรนเดอร์ของ PDF ได้จริง
with tab.model.baked() as d:
    pix = d[new[0].page].get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False)
arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
val, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
assert val == url, f"scan จากหน้า PDF ที่ฝังแล้วต้องได้ลิงก์เดิม: {val!r}"
print("qr OK (decoded from rendered PDF page)")
win.ribbon.tabbar.setCurrentIndex(0); wait(150); shot(win, "53_ribbon_home")
win.ribbon.tabbar.setCurrentIndex(1); wait(150); shot(win, "54_ribbon_edit")
print("ROUND 3 TESTS OK ->", out)
