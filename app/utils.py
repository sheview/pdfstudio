from __future__ import annotations

import datetime as _dt
import re

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]


def parse_page_range(text: str, total: int) -> list[int]:
    """แปลงข้อความเช่น "1-3, 5, 8-" เป็นรายการหน้า (เริ่มที่ 0)

    ว่าง / "ทั้งหมด" / "all" = ทุกหน้า
    """
    t = (text or "").strip().lower().translate(THAI_DIGITS)
    if t in ("", "all", "ทั้งหมด", "*"):
        return list(range(total))
    result: list[int] = []
    for part in re.split(r"[,\s;]+", t):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)[-–:](\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else total
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(f"รูปแบบช่วงหน้าไม่ถูกต้อง: “{part}”")
        if a < 1 or b > total or a > b:
            raise ValueError(f"ช่วงหน้า “{part}” อยู่นอกขอบเขต (ไฟล์นี้มี 1-{total} หน้า)")
        result.extend(range(a - 1, b))
    if not result:
        raise ValueError("ไม่ได้ระบุหน้า")
    return result


def format_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def thai_date(d: _dt.date | None = None) -> str:
    d = d or _dt.date.today()
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year + 543}"


def thai_date_short(d: _dt.date | None = None) -> str:
    d = d or _dt.date.today()
    return f"{d.day:02d}/{d.month:02d}/{d.year + 543}"


def group_runs(indices: list[int]) -> list[tuple[int, int]]:
    """จัดลำดับหน้าที่ต่อเนื่องกันเป็นช่วง (a, b) เพื่อ insert_pdf ทีละช่วง"""
    runs: list[tuple[int, int]] = []
    for i in indices:
        if runs and runs[-1][1] + 1 == i:
            runs[-1] = (runs[-1][0], i)
        else:
            runs.append((i, i))
    return runs
