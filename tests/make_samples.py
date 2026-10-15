"""สร้างไฟล์ PDF ตัวอย่างสำหรับทดสอบ"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import pymupdf


def find_thai_font() -> str | None:
    cands = [
        r"C:\Windows\Fonts\tahoma.ttf",
        *glob.glob("/usr/share/fonts/**/Loma-Regular.*", recursive=True),
        *glob.glob("/usr/share/fonts/**/Garuda.*", recursive=True),
    ]
    for c in cands:
        if Path(c).exists():
            return c
    return None


def _thai(page, xy, text, size):
    """เขียนข้อความไทยให้ถูกต้องด้วย Qt (ถ้าไม่มี Qt ใช้ฟอนต์ธรรมดา)"""
    try:
        from PySide6.QtWidgets import QApplication
        from app.textrender import TextStyle, default_thai_font, render_text_pdf
        if QApplication.instance() is None:
            raise RuntimeError
        data, w, h = render_text_pdf(text, TextStyle(family=default_thai_font(), size=size), None)
        src = pymupdf.open("pdf", data)
        page.show_pdf_page(pymupdf.Rect(xy[0], xy[1], xy[0] + w, xy[1] + h), src, 0)
    except Exception:
        page.insert_text((xy[0], xy[1] + size), text, fontsize=size)


def make_sample(path: str, title: str, pages: int = 3, size=(595, 842), rotate: int = 0) -> str:
    doc = pymupdf.open()
    font = find_thai_font()
    for i in range(pages):
        p = doc.new_page(width=size[0], height=size[1])
        kw = {"fontname": "thai", "fontfile": font} if font else {}
        p.insert_text((60, 90), f"{title} - Page {i + 1}", fontsize=24, **({} if not font else kw))
        _thai(p, (60, 122), "สวัสดีครับ ทดสอบภาษาไทย หน้าที่ %d" % (i + 1), 16)
        for n in range(8):
            p.insert_text(
                (60, 190 + n * 28),
                f"Line {n + 1}: The quick brown fox jumps over the lazy dog. 0123456789",
                fontsize=12,
            )
        p.draw_rect(pymupdf.Rect(60, 450, 300, 520), color=(0.2, 0.4, 0.9), fill=(0.9, 0.94, 1))
        _thai(p, (70, 472), "กรอบสีฟ้า / blue box", 14)
        if rotate:
            p.set_rotation(rotate)
    doc.save(path)
    doc.close()
    return path


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    make_sample(str(out / "a.pdf"), "Document A", 3)
    make_sample(str(out / "b.pdf"), "Document B", 2)
    make_sample(str(out / "c_landscape.pdf"), "Document C", 2, size=(842, 595))
    make_sample(str(out / "rot90.pdf"), "Rotated", 2, rotate=90)
    print("ok")
