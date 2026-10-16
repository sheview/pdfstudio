"""สร้างโปรแกรมติดตั้ง Governix PDF ในคำสั่งเดียว:  python build_release.py

ขั้นตอน: สร้างไอคอน -> สร้าง .exe ด้วย PyInstaller -> สร้าง Setup.exe ด้วย Inno Setup
(ใช้ทั้งบนเครื่องตัวเองและใน GitHub Actions — ชื่อโปรแกรม/เวอร์ชันอ่านจาก app/config.py)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# เครื่อง Windows (เช่น GitHub Actions) ใช้ cp1252 เป็นค่าเริ่มต้น พิมพ์ภาษาไทยแล้วจะ error → บังคับเป็น UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
os.environ.setdefault("PYTHONUTF8", "1")

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app.config import APP_NAME, APP_VERSION, ORG_NAME  # noqa: E402

SLUG = APP_NAME.replace(" ", "")


def run(cmd: list[str]) -> None:
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def find_iscc() -> str | None:
    found = shutil.which("ISCC")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if not base:
            continue
        for sub in ("Inno Setup 6", "Programs/Inno Setup 6"):
            cand = Path(base) / sub / "ISCC.exe"
            if cand.exists():
                return str(cand)
    return None


def main() -> int:
    run([sys.executable, "make_icon.py"])
    sep = os.pathsep
    run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", APP_NAME, "--icon", str(Path("assets") / "icon.ico"),
        "--add-data", f"assets{sep}assets",
        "--collect-all", "qtawesome", "--collect-all", "pymupdf",
        "--collect-all", "pdf2docx", "--collect-data", "docx", "--hidden-import", "docx", "--hidden-import", "cv2", "--hidden-import", "fitz",
        "--exclude-module", "tkinter", "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtQml", "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtMultimedia",
        "main.py",
    ])
    print(f"\nสร้าง dist/{APP_NAME}/{APP_NAME}.exe แล้ว")

    if "--no-installer" in sys.argv:
        return 0
    iscc = find_iscc()
    if not iscc:
        print("ไม่พบ Inno Setup — ติดตั้งจาก https://jrsoftware.org/isinfo.php แล้วรันใหม่ (หรือใช้โฟลเดอร์ dist ได้เลย)")
        return 2
    run([iscc, f"/DAppName={APP_NAME}", f"/DAppVersion={APP_VERSION}", f"/DAppPublisher={ORG_NAME}",
         f"/DAppSlug={SLUG}", "installer.iss"])
    print(f"\nเสร็จแล้ว: installer/{SLUG}_Setup.exe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
