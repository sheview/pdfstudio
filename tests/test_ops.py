"""ทดสอบ ops (ไม่ใช้หน้าจอ): QT_QPA_PLATFORM=offscreen python tests/test_ops.py <outdir>"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf
from PySide6.QtWidgets import QApplication

from app import ops
from app.textrender import TextStyle, default_thai_font
from tests.make_samples import make_sample

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pdfstudio_test")
out.mkdir(parents=True, exist_ok=True)
app = QApplication.instance() or QApplication([])

a = make_sample(str(out / "a.pdf"), "Document A", 3)
b = make_sample(str(out / "b.pdf"), "Document B", 2)
r = make_sample(str(out / "rot90.pdf"), "Rotated", 2, rotate=90)

# ── หน้า ──
d = pymupdf.open(a)
ops.rotate_pages(d, [0], 90); assert d[0].rotation == 90
ops.insert_blank_page(d, 0); assert d.page_count == 4
ops.duplicate_pages(d, [2]); assert d.page_count == 5
ops.delete_pages(d, [1]); assert d.page_count == 4
ops.reorder_pages(d, [3, 2, 1, 0]); assert d.page_count == 4
try:
    ops.delete_pages(d, [0, 1, 2, 3]); raise SystemExit("ควรลบทั้งหมดไม่ได้")
except ValueError:
    pass
ops.extract_pages(d, [0, 1], out / "extract.pdf"); assert pymupdf.open(out / "extract.pdf").page_count == 2
src = pymupdf.open(b); ops.insert_pdf_at(d, src, [0, 1], 1); assert d.page_count == 6
print("page ops OK")

# ── รวมไฟล์ ──
cnt = ops.merge_files(
    [ops.MergeItem(a), ops.MergeItem(b, "2"), ops.MergeItem(a, "1-2")],
    out / "merged.pdf", bookmarks=True,
)
assert cnt == 3 + 1 + 2, cnt
m = pymupdf.open(out / "merged.pdf"); assert len(m.get_toc()) == 3
print("merge OK", cnt)

# ── เขียนข้อความไทย (Qt) ──
style = TextStyle(family=default_thai_font(), size=20, color="#c0392b", bold=True)
d2 = pymupdf.open(a)
rect = ops.add_text(d2[0], pymupdf.Rect(60, 560, 400, 620), "ทดสอบข้อความไทย ที่นี่ ผู้ใหญ่ ปู่ย่า น้ำ\nบรรทัดที่สอง English mix 123", style)
print("text rect", rect, "font", style.family)
txt = d2[0].get_text()
assert "ทดสอบ" in txt or "English" in txt, txt[:200]

# ไฮไลต์
hits = d2[0].search_for("quick brown")
ops.add_text_markup(d2[0], "highlight", [h.quad for h in hits[:1]], (1, 1, 0))
ops.add_text_markup(d2[0], "underline", [h.quad for h in hits[1:2]], (1, 0, 0))
ops.add_text_markup(d2[0], "strike", [h.quad for h in hits[2:3]], (0, 0, 1))
ops.add_ink(d2[0], [(300, 600), (350, 650), (400, 610), (450, 660)], (0.1, 0.5, 0.9), 3)

# แก้ข้อความเดิม
vis = pymupdf.Rect(55, 120, 400, 150)
probe = ops.probe_text(d2[0], vis)
print("probe:", probe)
ops.replace_text(d2[0], probe.bbox_vis, "แก้ไขแล้ว ✓ ข้อความใหม่", TextStyle(family=style.family, size=probe.size, color=probe.color))
# ปิดดำ
ops.redact_area(d2[0], pymupdf.Rect(55, 180, 400, 200), (0, 0, 0))
assert "Line 1" not in d2[0].get_text()
d2.save(out / "edited.pdf")
d2[0].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2)).save(out / "edited.png")

# ── หน้าที่หมุน ──
d3 = pymupdf.open(r)
p = d3[0]
vis = pymupdf.Rect(50, 300, 350, 340)
ops.add_text(p, vis, "ข้อความบนหน้าหมุน 90°", TextStyle(family=style.family, size=16, color="#0a7a3a"))
ops.add_ink(p, [(100, 100), (200, 150), (300, 100)], (1, 0, 0), 2)
ops.redact_area(p, pymupdf.Rect(40, 40, 200, 70), (0.9, 0.9, 0.5))
pix = d3[0].get_pixmap(matrix=pymupdf.Matrix(1, 1)); pix.save(out / "rot_edit.png")
print("ALL OK ->", out)
