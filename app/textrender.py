"""สร้างข้อความเป็น PDF แบบเวกเตอร์ด้วย Qt

ใช้ Qt จัดวางตัวอักษร (HarfBuzz) เพื่อให้สระ/วรรณยุกต์ภาษาไทยซ้อนกันถูกต้อง
แล้วนำผลที่ได้ไปวางทับบนหน้า PDF ด้วย PyMuPDF — ข้อความยังเป็นตัวอักษรจริง
ค้นหา/คัดลอกได้ และใช้ฟอนต์ใดก็ได้ที่ติดตั้งในเครื่อง
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QIODevice, QMarginsF, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)

THAI_FONT_CANDIDATES = [
    "Leelawadee UI", "Tahoma", "Sarabun", "TH Sarabun New", "Angsana New",
    "Cordia New", "Loma", "Garuda", "Norasi", "Noto Sans Thai", "Segoe UI",
]


def default_thai_font() -> str:
    families = set(QFontDatabase.families())
    for name in THAI_FONT_CANDIDATES:
        if name in families:
            return name
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()


@dataclass
class TextStyle:
    family: str = ""
    size: float = 14.0
    color: str = "#000000"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    align: str = "left"  # left | center | right

    def qfont(self) -> QFont:
        f = QFont(self.family or default_thai_font())
        f.setPointSizeF(self.size)
        f.setBold(self.bold)
        f.setItalic(self.italic)
        f.setUnderline(self.underline)
        return f


_ALIGN = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
}


def _build_doc(text: str, style: TextStyle, width: float | None, device) -> QTextDocument:
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(device)
    doc.setDocumentMargin(0)
    doc.setDefaultFont(style.qfont())
    opt = QTextOption()
    opt.setAlignment(_ALIGN.get(style.align, Qt.AlignmentFlag.AlignLeft))
    opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    doc.setDefaultTextOption(opt)
    if width:
        doc.setTextWidth(width)
    doc.setPlainText(text)
    cur = QTextCursor(doc)
    cur.select(QTextCursor.SelectionType.Document)
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(style.color))
    cur.mergeCharFormat(fmt)
    return doc


def _make_writer(buf: QBuffer, w: float, h: float) -> QPdfWriter:
    writer = QPdfWriter(buf)
    writer.setResolution(72)
    writer.setPageSize(QPageSize(QSizeF(w, h), QPageSize.Unit.Point))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
    return writer


def render_text_pdf(text: str, style: TextStyle, width: float | None) -> tuple[bytes, float, float]:
    """คืน (pdf_bytes, กว้าง, สูง) หน่วยเป็น pt

    width=None → กว้างตามความยาวข้อความจริง (ไม่ตัดบรรทัดอัตโนมัติ)
    """
    # 1) วัดขนาดด้วย writer ชั่วคราว (ความละเอียดเดียวกับตอนวาดจริง)
    probe_buf = QBuffer()
    probe_buf.open(QIODevice.OpenModeFlag.WriteOnly)
    probe = _make_writer(probe_buf, 100, 100)
    doc = _build_doc(text, style, width, probe)
    if width is None:
        doc.setTextWidth(-1)
        w = doc.idealWidth() + 1
        doc.setTextWidth(w)
    else:
        w = width
    size = doc.size()
    h = max(size.height(), style.size * 1.2)
    w = max(w, 1.0)

    # 2) วาดลง PDF จริง
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = _make_writer(buf, w, h)
    doc2 = _build_doc(text, style, w, writer)
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    doc2.drawContents(painter)
    painter.end()
    buf.close()
    return bytes(buf.data()), float(w), float(h)
