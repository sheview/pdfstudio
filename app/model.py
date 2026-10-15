"""โมเดลเอกสาร: เก็บ pymupdf.Document + ประวัติย้อนกลับ/ทำซ้ำ (แบบ snapshot)"""
from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import QObject, Signal

from . import ops
from .config import MAX_UNDO


class PdfModel(QObject):
    changed = Signal()          # เนื้อหา/โครงสร้างเปลี่ยน (รวมถึง undo/redo)
    dirtyChanged = Signal(bool)

    def __init__(self, doc: pymupdf.Document, path: str | None = None, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.path = path
        self.was_encrypted = False
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []
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

    # ── snapshot ──
    def _snapshot(self) -> bytes:
        return self.doc.tobytes(garbage=0, deflate=False, encryption=pymupdf.PDF_ENCRYPT_NONE)

    def commit(self) -> None:
        """เรียกหลังแก้ไขเอกสารเสร็จ เพื่อบันทึกจุดย้อนกลับ"""
        self._undo.append(self._current)
        if len(self._undo) > MAX_UNDO:
            self._undo.pop(0)
        self._redo.clear()
        self._current = self._snapshot()
        self.version += 1
        self._set_dirty(True)
        self.changed.emit()

    def _restore(self, data: bytes) -> None:
        old = self.doc
        self.doc = pymupdf.open("pdf", data)
        old.close()
        self._current = data
        self.version += 1
        self._set_dirty(True)
        self.changed.emit()

    def revert(self) -> None:
        """ย้อนเอกสารกลับเป็นสถานะล่าสุดที่ commit (ใช้เมื่อการแก้ไขล้มเหลวกลางทาง)"""
        old = self.doc
        self.doc = pymupdf.open("pdf", self._current)
        old.close()
        self.version += 1
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
        tmp = Path(target).with_suffix(".tmp_pdfstudio")
        try:
            self.doc.save(str(tmp), garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_NONE)
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
