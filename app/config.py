"""ค่าคงที่ของโปรแกรม — แก้ชื่อ/เวอร์ชัน/ชื่อบริษัทได้ที่นี่"""
from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "PDF Governix"
APP_VERSION = "1.0.0"
ORG_NAME = "Governix"
COPYRIGHT = "© 2026 Governix. สงวนลิขสิทธิ์ (All rights reserved)"
SETTINGS_ORG = "Governix"
SETTINGS_APP = "PDFGovernix"
FONT_FAMILY = "Prompt"

MAX_UNDO = 20          # จำนวนขั้นตอนย้อนกลับสูงสุด
MAX_RECENT = 10        # จำนวนไฟล์ล่าสุดที่จำไว้
PRINT_DPI = 300        # ความละเอียดสูงสุดตอนพิมพ์


def resource_path(*parts: str) -> Path:
    """หาไฟล์ทรัพยากร ทั้งตอนรันจาก source และตอนเป็น .exe (PyInstaller)"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)
