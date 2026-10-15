"""การดำเนินการกับเอกสาร PDF (ไม่เกี่ยวกับ GUI — ทดสอบได้แยก)

หมายเหตุเรื่องพิกัด: PyMuPDF ใช้พิกัด "ก่อนหมุนหน้า" (unrotated) ทั้งตอนอ่านข้อความและตอนเขียน
ส่วนหน้าจอแสดงพิกัด "หลังหมุน" (visible) — ฟังก์ชันที่รับ visible จะแปลงให้เองด้วย
page.derotation_matrix
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import pymupdf

from .textrender import TextStyle, render_text_pdf
from .utils import group_runs, parse_page_range

Color = tuple[float, float, float]


# ───────────────────────── พิกัด ─────────────────────────
def vis_to_unrot_rect(page: pymupdf.Page, rect: pymupdf.Rect) -> pymupdf.Rect:
    r = pymupdf.Rect(rect) * page.derotation_matrix
    r.normalize()
    return r


def vis_to_unrot_point(page: pymupdf.Page, p: tuple[float, float]) -> pymupdf.Point:
    return pymupdf.Point(p) * page.derotation_matrix


def unrot_to_vis_rect(page: pymupdf.Page, rect: pymupdf.Rect) -> pymupdf.Rect:
    r = pymupdf.Rect(rect) * page.rotation_matrix
    r.normalize()
    return r


# ───────────────────────── จัดการหน้า ─────────────────────────
def rotate_pages(doc: pymupdf.Document, idxs: Iterable[int], delta: int) -> None:
    for i in idxs:
        p = doc[i]
        p.set_rotation((p.rotation + delta) % 360)


def delete_pages(doc: pymupdf.Document, idxs: Iterable[int]) -> None:
    idxs = sorted(set(idxs))
    if len(idxs) >= doc.page_count:
        raise ValueError("ลบทุกหน้าไม่ได้ — เอกสารต้องมีอย่างน้อย 1 หน้า")
    doc.delete_pages(idxs)


def insert_blank_page(doc: pymupdf.Document, after: int, like: int | None = None) -> int:
    ref = doc[like if like is not None else max(after, 0)]
    r = ref.rect
    doc.new_page(pno=after + 1, width=r.width, height=r.height)
    return after + 1


def duplicate_pages(doc: pymupdf.Document, idxs: Iterable[int]) -> None:
    for i in sorted(set(idxs), reverse=True):
        doc.fullcopy_page(i, i + 1)


def reorder_pages(doc: pymupdf.Document, order: list[int]) -> None:
    if sorted(order) != list(range(doc.page_count)):
        raise ValueError("ลำดับหน้าไม่ถูกต้อง")
    doc.select(order)


def extract_pages(doc: pymupdf.Document, idxs: list[int], out_path: str | os.PathLike) -> None:
    new = pymupdf.open()
    for a, b in group_runs(sorted(set(idxs))):
        new.insert_pdf(doc, from_page=a, to_page=b)
    new.save(str(out_path), garbage=3, deflate=True)
    new.close()


def insert_pdf_at(doc: pymupdf.Document, src: pymupdf.Document, pages: list[int], at: int) -> int:
    """แทรกหน้า `pages` ของ src เข้าที่ตำแหน่ง at (0 = หน้าแรก, page_count = ท้ายสุด)"""
    n = 0
    pos = at
    for a, b in group_runs(pages):
        doc.insert_pdf(src, from_page=a, to_page=b, start_at=pos)
        pos += b - a + 1
        n += b - a + 1
    return n


# ───────────────────────── เปิดไฟล์ ─────────────────────────
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}


def open_any(path: str | os.PathLike, password: str | None = None) -> pymupdf.Document:
    """เปิด PDF หรือรูปภาพ (แปลงเป็น PDF) — ยกข้อยกเว้นถ้าต้องใช้รหัสผ่าน"""
    p = Path(path)
    if p.suffix.lower() in IMAGE_EXTS:
        img = pymupdf.open(str(p))
        pdfbytes = img.convert_to_pdf()
        img.close()
        return pymupdf.open("pdf", pdfbytes)
    data = p.read_bytes()
    doc = pymupdf.open("pdf", data)
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            doc.close()
            raise PermissionError("ต้องใช้รหัสผ่าน")
    return doc


# ───────────────────────── ตั้งรหัสผ่านเอกสาร ─────────────────────────
def build_permissions(no_print: bool = False, no_copy: bool = False, no_edit: bool = False) -> int:
    """สร้างบิตสิทธิ์ของผู้เปิดไฟล์ (ด้วยรหัสผู้ใช้) — ค่าเริ่มต้นอนุญาตทุกอย่าง"""
    perm = (pymupdf.PDF_PERM_ACCESSIBILITY | pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
            | pymupdf.PDF_PERM_COPY | pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ANNOTATE
            | pymupdf.PDF_PERM_FORM | pymupdf.PDF_PERM_ASSEMBLE)
    if no_print:
        perm &= ~(pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ)
    if no_copy:
        perm &= ~pymupdf.PDF_PERM_COPY
    if no_edit:
        perm &= ~(pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ANNOTATE | pymupdf.PDF_PERM_FORM | pymupdf.PDF_PERM_ASSEMBLE)
    return int(perm)


def save_protected(doc: pymupdf.Document, out_path: str | os.PathLike, user_pw: str, owner_pw: str = "",
                   no_print: bool = False, no_copy: bool = False, no_edit: bool = False) -> None:
    """บันทึกสำเนาที่เข้ารหัส AES-256 — ต้องใส่ user_pw ถึงจะเปิดไฟล์ได้
    owner_pw ใช้ปลดข้อจำกัดสิทธิ์ (ถ้าไม่ระบุแต่มีข้อจำกัด จะสร้างรหัสสุ่มให้ ซึ่งจะไม่มีใครรู้)"""
    import secrets

    if len(user_pw) < 4:
        raise ValueError("รหัสผ่านสั้นเกินไป (อย่างน้อย 4 ตัวอักษร)")
    restricted = no_print or no_copy or no_edit
    owner = owner_pw or (secrets.token_urlsafe(18) if restricted else user_pw)
    out = Path(out_path)
    tmp = out.with_suffix(".tmp_pdfgovernix")
    try:
        doc.save(str(tmp), garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                 user_pw=user_pw, owner_pw=owner, permissions=build_permissions(no_print, no_copy, no_edit))
        tmp.replace(out)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def protect_file(src: str | os.PathLike, out_path: str | os.PathLike, user_pw: str, owner_pw: str = "",
                 no_print: bool = False, no_copy: bool = False, no_edit: bool = False) -> None:
    """เข้ารหัสไฟล์ PDF ทั้งไฟล์ (ไฟล์ที่มีรหัสอยู่แล้วต้องเปิดด้วยรหัสเดิมก่อน → ข้ามโดยยกข้อยกเว้น)"""
    doc = open_any(src)
    try:
        save_protected(doc, out_path, user_pw, owner_pw, no_print, no_copy, no_edit)
    finally:
        doc.close()


# ───────────────────────── รวมไฟล์ ─────────────────────────
@dataclass
class MergeItem:
    path: str
    page_range: str = ""        # ว่าง = ทั้งหมด
    password: str | None = None
    title: str = ""


def merge_files(
    items: list[MergeItem],
    out_path: str | os.PathLike,
    bookmarks: bool = False,
    progress: Callable[[int, int, str], bool] | None = None,
) -> int:
    """รวมไฟล์ตามลำดับ คืนจำนวนหน้ารวม — progress(i, total, name) คืน False เพื่อยกเลิก"""
    out = pymupdf.open()
    toc: list[list] = []
    try:
        for n, item in enumerate(items):
            name = Path(item.path).name
            if progress and progress(n, len(items), name) is False:
                raise InterruptedError("ยกเลิกการรวมไฟล์")
            src = open_any(item.path, item.password)
            try:
                pages = parse_page_range(item.page_range, src.page_count)
                start = out.page_count
                for a, b in group_runs(pages):
                    out.insert_pdf(src, from_page=a, to_page=b)
                toc.append([1, item.title or Path(item.path).stem, start + 1])
            finally:
                src.close()
        if bookmarks and toc:
            out.set_toc(toc)
        out.save(str(out_path), garbage=3, deflate=True)
        return out.page_count
    finally:
        out.close()


# ───────────────────────── มาร์กอัป ─────────────────────────
def hex_to_rgb(h: str) -> Color:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def add_text_markup(page: pymupdf.Page, kind: str, quads: list[pymupdf.Quad], color: Color) -> None:
    """kind: highlight | underline | strike — quads เป็นพิกัด unrotated"""
    fn = {
        "highlight": page.add_highlight_annot,
        "underline": page.add_underline_annot,
        "strike": page.add_strikeout_annot,
    }[kind]
    annot = fn(quads=quads)
    annot.set_colors(stroke=color)
    annot.update()


def add_ink(page: pymupdf.Page, points_vis: list[tuple[float, float]], color: Color, width: float) -> None:
    pts = [tuple(vis_to_unrot_point(page, p)) for p in points_vis]
    if len(pts) < 2:
        pts = pts * 2
    annot = page.add_ink_annot([pts])
    annot.set_colors(stroke=color)
    annot.set_border(width=width)
    annot.update()


def add_text(page: pymupdf.Page, rect_vis: pymupdf.Rect, text: str, style: TextStyle) -> pymupdf.Rect:
    """วางข้อความ (เวกเตอร์ ผ่าน Qt) ที่มุมซ้ายบนของ rect_vis กว้างตาม rect — คืน rect ที่ใช้จริง (visible)"""
    data, w, h = render_text_pdf(text, style, rect_vis.width)
    vis = pymupdf.Rect(rect_vis.x0, rect_vis.y0, rect_vis.x0 + w, rect_vis.y0 + h)
    _overlay_pdf(page, vis, data)
    return vis


def _overlay_pdf(page: pymupdf.Page, rect_vis: pymupdf.Rect, pdf_bytes: bytes, overlay: bool = True) -> None:
    src = pymupdf.open("pdf", pdf_bytes)
    try:
        page.show_pdf_page(vis_to_unrot_rect(page, rect_vis), src, 0, rotate=page.rotation, overlay=overlay)
    finally:
        src.close()


def add_watermark(doc: pymupdf.Document, pages: list[int], *, text: str = "", style: TextStyle | None = None,
                  image: bytes | None = None, opacity: float = 0.25, angle: float = 45.0, tile: bool = False,
                  img_frac: float = 0.5, behind: bool = False) -> None:
    """ใส่ลายน้ำ (ข้อความหรือรูป) ลงหน้าที่ระบุ — โปร่งแสง หมุนได้ วางกลางหน้าหรือซ้ำทั่วหน้า"""
    from PySide6.QtGui import QImage

    from .textrender import render_watermark_pdf

    img = QImage.fromData(image) if image else None
    if image and (img is None or img.isNull()):
        raise ValueError("อ่านไฟล์รูปภาพลายน้ำไม่ได้")
    if img is None and not text.strip():
        raise ValueError("ยังไม่ได้ใส่ข้อความลายน้ำ")
    cache: dict[tuple[float, float], bytes] = {}
    for pno in pages:
        page = doc[pno]
        r = page.rect
        key = (round(r.width, 1), round(r.height, 1))
        if key not in cache:
            cache[key] = render_watermark_pdf(r.width, r.height, text=text, style=style, image=img,
                                              opacity=opacity, angle=angle, tile=tile, img_frac=img_frac)
        _overlay_pdf(page, r, cache[key], overlay=not behind)


def add_image(page: pymupdf.Page, rect_vis: pymupdf.Rect, path: str, keep_proportion: bool = True) -> None:
    page.insert_image(
        vis_to_unrot_rect(page, rect_vis),
        filename=path,
        keep_proportion=keep_proportion,
        rotate=page.rotation,
        overlay=True,
    )


def redact_area(page: pymupdf.Page, rect_vis: pymupdf.Rect, fill: Color) -> None:
    """ลบเนื้อหาในกรอบ (ข้อความ/ภาพ) ถาวร แล้วเทสี fill"""
    page.add_redact_annot(vis_to_unrot_rect(page, rect_vis), fill=fill)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)


# ───────────────────────── แก้ข้อความเดิม ─────────────────────────
@dataclass
class TextProbe:
    text: str = ""
    size: float = 12.0
    color: str = "#000000"
    bold: bool = False
    italic: bool = False
    bbox_vis: pymupdf.Rect = field(default_factory=lambda: pymupdf.Rect())


def probe_text(page: pymupdf.Page, rect_vis: pymupdf.Rect) -> TextProbe:
    """อ่านข้อความ/ขนาด/สี ของข้อความเดิมในกรอบ เพื่อเติมให้ในหน้าต่างแก้ไข"""
    clip = vis_to_unrot_rect(page, rect_vis)
    d = page.get_text("dict", clip=clip)
    lines: list[str] = []
    sizes: list[float] = []
    color = 0
    flags = 0
    bbox: pymupdf.Rect | None = None
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            lb = pymupdf.Rect(ln["bbox"])
            if not lb.intersects(clip):
                continue
            txt = "".join(s["text"] for s in ln["spans"])
            if not txt.strip():
                continue
            lines.append(txt.rstrip())
            bbox = lb if bbox is None else bbox | lb
            for s in ln["spans"]:
                if s["text"].strip():
                    sizes.append(s["size"])
                    color, flags = s["color"], s["flags"]
    probe = TextProbe()
    if lines:
        probe.text = "\n".join(lines)
        probe.size = round(sorted(sizes)[len(sizes) // 2], 1)
        probe.color = "#{:06x}".format(color)
        probe.bold = bool(flags & 16)
        probe.italic = bool(flags & 2)
        probe.bbox_vis = unrot_to_vis_rect(page, bbox)  # type: ignore[arg-type]
    return probe


def background_color(page: pymupdf.Page, rect_vis: pymupdf.Rect) -> Color:
    """เดาสีพื้นหลังบริเวณกรอบ จากพิกเซลขอบ (ใช้เป็นสีปิดทับตอนแก้ข้อความ)"""
    try:
        pad = 2
        r = pymupdf.Rect(rect_vis.x0 - pad, rect_vis.y0 - pad, rect_vis.x1 + pad, rect_vis.y1 + pad)
        r = r & page.rect
        pix = page.get_pixmap(clip=r, alpha=False, annots=False)
        samples = []
        for x, y in ((0, 0), (pix.width - 1, 0), (0, pix.height - 1), (pix.width - 1, pix.height - 1)):
            samples.append(pix.pixel(x, y))
        samples.sort()
        s = samples[len(samples) // 2]
        return (s[0] / 255, s[1] / 255, s[2] / 255)
    except Exception:
        return (1.0, 1.0, 1.0)


def replace_text(page: pymupdf.Page, rect_vis: pymupdf.Rect, new_text: str, style: TextStyle) -> None:
    """ลบข้อความเดิมในกรอบ (พื้นหลังกลมกลืน) แล้วเขียนข้อความใหม่ทับตำแหน่งเดิม"""
    fill = background_color(page, rect_vis)
    redact_area(page, rect_vis, fill)
    if new_text.strip():
        # ใช้ความกว้างตามธรรมชาติของข้อความ ถ้าไม่ล้นขอบหน้า มิฉะนั้นตัดบรรทัดตามพื้นที่ที่เหลือ
        avail = max(20.0, page.rect.x1 - 12 - rect_vis.x0)
        _, natural_w, _ = render_text_pdf(new_text, style, None)
        width = max(rect_vis.width * 1.05, natural_w + 2)
        data, w, h = render_text_pdf(new_text, style, min(width, avail))
        _overlay_pdf(page, pymupdf.Rect(rect_vis.x0, rect_vis.y0, rect_vis.x0 + w, rect_vis.y0 + h), data)
