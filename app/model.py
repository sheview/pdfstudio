"""โมเดลเอกสาร: เก็บ pymupdf.Document + ประวัติย้อนกลับ/ทำซ้ำ (แบบ snapshot)"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pymupdf
from PySide6.QtCore import QObject, Signal

from . import objects as objs_mod
from . import ops
from .config import MAX_UNDO
from .objects import FloatObj


class PdfModel(QObject):
    changed = Signal()          # เนื้อหา/โครงสร้างเปลี่ยน (รวมถึง undo/redo)
    dirtyChanged = Signal(bool)

    def __init__(self, doc: pymupdf.Document, path: str | None = None, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.path = path
        self.was_encrypted = False
        self.objects: list[FloatObj] = []     # วัตถุลอย (รูป/ข้อความ) ที่ยังไม่ฝังลงเอกสาร
        self._undo: list[tuple[bytes, list[FloatObj]]] = []
        self._redo: list[tuple[bytes, list[FloatObj]]] = []
        self._dirty = False
        self.version = 0
        self._current = self._snapshot()

    # ── สร้าง ──
    @classmethod
    def open_path(cls, path: str, password: str | None = None) -> "PdfModel":
        p = Path(path)
        doc = ops.open_any(p, password)
        is_image = p.suffix.lower() in ops.IMAGE_EXTS
        m = cls(doc, None if is_image else str(p))
        m.was_encrypted = bool(password)
        if is_image:
            m._set_dirty(True)
        return m

    @classmethod
    def blank(cls) -> "PdfModel":
        doc = pymupdf.open()
        doc.new_page(width=595, height=842)
        return cls(doc, None)

    # ── สถานะ ──
    @property
    def dirty(self) -> bool:
        return self._dirty

    def _set_dirty(self, v: bool) -> None:
        if v != self._dirty:
            self._dirty = v
            self.dirtyChanged.emit(v)

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    @property
    def title(self) -> str:
        return Path(self.path).name if self.path else "ไม่มีชื่อ.pdf"

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    # ── วัตถุลอย ──
    def objects_on(self, page: int) -> list[FloatObj]:
        return [o for o in self.objects if o.page == page]

    def find_object(self, uid: int | None) -> FloatObj | None:
        if uid is None:
            return None
        return next((o for o in self.objects if o.uid == uid), None)

    def flatten(self, pages: set[int] | None = None) -> set[int]:
        """ฝังวัตถุลอยลงเนื้อหาเอกสาร (pages=None คือทุกหน้า) คืนเลขหน้าที่ถูกฝัง — ไม่ commit"""
        chosen = [o for o in self.objects if pages is None or o.page in pages]
        if not chosen:
            return set()
        objs_mod.bake_all(self.doc, chosen)
        done = {o.page for o in chosen}
        gone = {o.uid for o in chosen}
        self.objects = [o for o in self.objects if o.uid not in gone]
        return done

    @contextmanager
    def baked(self):
        """เอกสารที่ฝังวัตถุลอยแล้ว (สำเนาชั่วคราว) สำหรับบันทึก/พิมพ์/ส่งออก"""
        if not self.objects:
            yield self.doc
            return
        tmp = pymupdf.open("pdf", self.doc.tobytes(garbage=0, deflate=False, encryption=pymupdf.PDF_ENCRYPT_NONE))
        try:
            objs_mod.bake_all(tmp, self.objects)
            yield tmp
        finally:
            tmp.close()

    # ── snapshot ──
    def _snapshot(self, data: bytes | None = None) -> tuple[bytes, list[FloatObj]]:
        if data is None:
            data = self.doc.tobytes(garbage=0, deflate=False, encryption=pymupdf.PDF_ENCRYPT_NONE)
        return data, [o.clone() for o in self.objects]

    def commit(self, doc_changed: bool = True) -> None:
        """เรียกหลังแก้ไขเสร็จ เพื่อบันทึกจุดย้อนกลับ (doc_changed=False เมื่อแก้เฉพาะวัตถุลอย → ไม่ต้องสร้างไฟล์ใหม่)"""
        self._undo.append(self._current)
        if len(self._undo) > MAX_UNDO:
            self._undo.pop(0)
        self._redo.clear()
        self._current = self._snapshot(None if doc_changed else self._current[0])
        self.version += 1
        self._set_dirty(True)
        self.changed.emit()

    def _load(self, snap: tuple[bytes, list[FloatObj]]) -> None:
        old = self.doc
        self.doc = pymupdf.open("pdf", snap[0])
        old.close()
        self.objects = [o.clone() for o in snap[1]]
        self._current = snap
        self.version += 1

    def _restore(self, snap: tuple[bytes, list[FloatObj]]) -> None:
        self._load(snap)
        self._set_dirty(True)
        self.changed.emit()

    def revert(self) -> None:
        """ย้อนเอกสารกลับเป็นสถานะล่าสุดที่ commit (ใช้เมื่อการแก้ไขล้มเหลวกลางทาง)"""
        self._load(self._current)
        self.changed.emit()

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(self._current)
        self._restore(self._undo.pop())

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._current)
        self._restore(self._redo.pop())

    # ── บันทึก ──
    def save(self, path: str | None = None) -> str:
        target = path or self.path
        if not target:
            raise ValueError("ยังไม่มีชื่อไฟล์")
        tmp = Path(target).with_suffix(".tmp_pdfgovernix")
        try:
            with self.baked() as d:
                d.save(str(tmp), garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_NONE)
            tmp.replace(target)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        self.path = str(target)
        self._set_dirty(False)
        return self.path
