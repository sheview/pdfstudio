"""ธีมสี + สไตล์ชีต (QSS) ให้หน้าตาทันสมัย"""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

BG = "#F3F5F9"
SURFACE = "#FFFFFF"
BORDER = "#E1E5ED"
BORDER_STRONG = "#CDD3DF"
TEXT = "#1F2533"
MUTED = "#697386"
ACCENT = "#3B5BDB"
ACCENT_HOVER = "#2F4AC0"
ACCENT_SOFT = "#E8EDFF"
ACCENT_SOFT_2 = "#D6DEFF"
VIEW_BG = "#DCE1EA"
DANGER = "#E03131"
ICON = "#3A4257"
ICON_DISABLED = "#B9C0CE"

UI_FONT_FAMILIES = ["Segoe UI", "Leelawadee UI", "Tahoma", "Sarabun", "Noto Sans Thai", "Loma"]


def apply_app_font(app) -> None:
    available = set(QFontDatabase.families())
    fam = [f for f in UI_FONT_FAMILIES if f in available] or [app.font().family()]
    font = QFont(fam[0])
    font.setFamilies(fam)
    font.setPointSizeF(10.5)
    app.setFont(font)


def make_check_png() -> str:
    """สร้างไฟล์เครื่องหมายถูกสีขาวสำหรับ checkbox (QSS ต้องใช้ไฟล์ภาพ)"""
    from pathlib import Path

    from PySide6.QtCore import QStandardPaths

    import qtawesome as qta

    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation) or str(Path.home())
    d = Path(base)
    d.mkdir(parents=True, exist_ok=True)
    f = d / "check_white.png"
    qta.icon("mdi6.check-bold", color="white").pixmap(16, 16).save(str(f))
    return f.as_posix()


def stylesheet() -> str:
    check = make_check_png()
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: #1F2533; color: white; border: 0; padding: 5px 8px; border-radius: 6px; }}

/* ───── ส่วนหัว / ริบบิ้น ───── */
#Header {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
#Logo {{ font-size: 15pt; font-weight: 700; color: {ACCENT}; padding-right: 8px; }}
#LogoSub {{ color: {MUTED}; font-size: 9pt; }}
QTabBar#RibbonTabs {{ background: transparent; }}
QTabBar#RibbonTabs::tab {{
    background: transparent; color: {MUTED}; padding: 9px 20px 8px 20px; margin-right: 2px;
    border: 0; border-bottom: 3px solid transparent; font-weight: 600;
}}
QTabBar#RibbonTabs::tab:hover {{ color: {TEXT}; background: {BG}; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
QTabBar#RibbonTabs::tab:selected {{ color: {ACCENT}; border-bottom: 3px solid {ACCENT}; }}
#RibbonBody {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
#RibbonGroup {{ background: transparent; border: 0; border-right: 1px solid {BORDER}; }}
#RibbonGroupLabel {{ color: {MUTED}; font-size: 8.5pt; padding-bottom: 2px; }}
QToolButton#RibbonBtn {{
    background: transparent; border: 1px solid transparent; border-radius: 9px;
    padding: 6px 4px 3px 4px; min-width: 62px; font-size: 9.5pt;
}}
QToolButton#RibbonBtn:hover {{ background: {BG}; border-color: {BORDER}; }}
QToolButton#RibbonBtn:pressed {{ background: {ACCENT_SOFT}; }}
QToolButton#RibbonBtn:checked {{ background: {ACCENT_SOFT}; border: 1px solid {ACCENT_SOFT_2}; color: {ACCENT}; font-weight: 600; }}
QToolButton#RibbonBtn:disabled {{ color: {ICON_DISABLED}; }}
QToolButton#RibbonPrimary {{
    background: {ACCENT}; color: white; border: 1px solid {ACCENT}; border-radius: 9px;
    padding: 6px 4px 3px 4px; min-width: 62px; font-size: 9.5pt; font-weight: 600;
}}
QToolButton#RibbonPrimary:hover {{ background: {ACCENT_HOVER}; }}
QToolButton#RibbonPrimary:disabled {{ background: {ACCENT_SOFT_2}; border-color: {ACCENT_SOFT_2}; }}

/* ───── แถบตัวเลือกของเครื่องมือ ───── */
#OptionsBar {{ background: {BG}; border-bottom: 1px solid {BORDER}; }}
#OptionsLabel {{ color: {MUTED}; font-size: 9pt; }}
QToolButton#Swatch {{ border: 2px solid white; border-radius: 12px; min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; }}
QToolButton#Swatch:hover {{ border-color: {BORDER_STRONG}; }}
QToolButton#Swatch:checked {{ border: 2px solid {ACCENT}; }}

/* ───── แท็บเอกสาร ───── */
QTabWidget#DocTabs::pane {{ border: 0; background: {BG}; }}
QTabWidget#DocTabs > QTabBar {{ background: {BG}; }}
QTabWidget#DocTabs > QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 14px 8px 14px; margin: 6px 2px 0 2px;
    border: 1px solid transparent; border-top-left-radius: 9px; border-top-right-radius: 9px; min-width: 90px; max-width: 240px;
}}
QTabWidget#DocTabs > QTabBar::tab:hover {{ background: #E8ECF4; color: {TEXT}; }}
QTabWidget#DocTabs > QTabBar::tab:selected {{ background: {SURFACE}; color: {TEXT}; border-color: {BORDER}; border-bottom-color: {SURFACE}; font-weight: 600; }}
QTabBar::close-button {{ subcontrol-position: right; margin: 2px; border-radius: 4px; }}
QTabBar::close-button:hover {{ background: #E3E7F0; }}

/* ───── แผงภาพย่อ ───── */
#ThumbPanel {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#PanelTitle {{ color: {MUTED}; font-weight: 600; font-size: 9pt; padding: 10px 12px 4px 14px; }}
QListWidget#Thumbs {{ background: {SURFACE}; border: 0; padding: 4px; }}
QListWidget#Thumbs::item {{ border-radius: 10px; padding: 8px 4px 4px 4px; margin: 2px 6px; color: {MUTED}; }}
QListWidget#Thumbs::item:hover {{ background: {BG}; }}
QListWidget#Thumbs::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}

/* ───── ตัวแสดงผล ───── */
QScrollArea#Viewer {{ background: {VIEW_BG}; border: 0; }}
QWidget#Canvas {{ background: {VIEW_BG}; }}
#SearchBar {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}

/* ───── ปุ่มและช่องกรอก ───── */
QPushButton {{
    background: {SURFACE}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 7px 16px; min-height: 18px;
}}
QPushButton:hover {{ background: {BG}; border-color: #B8C0D0; }}
QPushButton:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton:disabled {{ color: {ICON_DISABLED}; background: {BG}; border-color: {BORDER}; }}
QPushButton#Primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: white; font-weight: 600; padding: 8px 22px; }}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Primary:disabled {{ background: {ACCENT_SOFT_2}; border-color: {ACCENT_SOFT_2}; color: white; }}
QPushButton#Danger {{ color: {DANGER}; }}
QPushButton#Link {{ border: 0; background: transparent; color: {ACCENT}; padding: 2px 6px; text-align: left; }}
QPushButton#Link:hover {{ text-decoration: underline; background: transparent; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 4px; }}
QToolButton:hover {{ background: {BG}; border-color: {BORDER}; }}
QToolButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT_SOFT_2}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox, QPlainTextEdit, QTextEdit {{
    background: {SURFACE}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 5px 8px;
    selection-background-color: {ACCENT_SOFT_2}; selection-color: {TEXT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; padding: 4px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {BORDER_STRONG}; background: {SURFACE}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url({check}); }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 10px; margin-top: 14px; padding: 12px; background: {SURFACE}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {MUTED}; }}

QTreeWidget, QListWidget, QTableWidget {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; alternate-background-color: #F8F9FC;
}}
QTreeWidget::item {{ padding: 7px 4px; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QHeaderView::section {{ background: {BG}; border: 0; border-bottom: 1px solid {BORDER}; padding: 7px 8px; color: {MUTED}; font-weight: 600; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #B4BCCB; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: #8E98AC; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #B4BCCB; border-radius: 4px; min-width: 36px; }}
QScrollBar::handle:horizontal:hover {{ background: #8E98AC; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: 0; width: 0; height: 0; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER_STRONG}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; border: 2px solid {ACCENT}; width: 12px; height: 12px; margin: -7px 0; border-radius: 8px; }}

QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: 0; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu::item:disabled {{ color: {ICON_DISABLED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QProgressBar {{ border: 0; background: {BORDER}; border-radius: 5px; text-align: center; min-height: 10px; max-height: 10px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QSplitter::handle {{ background: {BORDER}; width: 1px; }}

/* ───── หน้าต้อนรับ ───── */
#Welcome {{ background: {BG}; }}
#WelcomeCard {{ background: {SURFACE}; border: 2px dashed {BORDER_STRONG}; border-radius: 20px; }}
#WelcomeCard[drag="true"] {{ border-color: {ACCENT}; background: {ACCENT_SOFT}; }}
#WelcomeTitle {{ font-size: 22pt; font-weight: 700; }}
#WelcomeSub {{ color: {MUTED}; font-size: 11pt; }}
#BigBtn {{ background: {ACCENT}; color: white; border: 0; border-radius: 12px; padding: 12px 28px; font-size: 11.5pt; font-weight: 600; }}
#BigBtn:hover {{ background: {ACCENT_HOVER}; }}
#BigBtnAlt {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; border-radius: 12px; padding: 12px 28px; font-size: 11.5pt; font-weight: 600; }}
#BigBtnAlt:hover {{ background: {BG}; }}
#RecentTitle {{ font-weight: 600; color: {MUTED}; }}
"""
