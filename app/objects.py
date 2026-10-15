"""วัตถุลอยบนหน้า (รูปภาพ / ลายเซ็น / กล่องข้อความ)

วัตถุเหล่านี้ยังไม่ถูกฝังลงในเนื้อหา PDF จนกว่าจะบันทึก/พิมพ์/ทำรายการที่แก้โครงสร้างหน้า
จึงย้าย ย่อขยาย คัดลอก ลบ และย้อนกลับได้อิสระ — ตอนบันทึกจะฝังเป็นเนื้อหาจริงของ PDF
พิกัดทั้งหมดเป็นหน่วย pt ในมุมมองที่เห็นบนจอ (หลังหมุนหน้าแล้ว)
"""
from __future__ import annotations

import dataclasses
import itertools
from collections import OrderedDict
from dataclasses import dataclass, field

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from .textrender import TextStyle, measure_text, render_text_pdf  # noqa: F401  (measure_text ใช้ผ่าน objmod)

_uid = itertools.count(1)
MIN_SIZE = 12.0
MIN_FONT, MAX_FONT = 4.0, 400.0


@dataclass
class FloatObj:
    kind: str                       # "image" | "text"
    page: int
    x: float
    y: float
    w: float
    h: float
    data: bytes = b""               # รูป (PNG/JPG ดิบ)
    text: str = ""
    style: TextStyle = field(default_factory=TextStyle)
    uid: int = field(default_factory=lambda: next(_uid))

    @property
    def is_text(self) -> bool:
        return self.kind == "text"

    def clone(self, new_uid: bool = False) -> "FloatObj":
        c = dataclasses.replace(self, style=dataclasses.replace(self.style))
        if new_uid:
            c.uid = next(_uid)
        return c

    def rect(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.w, self.h

    def set_rect(self, r: tuple[float, float, float, float]) -> None:
        self.x, self.y, self.w, self.h = r


# ───────────────────────── สร้างวัตถุ ─────────────────────────
def relayout(obj: FloatObj) -> None:
    """คำนวณความสูงของกล่องข้อความใหม่ตามความกว้าง/ฟอนต์ปัจจุบัน"""
    if obj.is_text:
        w, h = measure_text(obj.text, obj.style, max(obj.w, MIN_SIZE))
        obj.w, obj.h = w, h


def image_size(data: bytes) -> tuple[int, int]:
    img = QImage.fromData(data)
    return (img.width(), img.height()) if not img.isNull() else (0, 0)


def make_image(page: int, data: bytes, cx: float, cy: float, width: float,
               page_size: tuple[float, float] | None = None) -> FloatObj:
    """สร้างวัตถุรูปโดยให้จุดกึ่งกลางอยู่ที่ (cx, cy) และกว้าง width (คงสัดส่วนเดิม)"""
    iw, ih = image_size(data)
    if iw <= 0 or ih <= 0:
        raise ValueError("อ่านไฟล์รูปภาพไม่ได้")
    w = max(MIN_SIZE, width)
    h = w * ih / iw
    if page_size:
        pw, ph = page_size
        if h > ph * 0.8:                      # รูปสูงเกินหน้า → ย่อให้พอดี
            h = ph * 0.8
            w = h * iw / ih
    x, y = cx - w / 2, cy - h / 2
    if page_size:
        x = min(max(x, 0.0), max(page_size[0] - w, 0.0))
        y = min(max(y, 0.0), max(page_size[1] - h, 0.0))
    return FloatObj("image", page, x, y, w, h, data=data)


def make_text(page: int, x: float, y: float, width: float, text: str, style: TextStyle) -> FloatObj:
    obj = FloatObj("text", page, x, y, max(width, 40.0), 20.0, text=text, style=dataclasses.replace(style))
    relayout(obj)
    return obj


# ───────────────────────── ภาพตัวอย่างบนจอ ─────────────────────────
_decoded: "OrderedDict[int, QImage]" = OrderedDict()
_scaled: "OrderedDict[tuple, QImage]" = OrderedDict()
_text_prev: "OrderedDict[tuple, QImage]" = OrderedDict()


def _lru(cache: OrderedDict, key, make, limit: int):
    v = cache.get(key)
    if v is not None:
        cache.move_to_end(key)
        return v
    v = make()
    cache[key] = v
    while len(cache) > limit:
        cache.popitem(last=False)
    return v


def _decode(data: bytes) -> QImage:
    def make() -> QImage:
        img = QImage.fromData(data)
        if img.isNull():
            return img
        if max(img.width(), img.height()) > 1800:       # ย่อรูปใหญ่มากเพื่อให้วาดบนจอลื่น
            img = img.scaled(1800, 1800, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    return _lru(_decoded, hash(data), make, 24)


def image_preview(obj: FloatObj, px_w: int, px_h: int) -> QImage:
    px_w, px_h = max(1, px_w), max(1, px_h)

    def make() -> QImage:
        src = _decode(obj.data)
        if src.isNull():
            return src
        return src.scaled(px_w, px_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return _lru(_scaled, (hash(obj.data), px_w, px_h), make, 48)


def text_preview(obj: FloatObj, px_per_pt: float) -> QImage:
    """เรนเดอร์ข้อความจาก PDF เวกเตอร์เดียวกับที่จะฝังจริง (WYSIWYG) เป็นภาพโปร่งใส"""
    st = obj.style
    key = (obj.text, st.family, round(st.size, 2), st.color, st.bold, st.italic, st.underline, st.align,
           round(obj.w, 1), round(px_per_pt, 3))

    def make() -> QImage:
        data, w, h = render_text_pdf(obj.text, st, obj.w)
        src = pymupdf.open("pdf", data)
        try:
            pix = src[0].get_pixmap(matrix=pymupdf.Matrix(px_per_pt, px_per_pt), alpha=True)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGBA8888).copy()
        finally:
            src.close()
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    return _lru(_text_prev, key, make, 40)


# ───────────────────────── ฝังลงเอกสาร ─────────────────────────
def bake(page: pymupdf.Page, obj: FloatObj) -> None:
    """ฝังวัตถุลงเนื้อหาของหน้าจริง (พิกัดของวัตถุเป็นแบบที่เห็นบนจอ)"""
    from .ops import _overlay_pdf, vis_to_unrot_rect

    rect = pymupdf.Rect(obj.x, obj.y, obj.x + obj.w, obj.y + obj.h)
    if obj.is_text:
        data, w, h = render_text_pdf(obj.text, obj.style, obj.w)
        _overlay_pdf(page, pymupdf.Rect(obj.x, obj.y, obj.x + w, obj.y + h), data)
    else:
        page.insert_image(
            vis_to_unrot_rect(page, rect),
            stream=obj.data,
            keep_proportion=False,
            rotate=page.rotation,
            overlay=True,
        )


def bake_all(doc: pymupdf.Document, objs: list[FloatObj], pages: set[int] | None = None) -> None:
    for o in objs:
        if (pages is None or o.page in pages) and 0 <= o.page < doc.page_count:
            bake(doc[o.page], o)
