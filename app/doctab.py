"""แท็บเอกสาร 1 ไฟล์: ภาพย่อ + ตัวแสดงผล + การแก้ไขทั้งหมดของเอกสารนั้น"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Callable

import pymupdf
from PySide6.QtCore import QBuffer, QIODevice, QMimeData, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import objects as objmod
from . import ops, printing
from . import exporters, imagetools
from .qrtool import QrDialog
from .imgdialogs import CropDialog, ExportOptionsDialog, RemoveBgDialog
from .dialogs import ExportImageDialog, InsertPdfDialog, SplitDialog, TextDialog, WatermarkDialog
from .model import PdfModel
from .signatures import SignatureDialog
from .textrender import TextStyle, default_thai_font
from .utils import parse_page_range
from .viewer import PdfView, Tool
from .widgets import SearchBar, ThumbList, make_thumb_pixmap, make_thumb_placeholder


def _flat_icon(pm: QPixmap) -> QIcon:
    """ไอคอนที่ไม่ถูกย้อมสีเวลาเลือก (Qt ปกติจะทาสีฟ้าทับ)"""
    ic = QIcon()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active, QIcon.Mode.Disabled):
        ic.addPixmap(pm, mode)
    return ic


class DocTab(QWidget):
    stateChanged = Signal()           # เปลี่ยนหน้า/ซูม/เลือกข้อความ/ประวัติ — ให้หน้าต่างหลักอัปเดตปุ่ม
    titleChanged = Signal()
    message = Signal(str)

    def __init__(self, model: PdfModel, win):
        super().__init__()
        self.model = model
        self.win = win
        self._suppress = False
        self._sync_lock = False
        self._thumb_job = 0
        self._thumb_todo: list[int] = []
        self._hits: list[tuple[int, int]] = []
        self._hit_idx = -1
        self._warned_encrypt = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        root.addWidget(self.splitter)

        # ── ภาพย่อ ──
        self.thumb_panel = QWidget()
        self.thumb_panel.setObjectName("ThumbPanel")
        self.thumb_panel.setMinimumWidth(170)
        self.thumb_panel.setMaximumWidth(280)
        tv = QVBoxLayout(self.thumb_panel)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(0)
        title = QLabel("หน้าเอกสาร")
        title.setObjectName("PanelTitle")
        tv.addWidget(title)
        self.thumbs = ThumbList()
        tv.addWidget(self.thumbs, 1)
        self.splitter.addWidget(self.thumb_panel)

        # ── พื้นที่แสดงผล ──
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.search = SearchBar()
        self.search.setVisible(False)
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 8, 14, 0)
        wl.addStretch(1)
        wl.addWidget(self.search)
        self.search_wrap = wrap
        wrap.setVisible(False)
        rv.addWidget(wrap)
        self.view = PdfView()
        rv.addWidget(self.view, 1)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([190, 1000])

        # ── เชื่อมสัญญาณ ──
        v = self.view
        v.pageChanged.connect(self._on_page_changed)
        v.zoomChanged.connect(lambda _: self.stateChanged.emit())
        v.fitModeChanged.connect(lambda _: self.stateChanged.emit())
        v.selectionChanged.connect(lambda _: self.stateChanged.emit())
        v.rectDrawn.connect(self.on_rect)
        v.inkDrawn.connect(self.on_ink)
        v.markupReady.connect(self.on_markup)
        v.get_objects = lambda: self.model.objects
        v.objectsChanged.connect(self._objects_edited)
        v.objectEditRequested.connect(self.edit_object)
        v.objectDeleteRequested.connect(self.delete_object)
        v.objectContextRequested.connect(self._object_menu)
        v.objectSelectionChanged.connect(lambda: self.stateChanged.emit())
        v.contextRequested.connect(self._view_menu)
        self.thumbs.itemClicked.connect(lambda it: self._goto(it.data(Qt.ItemDataRole.UserRole)))
        self.thumbs.itemSelectionChanged.connect(lambda: self.stateChanged.emit())
        self.thumbs.reordered.connect(self.on_reorder)
        self.thumbs.deleteRequested.connect(self.delete_pages)
        self.thumbs.customContextMenuRequested.connect(self._thumb_menu)
        self.thumbs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search.searchRequested.connect(self._do_search)
        self.search.nextRequested.connect(lambda: self._step_hit(1))
        self.search.prevRequested.connect(lambda: self._step_hit(-1))
        self.search.closed.connect(self.close_search)
        self.model.changed.connect(self._on_model_changed)
        self.model.dirtyChanged.connect(lambda _: self.titleChanged.emit())

        self.apply_tool_state()
        self.view.set_document(self.model.doc)
        self.rebuild_thumbs()
        self._select_thumb(0)

    # ───────────────────────── สถานะ ─────────────────────────
    @property
    def doc(self) -> pymupdf.Document:
        return self.model.doc

    def title(self) -> str:
        return self.model.title + (" •" if self.model.dirty else "")

    def apply_tool_state(self) -> None:
        w = self.win
        self.view.pen_color = QColor(w.pen_color)
        self.view.pen_width = w.pen_width
        self.view.set_tool(w.tool)

    def selected_pages(self) -> list[int]:
        sel = self.thumbs.selected_pages()
        return sel or [self.view.current_page]

    def has_page_selection(self) -> bool:
        return bool(self.thumbs.selectedItems())

    # ───────────────────────── รีเฟรช ─────────────────────────
    def _on_model_changed(self) -> None:
        if self._suppress:
            return
        self.full_refresh()

    def full_refresh(self, select: list[int] | None = None) -> None:
        self.view.set_document(self.model.doc, reset_view=False)
        self.rebuild_thumbs(select)
        self.titleChanged.emit()
        self.stateChanged.emit()

    def partial_refresh(self, pages: list[int]) -> None:
        self.view.invalidate(pages)
        for i in pages:
            self._render_thumb(i)
        self.titleChanged.emit()
        self.stateChanged.emit()

    # ───────────────────────── ภาพย่อ ─────────────────────────
    def rebuild_thumbs(self, select: list[int] | None = None) -> None:
        keep = select if select is not None else self.thumbs.selected_pages()
        n = self.model.page_count
        dpr = self.devicePixelRatioF()
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        for i in range(n):
            it = QListWidgetItem(_flat_icon(make_thumb_placeholder(i + 1, dpr)), "")
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.thumbs.addItem(it)
        for i in keep:
            if 0 <= i < n:
                self.thumbs.item(i).setSelected(True)
        self.thumbs.blockSignals(False)
        self._thumb_job += 1
        self._thumb_todo = sorted(range(n), key=lambda k: abs(k - self.view.current_page))
        QTimer.singleShot(0, lambda job=self._thumb_job: self._thumb_step(job))

    def _thumb_step(self, job: int) -> None:
        if job != self._thumb_job:
            return
        for _ in range(4):
            if not self._thumb_todo:
                return
            self._render_thumb(self._thumb_todo.pop(0))
        QTimer.singleShot(0, lambda: self._thumb_step(job))

    def _render_thumb(self, i: int) -> None:
        if not (0 <= i < self.thumbs.count()):
            return
        try:
            objs = self.model.objects_on(i)
            if objs:   # ภาพย่อต้องเห็นรูป/ข้อความที่วางไว้ด้วย → ฝังลงสำเนาหน้าเดียวชั่วคราว
                tmp = pymupdf.open()
                try:
                    tmp.insert_pdf(self.model.doc, from_page=i, to_page=i)
                    objmod.bake_all(tmp, [dataclasses.replace(o, page=0) for o in objs])
                    pm = make_thumb_pixmap(tmp[0], i + 1, self.devicePixelRatioF())
                finally:
                    tmp.close()
            else:
                pm = make_thumb_pixmap(self.model.doc[i], i + 1, self.devicePixelRatioF())
            self.thumbs.item(i).setIcon(_flat_icon(pm))
        except Exception as e:  # ภาพย่อพังไม่ควรทำให้โปรแกรมล้ม
            print("thumb error:", e)

    def _select_thumb(self, i: int) -> None:
        if not (0 <= i < self.thumbs.count()):
            return
        self._sync_lock = True
        try:
            if len(self.thumbs.selectedItems()) <= 1:
                self.thumbs.blockSignals(True)
                self.thumbs.clearSelection()
                self.thumbs.item(i).setSelected(True)
                self.thumbs.setCurrentRow(i)
                self.thumbs.blockSignals(False)
            self.thumbs.scrollToItem(self.thumbs.item(i), self.thumbs.ScrollHint.EnsureVisible)
        finally:
            self._sync_lock = False

    def _on_page_changed(self, i: int) -> None:
        self._select_thumb(i)
        self.stateChanged.emit()

    def _goto(self, i: int) -> None:
        self.view.go_to_page(i)

    def go_to_page(self, i: int) -> None:
        self.view.go_to_page(i)
        self._select_thumb(i)

    # ───────────────────────── ใช้การแก้ไข ─────────────────────────
    def _apply(self, fn: Callable[[pymupdf.Document], None], pages: list[int] | None = None,
               select: list[int] | None = None, focus: int | None = None,
               flatten: set[int] | None = None, remap: dict[int, list[int]] | None = None) -> bool:
        """ทำการแก้ไข → commit → รีเฟรช (pages=None คือโครงสร้างเปลี่ยน ต้องรีเฟรชทั้งหมด)

        วัตถุลอย (รูป/ข้อความ) จะถูกฝังลงเอกสารก่อนเมื่อการแก้ไขกระทบโครงสร้างหน้า (pages=None)
        หรือกระทบหน้าที่ระบุใน flatten (เช่น ลบ/ปิดข้อมูลลับ ต้องลบของใต้วัตถุด้วย)"""
        self._suppress = True
        touched: set[int] = set()
        try:
            if pages is None and remap is None:
                touched = self.model.flatten(None)
            elif flatten:
                touched = self.model.flatten(flatten)
            fn(self.model.doc)
            if remap is not None:               # จัดหน้าใหม่ → ย้ายรูป/ข้อความตามไปด้วย (ยังแก้ไขต่อได้)
                self.model.remap_objects(remap)
            self.model.commit()
        except Exception as e:
            self._suppress = False
            self.model.revert()
            QMessageBox.warning(self.window(), "ทำรายการไม่สำเร็จ", str(e))
            return False
        self._suppress = False
        if pages is None:
            self.full_refresh(select)
            if focus is not None:
                self.go_to_page(focus)
        else:
            self.partial_refresh(sorted(set(pages) | touched))
        return True

    # ───────────────────────── เครื่องมือบนหน้า ─────────────────────────
    def _rect(self, r: QRectF) -> pymupdf.Rect:
        return pymupdf.Rect(r.left(), r.top(), r.right(), r.bottom())

    def on_rect(self, page: int, r: QRectF) -> None:
        tool = self.view.tool
        rect = self._rect(r)
        doc = self.model.doc
        if tool == Tool.TEXT:
            dlg = TextDialog(self.window(), "ใส่ข้อความ", "", self.win.text_style_copy())
            if dlg.exec() != TextDialog.DialogCode.Accepted:
                return
            text, style = dlg.text_value(), dlg.style_value()
            self.win.remember_text_style(style)
            if text.strip():
                pw = self.view.sizes[page][0]
                x = min(max(r.x(), 0.0), max(pw - 40.0, 0.0))
                obj = objmod.make_text(page, x, r.y(), min(r.width(), max(pw - x, 40.0)), text, style)
                self.add_object(obj)
                self.win.set_tool(Tool.SELECT)
                self.message.emit("วางข้อความแล้ว — ลากเพื่อย้าย • ลากมุมเพื่อย่อ/ขยาย • ดับเบิลคลิกเพื่อแก้ไข • กด Delete เพื่อลบ")
        elif tool == Tool.EDIT_TEXT:
            probe = ops.probe_text(doc[page], rect)
            if not probe.text.strip():
                QMessageBox.information(
                    self.window(), "ไม่พบข้อความ",
                    "ไม่พบข้อความเดิมในกรอบที่ลาก\n\nถ้าเอกสารเป็นภาพสแกน ให้ใช้ “ลบ/ปิดทับ” ลบของเดิม แล้ว “ใส่ข้อความ” พิมพ์ใหม่แทน",
                )
                return
            base = self.win.text_style_copy()
            style = TextStyle(family=base.family or default_thai_font(), size=probe.size, color=probe.color,
                              bold=probe.bold, italic=probe.italic)
            dlg = TextDialog(self.window(), "แก้ไขข้อความเดิม", probe.text, style, deletable=True,
                             sub="ข้อความเดิมจะถูกแทนที่ด้วยกล่องข้อความใหม่ (ย้าย/แก้ต่อได้) • ปล่อยว่างหรือกด “ลบข้อความนี้” เพื่อลบ")
            if dlg.exec() != TextDialog.DialogCode.Accepted:
                return
            new, nstyle = dlg.text_value(), dlg.style_value()
            area = probe.bbox_vis
            fill = ops.background_color(doc[page], area)
            if dlg.deleted or not new.strip():
                if self._apply(lambda d: ops.redact_area(d[page], area, fill), [page]):
                    self.message.emit("ลบข้อความเดิมแล้ว (กด Ctrl+Z เพื่อย้อนกลับ)")
                return
            self.win.remember_text_style(nstyle)
            pw = self.view.sizes[page][0]
            avail = max(20.0, pw - 12 - area.x0)
            _, natural_w = objmod.measure_text(new, nstyle, None)
            width = min(max(area.width * 1.05, natural_w + 2), avail)
            obj = objmod.make_text(page, area.x0, area.y0, width, new, nstyle)

            def run(d: pymupdf.Document) -> None:
                ops.redact_area(d[page], area, fill)
                self.model.objects.append(obj)

            if self._apply(run, [page]):
                self.view.select_object(obj.uid)
                self.message.emit("แก้ข้อความแล้ว — ลากย้าย/ดับเบิลคลิกแก้ต่อได้ กด Delete เพื่อลบ")
        elif tool == Tool.IMAGE:
            dlg = SignatureDialog(self.window(), self.win.start_dir())
            if dlg.exec() == SignatureDialog.DialogCode.Accepted and dlg.chosen:
                try:
                    data = Path(dlg.chosen).read_bytes()
                    iw, ih = objmod.image_size(data)
                    if iw <= 0:
                        raise ValueError("อ่านไฟล์รูปภาพไม่ได้")
                    pw, ph = self.view.sizes[page]
                    if r.width() < 20 and r.height() < 20:       # คลิกเฉยๆ → ขนาดมาตรฐาน กึ่งกลางที่จุดคลิก
                        width = min(180.0, pw * 0.35)
                    else:                                       # ลากกรอบ → พอดีกรอบ (คงสัดส่วน)
                        width = min(r.width(), r.height() * iw / ih)
                    obj = objmod.make_image(page, data, r.center().x(), r.center().y(), width, (pw, ph))
                except Exception as e:
                    QMessageBox.warning(self.window(), "ใส่รูปไม่สำเร็จ", str(e))
                    return
                self.add_object(obj)
                self.win.set_tool(Tool.SELECT)
                self.message.emit("วางรูปแล้ว — ลากเพื่อย้าย • ลากมุมเพื่อปรับขนาด (กด Shift = ยืดอิสระ) • กด Delete เพื่อลบ")
        elif tool == Tool.ERASE:
            fill = ops.background_color(doc[page], rect)
            self._apply(lambda d: ops.redact_area(d[page], rect, fill), [page], flatten={page})
        elif tool == Tool.REDACT:
            self._apply(lambda d: ops.redact_area(d[page], rect, (0, 0, 0)), [page], flatten={page})

    def on_ink(self, page: int, pts: list) -> None:
        c = self.view.pen_color
        col = (c.redF(), c.greenF(), c.blueF())
        w = self.view.pen_width
        self._apply(lambda d: ops.add_ink(d[page], pts, col, w), [page])

    def on_markup(self, kind: str) -> None:
        sel = self.view.selection_quads()
        if not sel:
            return
        page, quads = sel
        c = self.win.markup_color if kind == "highlight" else self.win.line_color
        col = (c.redF(), c.greenF(), c.blueF())
        self.view.clear_selection(emit=False)
        self._apply(lambda d: ops.add_text_markup(d[page], kind, quads, col), [page])

    def apply_markup_to_selection(self, kind: str) -> None:
        if self.view.has_selection():
            self.on_markup(kind)
        else:
            self.message.emit("เลือกข้อความก่อน (ลากเมาส์คลุมข้อความด้วยเครื่องมือ “เลือก”)")

    # ───────────────────────── ลายน้ำ ─────────────────────────
    def add_watermark(self) -> None:
        dlg = WatermarkDialog(self.window(), self.model.doc, self.view.current_page, self.win.start_dir(),
                              self.win.text_style_copy())
        if dlg.exec() != WatermarkDialog.DialogCode.Accepted:
            return
        pages, kw = dlg.pages(), dlg.kwargs()
        if self._apply(lambda d: ops.add_watermark(d, pages, **kw), pages):
            self.message.emit(f"ใส่ลายน้ำแล้ว {len(pages)} หน้า (ย้อนกลับได้ด้วย Ctrl+Z)")

    # ───────────────────────── วัตถุลอย (รูป / ข้อความ) ─────────────────────────
    OBJ_MIME = "application/x-pdfgovernix-object"

    def _commit_objects(self, pages: list[int]) -> None:
        """บันทึกจุดย้อนกลับหลังแก้วัตถุลอย โดยไม่ต้องโหลดเอกสารใหม่ทั้งหมด"""
        self._suppress = True
        try:
            self.model.commit(doc_changed=False)
        finally:
            self._suppress = False
        self.view.canvas.update()
        for i in pages:
            self._render_thumb(i)
        self.titleChanged.emit()
        self.stateChanged.emit()

    def _objects_edited(self, pages: list) -> None:
        self._commit_objects(pages)

    def add_object(self, obj: objmod.FloatObj) -> None:
        self.model.objects.append(obj)
        self._commit_objects([obj.page])
        self.view.select_object(obj.uid)

    def selected_object(self) -> objmod.FloatObj | None:
        return self.view.selected_object()

    def selected_objects(self) -> list[objmod.FloatObj]:
        return self.view.selected_objects()

    def delete_object(self, uids=None) -> None:
        if isinstance(uids, int):
            uids = [uids]
        objs = [q for q in (self.model.find_object(u) for u in uids) if q is not None] if uids else self.selected_objects()
        if not objs:
            return
        gone = {o.uid for o in objs}
        self.model.objects = [q for q in self.model.objects if q.uid not in gone]
        self.view.select_object(None)
        self._commit_objects(sorted({o.page for o in objs}))
        self.message.emit(f"ลบ {len(objs)} รายการแล้ว (กด Ctrl+Z เพื่อย้อนกลับ)" if len(objs) > 1
                          else "ลบแล้ว (กด Ctrl+Z เพื่อย้อนกลับ)")

    def edit_object(self, uid: int | None = None) -> None:
        o = self.model.find_object(uid) if uid is not None else self.selected_object()
        if o is None or not o.is_text:
            return
        dlg = TextDialog(self.window(), "แก้ไขข้อความ", o.text, dataclasses.replace(o.style), deletable=True,
                         sub="ปรับข้อความ ฟอนต์ ขนาด สี ได้ — ตำแหน่งและความกว้างเดิมจะคงไว้")
        if dlg.exec() != TextDialog.DialogCode.Accepted:
            return
        text, style = dlg.text_value(), dlg.style_value()
        if dlg.deleted or not text.strip():
            self.delete_object(o.uid)
            return
        self.win.remember_text_style(style)
        o.text, o.style = text, style
        objmod.relayout(o)
        self._commit_objects([o.page])

    # ── QR Code / ผลจากเครื่องคิดเลข ──
    def add_qr(self) -> None:
        dlg = QrDialog(self.window())
        if dlg.exec() != QrDialog.DialogCode.Accepted:
            return
        png, caption, width = dlg.values()
        page = self.view.current_page
        size = self.view.sizes[page]
        c = self.view.visible_center(page)
        qr = objmod.make_image(page, png, c.x(), c.y(), width, size)
        new = [qr]
        if caption:
            st = TextStyle(family=default_thai_font(), size=9.5, align="center")
            cap = objmod.make_text(page, qr.x, qr.y + qr.h + 2, qr.w, caption, st)
            new.append(cap)
        self.model.objects.extend(new)
        self._commit_objects([page])
        self.view.select_objects([o.uid for o in new])
        self.message.emit("วาง QR Code แล้ว — ลากย้าย/ย่อขยายได้ (ลองสแกนด้วยมือถือก่อนแจกลูกค้า)")

    def insert_png(self, data: bytes) -> None:
        """วางรูป (เช่น ตารางงวดเงิน) กลางส่วนที่มองเห็นของหน้าปัจจุบัน"""
        page = self.view.current_page
        pw, ph = self.view.sizes[page]
        iw, _ = objmod.image_size(data)
        c = self.view.visible_center(page)
        o = objmod.make_image(page, data, c.x(), c.y(), min(iw / 2.0, pw - 40), (pw, ph))
        self.add_object(o)

    def insert_text_value(self, text: str) -> None:
        page = self.view.current_page
        pw, _ = self.view.sizes[page]
        c = self.view.visible_center(page)
        o = objmod.make_text(page, max(c.x() - 80, 0.0), c.y(), 160, text, self.win.text_style_copy())
        self.add_object(o)

    def page_text(self) -> str:
        return self.model.doc[self.view.current_page].get_text()

    # ── แก้ไขรูป: ครอป / ลบพื้นหลัง ──
    def _selected_image(self) -> objmod.FloatObj | None:
        o = self.selected_object()
        return o if o is not None and not o.is_text else None

    def _apply_image_edit(self, o: objmod.FloatObj, data: bytes, frac: tuple[float, float, float, float]) -> None:
        """เปลี่ยนข้อมูลรูป โดยให้ส่วนที่เหลืออยู่ตำแหน่ง/ขนาดเดิมบนหน้า (frac = ส่วนของภาพเดิมที่ยังเก็บไว้)"""
        x0, y0, x1, y1 = frac
        o.x, o.y = o.x + x0 * o.w, o.y + y0 * o.h
        o.w, o.h = max(objmod.MIN_SIZE, o.w * (x1 - x0)), max(objmod.MIN_SIZE, o.h * (y1 - y0))
        o.data = data
        self._commit_objects([o.page])
        self.view.select_object(o.uid)

    def crop_object(self) -> None:
        o = self._selected_image()
        if o is None:
            self.message.emit("เลือกรูปก่อน แล้วค่อยกดครอป")
            return
        dlg = CropDialog(self.window(), o.data)
        if dlg.exec() != CropDialog.DialogCode.Accepted:
            return
        try:
            data, real = imagetools.crop_image(o.data, dlg.fractions())
        except Exception as e:
            QMessageBox.warning(self.window(), "ครอปรูป", str(e))
            return
        self._apply_image_edit(o, data, real)
        self.message.emit("ครอปรูปแล้ว (กด Ctrl+Z เพื่อย้อนกลับ)")

    def remove_bg_object(self) -> None:
        o = self._selected_image()
        if o is None:
            self.message.emit("เลือกรูปก่อน แล้วค่อยกดลบพื้นหลัง")
            return
        dlg = RemoveBgDialog(self.window(), o.data)
        if dlg.exec() != RemoveBgDialog.DialogCode.Accepted:
            return
        try:
            data, frac = dlg.result()
        except Exception as e:
            QMessageBox.warning(self.window(), "ลบพื้นหลัง", str(e))
            return
        self._apply_image_edit(o, data, frac)
        self.message.emit("ลบพื้นหลังแล้ว (กด Ctrl+Z เพื่อย้อนกลับ)")

    def _clone_near(self, o: objmod.FloatObj) -> objmod.FloatObj:
        c = o.clone(new_uid=True)
        pw, ph = self.view.sizes[min(c.page, len(self.view.sizes) - 1)]
        c.x = min(c.x + 14, max(pw - c.w, 0.0))
        c.y = min(c.y + 14, max(ph - c.h, 0.0))
        return c

    def duplicate_object(self) -> None:
        objs = self.selected_objects()
        if not objs:
            return
        new = [self._clone_near(o) for o in objs]
        self.model.objects.extend(new)
        self._commit_objects(sorted({c.page for c in new}))
        self.view.select_objects([c.uid for c in new])

    def copy_object(self) -> bool:
        objs = self.selected_objects()
        if not objs:
            return False
        self.win.obj_clipboard = [o.clone() for o in objs]
        md = QMimeData()
        md.setData(self.OBJ_MIME, ",".join(str(o.uid) for o in objs).encode())
        first = objs[0]
        if len(objs) == 1 and first.is_text:
            md.setText(first.text)
        else:
            img_obj = next((o for o in objs if not o.is_text), None)
            img = QImage.fromData(img_obj.data) if img_obj else QImage()
            if not img.isNull():
                md.setImageData(img)
        QGuiApplication.clipboard().setMimeData(md)
        self.message.emit(f"คัดลอก {len(objs)} รายการแล้ว — กด Ctrl+V เพื่อวาง" if len(objs) > 1
                          else "คัดลอกแล้ว — กด Ctrl+V เพื่อวาง")
        return True

    def paste_object(self) -> None:
        page = self.view.current_page
        pw, ph = self.view.sizes[page]
        md = QGuiApplication.clipboard().mimeData()
        src = self.win.obj_clipboard
        if isinstance(src, objmod.FloatObj):
            src = [src]
        new: list[objmod.FloatObj] = []
        if md is not None and src and md.hasFormat(self.OBJ_MIME) \
                and bytes(md.data(self.OBJ_MIME)).decode() == ",".join(str(o.uid) for o in src):
            new = [o.clone(new_uid=True) for o in src]
            # จัดกลุ่มให้อยู่กึ่งกลางส่วนที่มองเห็น โดยคงตำแหน่งสัมพัทธ์ของแต่ละชิ้นไว้
            x0, y0 = min(o.x for o in new), min(o.y for o in new)
            x1, y1 = max(o.x + o.w for o in new), max(o.y + o.h for o in new)
            c = self.view.visible_center(page)
            dx = c.x() - (x0 + x1) / 2
            dy = c.y() - (y0 + y1) / 2
            dx = min(max(dx, -x0), max(pw - x1, -x0))
            dy = min(max(dy, -y0), max(ph - y1, -y0))
            if any(o.page == page for o in src) and abs(x0 + dx - min(o.x for o in src)) < 6 \
                    and abs(y0 + dy - min(o.y for o in src)) < 6:
                dx, dy = dx + 14, dy + 14
                dx = min(dx, max(pw - x1, 0.0))
                dy = min(dy, max(ph - y1, 0.0))
            for o in new:
                o.page = page
                o.x += dx
                o.y += dy
        else:
            o = None
            if md is not None and md.hasImage():
                img = QGuiApplication.clipboard().image()
                if not img.isNull():
                    buf = QBuffer()
                    buf.open(QIODevice.OpenModeFlag.WriteOnly)
                    img.save(buf, "PNG")
                    o = objmod.make_image(page, bytes(buf.data()), 0, 0, min(220.0, pw * 0.4), (pw, ph))
            elif md is not None and md.hasText() and md.text().strip():
                o = objmod.make_text(page, 0, 0, min(300.0, pw * 0.6), md.text().strip(), self.win.text_style_copy())
            if o is not None:
                c = self.view.visible_center(page)
                o.x = min(max(c.x() - o.w / 2, 0.0), max(pw - o.w, 0.0))
                o.y = min(max(c.y() - o.h / 2, 0.0), max(ph - o.h, 0.0))
                new = [o]
        if not new:
            self.message.emit("ไม่มีรูปหรือข้อความในคลิปบอร์ดให้วาง")
            return
        self.model.objects.extend(new)
        self._commit_objects([page])
        self.view.select_objects([o.uid for o in new])
        if len(new) > 1:
            self.message.emit(f"วาง {len(new)} รายการแล้ว")

    def reorder_object(self, front: bool) -> None:
        objs = self.selected_objects()
        if not objs:
            return
        gone = {o.uid for o in objs}
        rest = [q for q in self.model.objects if q.uid not in gone]
        moved = [q for q in self.model.objects if q.uid in gone]      # คงลำดับซ้อนกันเดิมในกลุ่ม
        self.model.objects = rest + moved if front else moved + rest
        self._commit_objects(sorted({o.page for o in objs}))

    def _object_menu(self, pos, uid: int) -> None:
        w = self.win
        o = self.model.find_object(uid)
        if o is None:
            return
        m = QMenu(self)
        if o.is_text and len(self.selected_objects()) <= 1:
            m.addAction("แก้ไขข้อความ…", lambda: self.edit_object(uid))
            m.addSeparator()
        if not o.is_text and len(self.selected_objects()) <= 1:
            m.addAction(w.act_img_crop)
            m.addAction(w.act_img_removebg)
            m.addSeparator()
        for a in (w.act_copy, w.act_paste, w.act_obj_dup, w.act_obj_front, w.act_obj_back):
            m.addAction(a)
        m.addSeparator()
        m.addAction(w.act_obj_delete)
        m.exec(pos)

    # ───────────────────────── จัดการหน้า ─────────────────────────
    def rotate(self, delta: int) -> None:
        pages = self.selected_pages()
        self._apply(lambda d: ops.rotate_pages(d, pages, delta), None, select=pages)

    def delete_pages(self) -> None:
        pages = self.selected_pages()
        if len(pages) >= self.model.page_count:
            QMessageBox.information(self.window(), "ลบหน้า", "ลบทุกหน้าไม่ได้ — เอกสารต้องมีอย่างน้อย 1 หน้า")
            return
        label = f"หน้า {pages[0] + 1}" if len(pages) == 1 else f"{len(pages)} หน้า ({', '.join(str(p + 1) for p in pages[:8])}{'…' if len(pages) > 8 else ''})"
        if QMessageBox.question(self.window(), "ลบหน้า", f"ต้องการลบ {label} ใช่หรือไม่?\n(ย้อนกลับได้ด้วย Ctrl+Z)") != QMessageBox.StandardButton.Yes:
            return
        nxt = min(pages[0], self.model.page_count - len(pages) - 1)
        n = self.model.page_count
        gone = set(pages)
        keep = [i for i in range(n) if i not in gone]
        remap = {old: ([keep.index(old)] if old in keep else []) for old in range(n)}
        self._apply(lambda d: ops.delete_pages(d, pages), None, select=[nxt], focus=nxt, remap=remap)

    def insert_blank(self) -> None:
        after = max(self.selected_pages())
        n = self.model.page_count
        remap = {old: [old if old <= after else old + 1] for old in range(n)}
        self._apply(lambda d: ops.insert_blank_page(d, after), None, select=[after + 1], focus=after + 1, remap=remap)

    def duplicate(self) -> None:
        pages = self.selected_pages()
        sel = [p + 1 + k for k, p in enumerate(pages)]
        dups = sorted(set(pages))
        remap = {}
        for old in range(self.model.page_count):
            new = old + sum(1 for q in dups if q < old)
            remap[old] = [new, new + 1] if old in dups else [new]
        self._apply(lambda d: ops.duplicate_pages(d, pages), None, select=sel, focus=sel[0], remap=remap)

    def move(self, direction: int) -> None:
        pages = self.selected_pages()
        n = self.model.page_count
        if (direction < 0 and pages[0] == 0) or (direction > 0 and pages[-1] == n - 1):
            return
        order = list(range(n))
        block = pages[:]
        if direction < 0:
            for p in block:
                order[p - 1], order[p] = order[p], order[p - 1]
        else:
            for p in reversed(block):
                order[p + 1], order[p] = order[p], order[p + 1]
        new_sel = [order.index(p) for p in pages]
        self._apply(lambda d: ops.reorder_pages(d, order), None, select=new_sel, focus=new_sel[0],
                    remap={old: [new] for new, old in enumerate(order)})

    def on_reorder(self, order: list[int], moved: list[int]) -> None:
        """ผู้ใช้ลากภาพย่อสลับลำดับ — order คือเลขหน้าเดิมตามลำดับใหม่, moved คือตำแหน่งใหม่ของหน้าที่ถูกลาก"""
        self._apply(lambda d: ops.reorder_pages(d, order), None, select=moved, focus=moved[0] if moved else None,
                    remap={old: [new] for new, old in enumerate(order)})

    def insert_pdf(self) -> None:
        dlg = InsertPdfDialog(self.window(), max(self.selected_pages()), self.model.page_count, self.win.start_dir())
        if dlg.exec() != InsertPdfDialog.DialogCode.Accepted:
            return
        path, pw, pages, at = dlg.values()
        self.win.remember_dir(path)

        def run(d: pymupdf.Document) -> None:
            src = ops.open_any(path, pw)
            try:
                ops.insert_pdf_at(d, src, pages, at)
            finally:
                src.close()

        sel = list(range(at, at + len(pages)))
        remap = {old: [old if old < at else old + len(pages)] for old in range(self.model.page_count)}
        self._apply(run, None, select=sel, focus=at, remap=remap)

    def split_pages(self) -> None:
        n = self.model.page_count
        preset = ""
        if self.has_page_selection():
            sel = self.selected_pages()
            preset = ", ".join(str(p + 1) for p in sel)
        dlg = SplitDialog(self.window(), n, preset)
        if dlg.exec() != SplitDialog.DialogCode.Accepted:
            return
        pages, each = dlg.values()
        base = Path(self.model.path).stem if self.model.path else "เอกสาร"
        start = str(Path(self.model.path).parent) if self.model.path else self.win.start_dir()
        try:
            if each:
                folder = QFileDialog.getExistingDirectory(self.window(), "เลือกโฟลเดอร์ปลายทาง", start)
                if not folder:
                    return
                width = len(str(n))
                with self.model.baked() as src:
                    for p in pages:
                        ops.extract_pages(src, [p], Path(folder) / f"{base}_หน้า{p + 1:0{width}d}.pdf")
                self.message.emit(f"แยกเป็น {len(pages)} ไฟล์แล้วที่ {folder}")
            else:
                out, _ = QFileDialog.getSaveFileName(self.window(), "บันทึกหน้าที่แยก", str(Path(start) / f"{base}_แยก.pdf"), "PDF (*.pdf)")
                if not out:
                    return
                if not out.lower().endswith(".pdf"):
                    out += ".pdf"
                with self.model.baked() as src:
                    ops.extract_pages(src, pages, out)
                self.message.emit(f"บันทึก {len(pages)} หน้าไปที่ {out}")
                if QMessageBox.question(self.window(), "แยกหน้าเสร็จแล้ว", "ต้องการเปิดไฟล์ที่แยกออกมาเลยหรือไม่?") == QMessageBox.StandardButton.Yes:
                    self.win.open_files([out])
        except Exception as e:
            QMessageBox.critical(self.window(), "แยกหน้าไม่สำเร็จ", str(e))

    def export_images(self) -> None:
        n = self.model.page_count
        preset = ", ".join(str(p + 1) for p in self.selected_pages()) if self.has_page_selection() else ""
        dlg = ExportImageDialog(self.window(), n, preset)
        if dlg.exec() != ExportImageDialog.DialogCode.Accepted:
            return
        pages, fmt, dpi = dlg.values()
        start = str(Path(self.model.path).parent) if self.model.path else self.win.start_dir()
        folder = QFileDialog.getExistingDirectory(self.window(), "เลือกโฟลเดอร์ปลายทาง", start)
        if not folder:
            return
        base = Path(self.model.path).stem if self.model.path else "เอกสาร"
        width = len(str(n))
        try:
            with self.model.baked() as src:
                for p in pages:
                    pix = src[p].get_pixmap(dpi=dpi, alpha=False)
                    pix.save(str(Path(folder) / f"{base}_หน้า{p + 1:0{width}d}.{fmt}"))
            self.message.emit(f"ส่งออก {len(pages)} รูปไปที่ {folder}")
        except Exception as e:
            QMessageBox.critical(self.window(), "ส่งออกไม่สำเร็จ", str(e))

    # ───────────────────────── ค้นหา ─────────────────────────
    def open_search(self) -> None:
        self.search_wrap.setVisible(True)
        self.search.setVisible(True)
        self.search.focus_edit()

    def close_search(self) -> None:
        self.search_wrap.setVisible(False)
        self.view.clear_search()
        self._hits, self._hit_idx = [], -1
        self.view.setFocus()

    def _do_search(self, text: str) -> None:
        self._hits = self.view.search(text) if text.strip() else []
        if text.strip() and not self._hits:
            self.search.set_count(0, 0, text)
            return
        self._hit_idx = -1
        if self._hits:
            # เริ่มจากผลที่อยู่ในหรือหลังหน้าปัจจุบัน
            cur = self.view.current_page
            self._hit_idx = next((k for k, (p, _) in enumerate(self._hits) if p >= cur), 0) - 1
            self._step_hit(1)
        else:
            self.search.set_count(0, 0, "")

    def _step_hit(self, d: int) -> None:
        if not self._hits:
            return
        self._hit_idx = (self._hit_idx + d) % len(self._hits)
        self.view.show_hit(self._hits[self._hit_idx])
        self.search.set_count(self._hit_idx + 1, len(self._hits), "x")

    # ───────────────────────── เมนูคลิกขวา ─────────────────────────
    def _view_menu(self, pos, page: int, has_sel: bool) -> None:
        w = self.win
        if page not in self.thumbs.selected_pages():
            self.thumbs.clearSelection()
            if 0 <= page < self.thumbs.count():
                self.thumbs.item(page).setSelected(True)
        m = QMenu(self)
        if has_sel:
            for a in (w.act_copy, w.act_highlight_sel, w.act_underline_sel, w.act_strike_sel):
                m.addAction(a)
            m.addSeparator()
        for a in (w.act_rotate_left, w.act_rotate_right, w.act_delete, w.act_insert_blank, w.act_duplicate):
            m.addAction(a)
        m.addSeparator()
        for a in (w.act_fit_width, w.act_fit_page):
            m.addAction(a)
        m.exec(pos)

    def _thumb_menu(self, pos) -> None:
        w = self.win
        m = QMenu(self)
        for a in (w.act_rotate_left, w.act_rotate_right, w.act_delete, w.act_duplicate, w.act_insert_blank):
            m.addAction(a)
        m.addSeparator()
        for a in (w.act_move_up, w.act_move_down, w.act_split):
            m.addAction(a)
        m.exec(self.thumbs.viewport().mapToGlobal(pos))

    # ───────────────────────── ไฟล์ / พิมพ์ ─────────────────────────
    def save(self) -> bool:
        if not self.model.path:
            return self.save_as()
        return self._save_to(None)

    SAVE_FILTERS = "PDF (*.pdf);;Word (*.docx);;รูปภาพ JPEG (*.jpg *.jpeg)"

    def save_as(self) -> bool:
        base = Path(self.model.path).with_suffix("") if self.model.path else Path(self.win.start_dir()) / "เอกสารใหม่"
        out, flt = QFileDialog.getSaveFileName(self.window(), "บันทึกเป็น", str(base) + ".pdf", self.SAVE_FILTERS)
        if not out:
            return False
        ext = Path(out).suffix.lower()
        if ext not in (".pdf", ".docx", ".jpg", ".jpeg"):
            ext = ".docx" if "Word" in flt else (".jpg" if "JPEG" in flt else ".pdf")
            out += ext
        if ext == ".docx":
            return self._export_docx(out)
        if ext in (".jpg", ".jpeg"):
            return self._export_jpeg(out)
        return self._save_to(out)

    def _export_pages_preset(self) -> str:
        sel = self.selected_pages() if self.has_page_selection() else []
        return ", ".join(str(p + 1) for p in sel) if len(sel) > 1 else ""      # เลือกหลายหน้าไว้ → ใส่ให้เลย ไม่งั้นทุกหน้า

    def _export_jpeg(self, out: str) -> bool:
        dlg = ExportOptionsDialog(self.window(), "jpg", self.model.page_count, self.view.current_page,
                                  self._export_pages_preset())
        if dlg.exec() != ExportOptionsDialog.DialogCode.Accepted:
            return False
        v = dlg.values()
        try:
            with self.model.baked() as d:
                files = exporters.export_jpeg(d, out, v["pages"], v["dpi"], v["quality"],
                                              progress=lambda n, t: QApplication.processEvents())
        except Exception as e:
            QMessageBox.critical(self.window(), "บันทึกเป็นรูปไม่สำเร็จ", str(e))
            return False
        self.message.emit(f"บันทึกเป็นรูป JPEG แล้ว {len(files)} ไฟล์: {files[0] if len(files) == 1 else str(Path(out).parent)}")
        return True

    def _export_docx(self, out: str) -> bool:
        dlg = ExportOptionsDialog(self.window(), "docx", self.model.page_count, self.view.current_page,
                                  self._export_pages_preset())
        if dlg.exec() != ExportOptionsDialog.DialogCode.Accepted:
            return False
        v = dlg.values()
        prog = QProgressDialog("กำลังแปลงเป็น Word…", None, 0, 0, self.window())
        prog.setWindowTitle("บันทึกเป็น Word")
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(0)
        prog.show()
        try:
            with self.model.baked() as d:
                if v["editable"]:
                    fn = lambda: exporters.export_docx_editable(d, out, v["pages"])  # noqa: E731
                else:
                    fn = lambda: exporters.export_docx_images(d, out, v["pages"])  # noqa: E731
                exporters.run_in_thread(fn, QApplication.processEvents)
        except Exception as e:
            prog.close()
            QMessageBox.critical(self.window(), "บันทึกเป็น Word ไม่สำเร็จ", str(e))
            return False
        prog.close()
        self.message.emit(f"บันทึกเป็น Word แล้ว: {out}")
        return True

    def _save_to(self, path: str | None) -> bool:
        if self.model.was_encrypted and not self._warned_encrypt:
            self._warned_encrypt = True
            QMessageBox.information(self.window(), "หมายเหตุ", "ไฟล์ต้นฉบับมีรหัสผ่าน — ไฟล์ที่บันทึกจะไม่มีรหัสผ่าน")
        try:
            saved = self.model.save(path)
        except PermissionError:
            QMessageBox.critical(
                self.window(), "บันทึกไม่ได้",
                "ไม่สามารถเขียนไฟล์ได้ — ไฟล์อาจถูกเปิดอยู่ในโปรแกรมอื่น หรือไม่มีสิทธิ์เขียน\n\nปิดไฟล์นั้นก่อน หรือเลือก “บันทึกเป็น” ชื่อใหม่",
            )
            return False
        except Exception as e:
            QMessageBox.critical(self.window(), "บันทึกไม่สำเร็จ", str(e))
            return False
        self.win.remember_recent(saved)
        self.titleChanged.emit()
        self.message.emit(f"บันทึกแล้ว: {saved}")
        return True

    def maybe_save(self) -> bool:
        """ถามบันทึกก่อนปิด — คืน True ถ้าปิดได้"""
        if not self.model.dirty:
            return True
        box = QMessageBox(self.window())
        box.setWindowTitle("บันทึกการเปลี่ยนแปลง?")
        box.setText(f"“{self.model.title}” มีการแก้ไขที่ยังไม่ได้บันทึก")
        box.setIcon(QMessageBox.Icon.Question)
        save = box.addButton("บันทึก", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("ไม่บันทึก", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("ยกเลิก", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is save:
            return self.save()
        return box.clickedButton() is discard

    def print_(self) -> None:
        with self.model.baked() as d:
            printing.print_document(self.window(), d, self.view.current_page, self.model.title)

    def print_system(self) -> None:
        """ทางสำรอง: เปิดไฟล์ในโปรแกรมอ่าน PDF ของเครื่องเพื่อสั่งพิมพ์จากที่นั่น"""
        try:
            with self.model.baked() as d:
                printing.print_via_system(d, self.model.title)
            self.message.emit("เปิดเอกสารในโปรแกรมอ่าน PDF ของเครื่องแล้ว — สั่งพิมพ์ (Ctrl+P) จากโปรแกรมนั้นได้เลย")
        except Exception as e:
            QMessageBox.warning(self.window(), "พิมพ์ผ่านระบบ", f"เปิดไฟล์ไม่ได้: {e}")

    def print_preview(self) -> None:
        with self.model.baked() as d:
            printing.print_preview(self.window(), d, self.view.current_page, self.model.title)
