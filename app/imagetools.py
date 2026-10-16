"""เครื่องมือแก้ภาพ: ครอป และลบพื้นหลัง (ทำงานในเครื่อง ไม่ต้องใช้อินเทอร์เน็ต)"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageOps

MAX_WORK_PX = 2400          # ย่อรูปใหญ่มากก่อนประมวลผล (ลายเซ็น/โลโก้ไม่จำเป็นต้องละเอียดกว่านี้)


def load_image(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    return im


def has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)


def encode(im: Image.Image, prefer_jpeg: bool = False) -> bytes:
    buf = io.BytesIO()
    if prefer_jpeg and not has_alpha(im):
        im.convert("RGB").save(buf, "JPEG", quality=92)
    else:
        im.convert("RGBA").save(buf, "PNG", optimize=False)
    return buf.getvalue()


# ───────────────────────── ครอป ─────────────────────────
def crop_image(data: bytes, box: tuple[float, float, float, float]) -> tuple[bytes, tuple[float, float, float, float]]:
    """box = (x0, y0, x1, y1) เป็นสัดส่วน 0..1 ของภาพ → (ข้อมูลภาพใหม่, box ที่ปรับให้เป็นพิกเซลจริงแล้ว)"""
    im = load_image(data)
    w, h = im.size
    x0, y0, x1, y1 = box
    px = (max(0, round(x0 * w)), max(0, round(y0 * h)), min(w, round(x1 * w)), min(h, round(y1 * h)))
    if px[2] - px[0] < 2 or px[3] - px[1] < 2:
        raise ValueError("พื้นที่ครอปเล็กเกินไป")
    jpeg = (im.format or "").upper() in ("JPEG", "JPG") or data[:3] == b"\xff\xd8\xff"
    out = im.crop(px)
    real = (px[0] / w, px[1] / h, px[2] / w, px[3] / h)
    return encode(out, prefer_jpeg=jpeg), real


# ───────────────────────── ลบพื้นหลัง ─────────────────────────
def guess_background(rgb: np.ndarray) -> tuple[int, int, int]:
    """เดาสีพื้นหลังจากสีที่พบมากที่สุดบริเวณขอบภาพ"""
    h, w = rgb.shape[:2]
    t = max(1, int(min(h, w) * 0.03))
    edge = np.concatenate([rgb[:t].reshape(-1, 3), rgb[-t:].reshape(-1, 3),
                           rgb[:, :t].reshape(-1, 3), rgb[:, -t:].reshape(-1, 3)])
    q = (edge // 16).astype(np.int32)
    key = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    vals, counts = np.unique(key, return_counts=True)
    best = vals[np.argmax(counts)]
    sel = edge[key == best]
    return tuple(int(v) for v in np.median(sel, axis=0))


def _run_or(reach: np.ndarray, cand: np.ndarray, axis: int) -> np.ndarray:
    """ขยายพื้นที่ reach ไปตามช่วงต่อเนื่องของ cand ตามแถว (axis=1) หรือตามคอลัมน์ (axis=0)"""
    if axis == 0:
        reach, cand = reach.T, cand.T
    h, w = cand.shape
    pad = np.zeros((h, 1), bool)
    c = np.concatenate([cand, pad], axis=1).ravel()
    r = np.concatenate([reach & cand, pad], axis=1).ravel()
    prev = np.concatenate([[False], c[:-1]])
    rid = np.cumsum(c & ~prev)
    ids = rid[c]
    hit = np.bincount(ids, weights=r[c].astype(np.float64), minlength=int(rid[-1]) + 1) > 0
    out = np.zeros_like(c)
    out[c] = hit[ids]
    out = out.reshape(h, w + 1)[:, :w]
    return out.T if axis == 0 else out


def connected_from_border(cand: np.ndarray) -> np.ndarray:
    """พื้นที่ของ cand ที่เชื่อมถึงขอบภาพ (4-connectivity) — ใช้แยก 'พื้นหลังจริง' ออกจากสีเดียวกันที่อยู่ในตัวภาพ"""
    seed = np.zeros_like(cand)
    seed[0, :] = seed[-1, :] = True
    seed[:, 0] = seed[:, -1] = True
    reach = seed & cand
    for _ in range(600):
        nxt = _run_or(_run_or(reach, cand, 1), cand, 0)
        if np.array_equal(nxt, reach):
            break
        reach = nxt
    return reach


def remove_background(rgba: np.ndarray, bg: tuple[int, int, int], tolerance: float = 30.0,
                      softness: float = 25.0, contiguous: bool = True) -> np.ndarray:
    """ทำสีพื้นหลังให้โปร่งใส

    tolerance 0..100  = สีที่ต่างจากพื้นหลังไม่เกินเท่าไรถือเป็นพื้นหลัง
    softness  0..100  = ความนุ่มของขอบ (ไล่ความโปร่งใสแทนการตัดคมๆ)
    contiguous        = ลบเฉพาะพื้นที่สีเดียวกันที่ติดขอบภาพ (ไม่ลบสีเดียวกันที่อยู่ในตัวภาพ เช่น ตาขาว)
                        ปิด = ลบทุกจุดที่สีใกล้เคียง (เหมาะกับลายเซ็น/ตัวหนังสือที่มีช่องว่างในตัวอักษร)
    """
    rgb = rgba[..., :3].astype(np.float32)
    a0 = rgba[..., 3].astype(np.float32) / 255.0
    bgv = np.array(bg, np.float32)
    dist = np.sqrt(((rgb - bgv) ** 2).sum(axis=2)) / math.sqrt(3.0)          # 0..255
    t0 = tolerance * 1.6
    width = 1.0 + softness * 1.2
    alpha = np.clip((dist - t0) / width, 0.0, 1.0)
    if contiguous:
        reach = connected_from_border(dist <= t0 + width)
        alpha = np.where(reach, alpha, 1.0)
    # ถอดสีพื้นหลังที่เจือในขอบกึ่งโปร่งใสออก (ขอบไม่เป็นเส้นขาว)
    a = np.maximum(alpha, 1e-3)[..., None]
    clean = np.clip((rgb - (1.0 - a) * bgv) / a, 0, 255)
    out = np.empty_like(rgba)
    semi = (alpha < 0.999)[..., None]
    out[..., :3] = np.where(semi, clean, rgb).astype(np.uint8)
    out[..., 3] = np.round(alpha * a0 * 255).astype(np.uint8)
    return out


def remove_background_bytes(data: bytes, bg: tuple[int, int, int] | None, tolerance: float, softness: float,
                            contiguous: bool, trim: bool = True) -> tuple[bytes, tuple[float, float, float, float]]:
    """คืน (PNG ใหม่, กรอบเนื้อหาเป็นสัดส่วนของภาพเดิม) — กรอบใช้ปรับตำแหน่ง/ขนาดวัตถุเมื่อตัดขอบว่างทิ้ง"""
    im = load_image(data).convert("RGBA")
    if max(im.size) > MAX_WORK_PX:
        k = MAX_WORK_PX / max(im.size)
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    arr = np.array(im)
    color = bg or guess_background(arr[..., :3])
    res = remove_background(arr, color, tolerance, softness, contiguous)
    out = Image.fromarray(res, "RGBA")
    frac = (0.0, 0.0, 1.0, 1.0)
    if trim:
        bbox = out.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        if bbox and (bbox[2] - bbox[0]) >= 2 and (bbox[3] - bbox[1]) >= 2:
            w, h = out.size
            pad = 2
            bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(w, bbox[2] + pad), min(h, bbox[3] + pad))
            out = out.crop(bbox)
            frac = (bbox[0] / w, bbox[1] / h, bbox[2] / w, bbox[3] / h)
    return encode(out), frac
