"""Governix PDF — จุดเริ่มต้นโปรแกรม"""
from __future__ import annotations

import sys


def main() -> int:
    import os

    for name in ("stdout", "stderr"):      # โหมดไม่มีหน้าต่างคอนโซล (.exe) ไลบรารีบางตัวยัง print/log → กันพัง
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.config import APP_NAME, APP_VERSION, SETTINGS_ORG, resource_path
    from app.theme import apply_app_font, stylesheet

    if sys.platform == "win32":  # ให้ไอคอนบนแถบงานเป็นของโปรแกรม ไม่ใช่ของ python
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Governix.GovernixPDF.App")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(SETTINGS_ORG)
    ico = resource_path("assets", "icon.png")
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))
    apply_app_font(app)
    app.setStyleSheet(stylesheet())

    from app.mainwindow import MainWindow

    files = [a for a in sys.argv[1:] if not a.startswith("-")]
    win = MainWindow(files)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
