"""ฝังข้อมูล "ชั้นที่แก้ไขต่อได้" (รูป/ข้อความลอย) ไว้ในไฟล์ PDF ที่บันทึก

ตอนบันทึก รูป/ข้อความจะถูกฝังลงหน้ากระดาษจริงเพื่อให้โปรแกรมอื่นเห็นตรงกัน
เราจึงแนบสำเนาก่อนฝัง + ตำแหน่งของแต่ละชิ้นไว้ในไฟล์เดียวกัน (ไฟล์แนบ PDF) —
ครั้งหน้าเปิดไฟล์ด้วย Governix PDF จะกู้รูป/ข้อความกลับมาเป็นวัตถุที่ย้าย/ย่อขยาย/แก้ไขได้อีก
ถ้าไฟล์ถูกแก้ด้วยโปรแกรมอื่นหลังจากนั้น (ลายนิ้วมือเนื้อหาไม่ตรง) จะไม่กู้คืน เพื่อไม่ให้ทับงานของคนอื่น
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pymupdf

from .objects import FloatObj
from .textrender import TextStyle

EMBED_NAME = "governix-editable.zip"
_VERSION = 1


def digest(doc: pymupdf.Document) -> str:
    h = hashlib.sha256()
    h.update(str(doc.page_count).encode())
    for p in doc:
        r = p.rect
        h.update(f"|{r.width:.2f},{r.height:.2f},{p.rotation}|".encode())
        try:
            h.update(p.read_contents())
        except Exception:
            pass
    return h.hexdigest()


def pack(base_pdf: bytes, objs: list[FloatObj], dg: str) -> bytes:
    meta = {"v": _VERSION, "digest": dg, "objects": []}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("base.pdf", base_pdf)
        for n, o in enumerate(objs):
            item = {"kind": o.kind, "page": o.page, "x": o.x, "y": o.y, "w": o.w, "h": o.h,
                    "text": o.text, "style": o.style.__dict__}
            if o.data:
                item["file"] = f"obj{n}.bin"
                z.writestr(item["file"], o.data)
            meta["objects"].append(item)
        z.writestr("meta.json", json.dumps(meta, ensure_ascii=False))
    return buf.getvalue()


def attach(doc: pymupdf.Document, payload: bytes) -> None:
    if EMBED_NAME in (doc.embfile_names() or []):
        doc.embfile_del(EMBED_NAME)
    doc.embfile_add(EMBED_NAME, payload, filename=EMBED_NAME, desc="Governix PDF editable layers")


def try_restore(doc: pymupdf.Document) -> tuple[bytes, list[FloatObj]] | None:
    """คืน (ไบต์ของเอกสารก่อนฝัง, วัตถุ) ถ้าไฟล์นี้มีข้อมูลแก้ไขต่อได้และยังตรงกับเนื้อหา — ไม่งั้น None"""
    try:
        if EMBED_NAME not in (doc.embfile_names() or []):
            return None
        z = zipfile.ZipFile(io.BytesIO(doc.embfile_get(EMBED_NAME)))
        meta = json.loads(z.read("meta.json").decode("utf-8"))
        if meta.get("v") != _VERSION or meta.get("digest") != digest(doc):
            return None
        base = z.read("base.pdf")
        objs: list[FloatObj] = []
        fields = set(TextStyle.__dataclass_fields__)
        for it in meta["objects"]:
            style = TextStyle(**{k: v for k, v in it.get("style", {}).items() if k in fields})
            data = z.read(it["file"]) if it.get("file") else b""
            objs.append(FloatObj(it["kind"], int(it["page"]), float(it["x"]), float(it["y"]),
                                 float(it["w"]), float(it["h"]), data=data, text=it.get("text", ""), style=style))
        return base, objs
    except Exception:
        return None
