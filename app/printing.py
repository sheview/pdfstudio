"""การพิมพ์: เรนเดอร์หน้า PDF ลงเครื่องพิมพ์ผ่าน Qt (รองรับช่วงหน้า / จำนวนชุด / ตัวอย่างก่อนพิมพ์)"""
from __future__ import annotations

from typing import Callable

import pymupdf
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPageLayout, QPainter
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .config import PRINT_DPI


def _page_image(page: pymupdf.Page, dpi: int) -> QImage:
    s = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
    return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()


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
    """วาดหน้าที่เลือกลง printer (ปรับให้พอดีพื้นที่พิมพ์ และหมุนกระดาษตามแนวหน้า)"""
    if not pages:
        return
    dpi = dpi or min(PRINT_DPI, max(printer.resolution(), 96))
    # ตั้งแนวกระดาษของหน้าแรกก่อนเริ่มวาด
    want = _orientation_for(doc[pages[0]])
    if printer.pageLayout().orientation() != want:
        printer.setPageOrientation(want)
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("เริ่มพิมพ์ไม่ได้ — ตรวจสอบเครื่องพิมพ์")
    try:
        for n, pno in enumerate(pages):
            page = doc[pno]
            if n > 0:
                want = _orientation_for(page)
                if printer.pageLayout().orientation() != want:
                    printer.setPageOrientation(want)  # มีผลกับหน้าถัดไปที่ newPage()
                printer.newPage()
            if progress and progress(n, len(pages)) is False:
                break
            r = page.rect
            area = printer.pageLayout().paintRectPixels(printer.resolution())
            area = QRectF(0, 0, area.width(), area.height())
            scale = min(area.width() / r.width, area.height() / r.height)
            w, h = r.width * scale, r.height * scale
            target = QRectF(area.x() + (area.width() - w) / 2, area.y() + (area.height() - h) / 2, w, h)
            painter.drawImage(target, _page_image(page, dpi))
    finally:
        painter.end()


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
    prog = QProgressDialog("กำลังส่งงานพิมพ์…", "ยกเลิก", 0, len(pages), parent)
    prog.setWindowTitle("พิมพ์")
    prog.setMinimumDuration(400)
    prog.setWindowModality(2)  # Qt.WindowModal

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
