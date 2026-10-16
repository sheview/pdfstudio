"""การพิมพ์: เรนเดอร์หน้า PDF ลงเครื่องพิมพ์ผ่าน Qt (รองรับช่วงหน้า / จำนวนชุด / ตัวอย่างก่อนพิมพ์)"""
from __future__ import annotations

from typing import Callable

import pymupdf
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPainter
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .config import PRINT_DPI


SAFE_PRINT_DPI = 200      # 200 dpi พอสำหรับงานเอกสาร และเบากว่ามากสำหรับไดรเวอร์/สปูลเลอร์ของ Windows


def _page_image(page: pymupdf.Page, dpi: int) -> QImage:
    s = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    return img.convertToFormat(QImage.Format.Format_RGB32)       # รูปแบบที่ GDI ของ Windows ใช้ตรง ๆ ไม่ต้องแปลงซ้ำ


def _orientation_for(page: pymupdf.Page) -> QPageLayout.Orientation:
    r = page.rect
    return QPageLayout.Orientation.Landscape if r.width > r.height else QPageLayout.Orientation.Portrait


def paint_pages(
    printer: QPrinter,
    doc: pymupdf.Document,
    pages: list[int],
    dpi: int | None = None,
    progress: Callable[[int, int], bool] | None = None,
) -> None:
    """วาดหน้าที่เลือกลง printer

    ตั้งแนวกระดาษ "ครั้งเดียว" ก่อนเริ่มงาน (การสลับแนวกลางงานทำให้สปูลเลอร์ของ Windows ค้างได้)
    หน้าที่แนวไม่ตรงกับกระดาษจะถูกหมุน 90° ตอนวาดแทน
    """
    if not pages:
        return
    dpi = dpi or min(SAFE_PRINT_DPI, PRINT_DPI)
    want = _orientation_for(doc[pages[0]])
    if printer.pageLayout().orientation() != want:
        printer.setPageOrientation(want)
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("เริ่มพิมพ์ไม่ได้ — ตรวจสอบว่าเครื่องพิมพ์เปิดอยู่/ไม่ถูกหยุดชั่วคราว")
    cancelled = False
    try:
        area0 = printer.pageLayout().paintRectPixels(printer.resolution())
        aw, ah = float(area0.width()), float(area0.height())
        for n, pno in enumerate(pages):
            page = doc[pno]
            if progress and progress(n, len(pages)) is False:
                cancelled = True
                break
            if n > 0:
                printer.newPage()
            r = page.rect
            rotate = (r.width > r.height) != (aw > ah)
            fw, fh = (ah, aw) if rotate else (aw, ah)           # ขนาดพื้นที่หลังหมุน
            scale = min(fw / r.width, fh / r.height)
            w, h = r.width * scale, r.height * scale
            painter.save()
            painter.translate(aw / 2, ah / 2)
            if rotate:
                painter.rotate(90)
            painter.drawImage(QRectF(-w / 2, -h / 2, w, h), _page_image(page, dpi))
            painter.restore()
            QApplication.processEvents()
    finally:
        painter.end()
    if cancelled:
        try:
            printer.abort()
        except Exception:
            pass


def pages_from_printer(printer: QPrinter, total: int, current: int) -> list[int]:
    rng = printer.printRange()
    if rng == QPrinter.PrintRange.PageRange:
        a = max(printer.fromPage(), 1)
        b = min(printer.toPage() or total, total)
        return list(range(a - 1, b))
    if rng == QPrinter.PrintRange.CurrentPage:
        return [current]
    return list(range(total))


def expand_copies(printer: QPrinter, pages: list[int]) -> list[int]:
    """ถ้าไดรเวอร์ไม่รองรับหลายชุด ให้ซ้ำหน้าเอง"""
    copies = max(printer.copyCount(), 1)
    if copies == 1 or printer.supportsMultipleCopies():
        return pages
    if printer.collateCopies():
        return pages * copies
    return [p for p in pages for _ in range(copies)]


def print_document(parent, doc: pymupdf.Document, current: int, title: str = "") -> bool:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setDocName(title or "PDF")
    printer.setFullPage(False)
    dlg = QPrintDialog(printer, parent)
    dlg.setWindowTitle("พิมพ์เอกสาร")
    dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintToFile, False)
    dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange, True)
    dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintCurrentPage, True)
    dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintCollateCopies, True)
    dlg.setMinMax(1, doc.page_count)
    if dlg.exec() != QPrintDialog.DialogCode.Accepted:
        return False
    return run_print(parent, printer, doc, current)


def run_print(parent, printer: QPrinter, doc: pymupdf.Document, current: int) -> bool:
    pages = expand_copies(printer, pages_from_printer(printer, doc.page_count, current))
    prog = QProgressDialog("กำลังเตรียมงานพิมพ์…", "ยกเลิก", 0, len(pages), parent)
    prog.setWindowTitle("พิมพ์")
    prog.setMinimumDuration(0)
    prog.setAutoClose(False)
    prog.setAutoReset(False)
    prog.setWindowModality(Qt.WindowModality.WindowModal)
    prog.setValue(0)
    prog.show()
    QApplication.processEvents()

    def cb(i: int, total: int) -> bool:
        prog.setValue(i)
        prog.setLabelText(f"กำลังพิมพ์หน้า {i + 1} จาก {total}")
        QApplication.processEvents()
        return not prog.wasCanceled()

    try:
        paint_pages(printer, doc, pages, progress=cb)
    except Exception as e:
        prog.close()
        QMessageBox.critical(parent, "พิมพ์ไม่สำเร็จ", str(e))
        return False
    prog.close()
    return True


def print_via_system(doc: pymupdf.Document, title: str = "") -> str:
    """ทางสำรอง: บันทึกไฟล์ PDF ชั่วคราวแล้วเปิดด้วยโปรแกรมอ่าน PDF ของเครื่อง (ไปสั่งพิมพ์จากโปรแกรมนั้น)"""
    import os
    import re
    import subprocess
    import sys
    import tempfile

    safe = re.sub(r'[\\/:*?"<>|]+', "_", title or "document").strip() or "document"
    path = os.path.join(tempfile.mkdtemp(prefix="governix_print_"), f"{safe}.pdf")
    doc.save(path, garbage=3, deflate=True)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
    return path


def print_preview(parent, doc: pymupdf.Document, current: int, title: str = "") -> None:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setDocName(title or "PDF")
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle("ตัวอย่างก่อนพิมพ์")
    dlg.resize(1000, 760)

    def paint(p: QPrinter) -> None:
        pages = pages_from_printer(p, doc.page_count, current)
        paint_pages(p, doc, expand_copies(p, pages))

    dlg.paintRequested.connect(paint)
    dlg.exec()
