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
    "Prompt", "Leelawadee UI", "Tahoma", "Sarabun", "TH Sarabun New", "Angsana New",
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


def measure_text(text: str, style: TextStyle, width: float | None) -> tuple[float, float]:
    """วัดขนาด (กว้าง, สูง) หน่วย pt ของข้อความ — ใช้ตัวจัดวางเดียวกับตอนสร้าง PDF จริง"""
    # วัดด้วย writer ชั่วคราว (ความละเอียดเดียวกับตอนวาดจริง)
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
    return max(float(w), 1.0), float(h)


def render_text_pdf(text: str, style: TextStyle, width: float | None) -> tuple[bytes, float, float]:
    """คืน (pdf_bytes, กว้าง, สูง) หน่วยเป็น pt

    width=None → กว้างตามความยาวข้อความจริง (ไม่ตัดบรรทัดอัตโนมัติ)
    """
    w, h = measure_text(text, style, width)

    # วาดลง PDF จริง
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


def render_watermark_pdf(
    w: float, h: float, *, text: str = "", style: TextStyle | None = None, image=None,
    opacity: float = 0.25, angle: float = 45.0, tile: bool = False, img_frac: float = 0.5,
) -> bytes:
    """สร้างหน้า PDF ขนาด w×h ที่มีลายน้ำ (ข้อความหรือรูป) โปร่งแสง หมุนตามองศา — เป็นเวกเตอร์ ข้อความยังค้นหาได้"""
    import math

    from PySide6.QtCore import QRectF

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = _make_writer(buf, w, h)
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setOpacity(max(0.02, min(opacity, 1.0)))

    if image is not None and not image.isNull():
        iw = max(20.0, w * img_frac)
        ih = iw * image.height() / image.width()

        def draw() -> None:
            painter.drawImage(QRectF(-iw / 2, -ih / 2, iw, ih), image)
        iw_, ih_ = iw, ih
    else:
        st = style or TextStyle()
        doc = _build_doc(text, st, None, writer)
        doc.setTextWidth(-1)
        tw = doc.idealWidth() + 2
        doc.setTextWidth(tw)
        th = doc.size().height()

        def draw() -> None:
            painter.translate(-tw / 2, -th / 2)
            doc.drawContents(painter)
        iw_, ih_ = tw, th

    def place(cx: float, cy: float) -> None:
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-angle)
        draw()
        painter.restore()

    if not tile:
        place(w / 2, h / 2)
    else:
        step = math.hypot(iw_, ih_) * 1.25
        step = max(step, 40.0)
        row, y = 0, -step / 2
        while y < h + step:
            x = -step / 2 + (step / 2 if row % 2 else 0)
            while x < w + step:
                place(x, y)
                x += step
            y += step
            row += 1
    painter.end()
    buf.close()
    return bytes(buf.data())
