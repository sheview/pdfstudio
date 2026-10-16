"""เครื่องคิดเลข + ตารางคิดงวดเงินตามสัญญา (หน้าต่างลอย เปิดค้างไว้ดูสัญญาไปด้วยได้)"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QClipboard, QColor, QFont, QGuiApplication, QImage, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import calc
from .calc import CalcError, fmt_money, fmt_num
from .dialogs import _title
from .theme import ACCENT, MUTED


def _tool_window(dlg: QDialog) -> None:
    dlg.setWindowFlag(Qt.WindowType.Tool, True)       # ลอยเหนือหน้าต่างหลักและไม่บังการใช้งานโปรแกรม
    dlg.setModal(False)


# ───────────────────────── เครื่องคิดเลข ─────────────────────────
class CalculatorDialog(QDialog):
    insertText = Signal(str)        # ขอวางผลลัพธ์ลงหน้าเอกสาร

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("เครื่องคิดเลข")
        _tool_window(self)
        self.setMinimumWidth(360)
        self.last: Decimal | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        self.expr = QLineEdit()
        self.expr.setPlaceholderText("พิมพ์ได้เลย เช่น 12,500,000 × 30%")
        self.expr.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.expr.setMinimumHeight(40)
        f = self.expr.font(); f.setPointSizeF(14); self.expr.setFont(f)
        self.expr.returnPressed.connect(self.equals)
        self.expr.textChanged.connect(self._live)
        lay.addWidget(self.expr)
        self.result = QLabel("0")
        self.result.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rf = self.result.font(); rf.setPointSizeF(24); rf.setBold(True); self.result.setFont(rf)
        self.result.setMinimumHeight(48)
        self.result.setStyleSheet(f"color:{ACCENT};")
        lay.addWidget(self.result)
        self.err = QLabel("")
        self.err.setStyleSheet("color:#D6336C;")
        lay.addWidget(self.err)

        grid = QGridLayout()
        grid.setSpacing(6)
        keys = [
            ["C", "⌫", "%", "÷"],
            ["7", "8", "9", "×"],
            ["4", "5", "6", "−"],
            ["1", "2", "3", "+"],
            ["(", "0", ".", ")"],
        ]
        for r, row in enumerate(keys):
            for c, k in enumerate(row):
                b = QPushButton(k)
                b.setMinimumHeight(40)
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                if k in "÷×−+%":
                    b.setStyleSheet(f"color:{ACCENT};font-weight:700;")
                b.clicked.connect(lambda _=False, key=k: self.press(key))
                grid.addWidget(b, r, c)
        eq = QPushButton("=")
        eq.setObjectName("Primary")
        eq.setMinimumHeight(40)
        eq.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        eq.clicked.connect(self.equals)
        grid.addWidget(eq, 5, 0, 1, 2)
        for c, (txt, fn) in enumerate((("+VAT 7%", lambda: self.vat(True)), ("−VAT 7%", lambda: self.vat(False)))):
            b = QPushButton(txt)
            b.setMinimumHeight(40)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip("บวก VAT 7% เข้ากับผลลัพธ์" if c == 0 else "แยก VAT 7% ออกจากราคารวม (หารด้วย 1.07)")
            b.clicked.connect(lambda _=False, f=fn: f())
            grid.addWidget(b, 5, 2 + c)
        lay.addLayout(grid)

        row = QHBoxLayout()
        cp = QPushButton("คัดลอกผล")
        cp.clicked.connect(self.copy_result)
        ins = QPushButton("วางผลลงหน้าเอกสาร")
        ins.clicked.connect(self.insert_result)
        row.addWidget(cp)
        row.addWidget(ins)
        lay.addLayout(row)
        hl = QLabel("ประวัติ (ดับเบิลคลิกเพื่อนำกลับมาคิดต่อ)")
        hl.setStyleSheet(f"color:{MUTED};")
        lay.addWidget(hl)
        self.history = QListWidget()
        self.history.setMaximumHeight(120)
        self.history.itemDoubleClicked.connect(self._reuse)
        lay.addWidget(self.history)

    # ── ปุ่ม/คีย์ ──
    def press(self, key: str) -> None:
        if key == "C":
            self.expr.clear()
            self.result.setText("0")
            self.err.clear()
        elif key == "⌫":
            self.expr.backspace()
        else:
            self.expr.insert(key)
        self.expr.setFocus()

    def _live(self) -> None:
        t = self.expr.text()
        if not t.strip():
            self.err.clear()
            return
        try:
            v = calc.evaluate(t)
            self.result.setText(fmt_num(v))
            self.err.clear()
        except CalcError:
            self.err.clear()        # ยังพิมพ์ไม่จบ ไม่ต้องฟ้องข้อผิดพลาดระหว่างพิมพ์
        except Exception:
            self.err.clear()

    def equals(self) -> None:
        t = self.expr.text().strip()
        if not t:
            return
        try:
            v = calc.evaluate(t)
        except CalcError as e:
            self.err.setText(str(e))
            return
        self.err.clear()
        self.last = v
        self.result.setText(fmt_num(v))
        self.history.insertItem(0, f"{t}  =  {fmt_num(v)}")
        self.expr.setText(fmt_num(v).replace(",", ""))
        self.expr.selectAll()

    def vat(self, add: bool) -> None:
        try:
            v = calc.evaluate(self.expr.text()) if self.expr.text().strip() else Decimal(self.result.text().replace(",", ""))
        except Exception:
            return
        out = v * Decimal("1.07") if add else v / Decimal("1.07")
        self.history.insertItem(0, f"{fmt_num(v)} {'+' if add else '−'} VAT 7%  =  {fmt_num(calc.q2(out))}")
        self.last = calc.q2(out)
        self.result.setText(fmt_num(self.last))
        self.expr.setText(str(self.last))

    def _value(self) -> Decimal | None:
        try:
            return calc.evaluate(self.expr.text()) if self.expr.text().strip() else self.last
        except CalcError:
            return self.last

    def copy_result(self) -> None:
        v = self._value()
        if v is not None:
            QGuiApplication.clipboard().setText(fmt_num(v).replace(",", ""))

    def insert_result(self) -> None:
        v = self._value()
        if v is not None:
            self.insertText.emit(fmt_num(v))

    def _reuse(self, item) -> None:
        self.expr.setText(item.text().split("=")[-1].strip().replace(",", ""))
        self.expr.setFocus()


# ───────────────────────── คิดงวดเงิน ─────────────────────────
COLS = ["งวด", "% ของสัญญา", "ก่อน VAT", "VAT", "รวม VAT", "หัก ณ ที่จ่าย", "ยอดรับสุทธิ"]


def render_table_png(title: str, header: list[str], rows: list[list[str]], foot: list[str] | None, scale: float = 2.0) -> bytes:
    """วาดตารางเป็นรูปภาพ (พื้นขาว) เพื่อวางลงหน้า PDF — ใช้ฟอนต์ของโปรแกรม (Prompt)"""
    from PySide6.QtCore import QBuffer, QIODevice
    font = QFont(QGuiApplication.font().family())
    font.setPixelSize(15)
    bold = QFont(font); bold.setBold(True)
    probe = QImage(10, 10, QImage.Format.Format_ARGB32)
    p = QPainter(probe)
    p.setFont(font)
    fm = p.fontMetrics()
    p.setFont(bold)
    fmb = p.fontMetrics()
    p.end()
    pad, rh = 10, 30
    allrows = [header] + rows + ([foot] if foot else [])
    widths = [max(max(fmb.horizontalAdvance(r[i]) if (k == 0 or (foot and r is foot)) else fm.horizontalAdvance(r[i])
                      for k, r in enumerate(allrows)), 40) + pad * 2 for i in range(len(header))]
    W = sum(widths) + 2
    title_h = 36 if title else 0
    H = title_h + rh * len(allrows) + 2
    img = QImage(int(W * scale), int(H * scale), QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.scale(scale, scale)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    y = 1.0
    if title:
        p.setFont(bold)
        p.setPen(QColor("#2A2547"))
        p.drawText(QRectF(pad, y, W - pad * 2, title_h), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), title)
        y += title_h
    for k, r in enumerate(allrows):
        is_head, is_foot = k == 0, bool(foot) and k == len(allrows) - 1
        if is_head:
            p.fillRect(QRectF(1, y, W - 2, rh), QColor("#6D4AE0"))
        elif is_foot:
            p.fillRect(QRectF(1, y, W - 2, rh), QColor("#ECE8FB"))
        elif k % 2 == 0:
            p.fillRect(QRectF(1, y, W - 2, rh), QColor("#F8F7FD"))
        x = 1.0
        for i, cell in enumerate(r):
            p.setFont(bold if (is_head or is_foot) else font)
            p.setPen(QColor("white") if is_head else QColor("#1F1B3A"))
            al = Qt.AlignmentFlag.AlignLeft if i == 0 else Qt.AlignmentFlag.AlignRight
            p.drawText(QRectF(x + pad, y, widths[i] - pad * 2, rh), int(Qt.AlignmentFlag.AlignVCenter | al), cell)
            x += widths[i]
        y += rh
    p.setPen(QPen(QColor("#CFCAEA"), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(1, title_h + 1, W - 2, rh * len(allrows)))
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


class InstallmentDialog(QDialog):
    insertImage = Signal(bytes)

    def __init__(self, parent=None, page_text: Callable[[], str] | None = None, selected_text: Callable[[], str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("คิดงวดเงินตามสัญญา")
        _tool_window(self)
        self.resize(920, 560)
        self._page_text, self._selected_text = page_text, selected_text
        self._busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        lay.addWidget(_title("คิดงวดเงินตามสัญญา", "ใส่มูลค่าสัญญาและ % ของแต่ละงวด ระบบคำนวณเป็นจำนวนเงินให้ — หรือกด “ดึงจากเอกสาร” ให้ช่วยหาตัวเลข (ต้องตรวจทานเองเสมอ)"))

        top = QHBoxLayout()
        top.addWidget(QLabel("มูลค่าสัญญา (บาท)"))
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("เช่น 1,234,567.89  หรือพิมพ์สูตรได้ เช่น 500000*3")
        self.amount.setMinimumWidth(220)
        top.addWidget(self.amount)
        self.vat = QComboBox()
        self.vat.addItem("ไม่คิด VAT", ("none", 0))
        self.vat.addItem("VAT 7% — มูลค่าสัญญา “ยังไม่รวม” VAT", ("excl", 7))
        self.vat.addItem("VAT 7% — มูลค่าสัญญา “รวม VAT แล้ว”", ("incl", 7))
        top.addWidget(self.vat)
        top.addWidget(QLabel("หัก ณ ที่จ่าย"))
        self.wht = QComboBox()
        self.wht.setEditable(True)
        for t in ("ไม่หัก", "1%", "2%", "3%", "5%"):
            self.wht.addItem(t)
        self.wht.setMinimumWidth(90)
        top.addWidget(self.wht)
        top.addStretch(1)
        lay.addLayout(top)

        bar = QHBoxLayout()
        self.preset = QComboBox()
        self.preset.addItem("ตั้งสัดส่วนสำเร็จรูป…")
        for k in calc.PRESETS:
            self.preset.addItem(k)
        self.preset.activated.connect(self._apply_preset)
        bar.addWidget(self.preset)
        for txt, fn in (("+ เพิ่มงวด", self.add_row), ("− ลบงวดที่เลือก", self.del_row)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _=False, f=fn: f())
            bar.addWidget(b)
        bar.addStretch(1)
        self.btn_sel = QPushButton("ดึงจากข้อความที่เลือก")
        self.btn_page = QPushButton("ดึงจากหน้านี้")
        self.btn_sel.clicked.connect(lambda: self.extract(True))
        self.btn_page.clicked.connect(lambda: self.extract(False))
        bar.addWidget(self.btn_sel)
        bar.addWidget(self.btn_page)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._recalc)
        lay.addWidget(self.table, 1)

        self.status = QLabel("")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch(1)
        for txt, fn, primary in (("คัดลอก (วางลง Excel ได้)", self.copy_table, False), ("วางตารางลงหน้าเอกสาร", self.insert_table, True)):
            b = QPushButton(txt)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(lambda _=False, f=fn: f())
            row.addWidget(b)
        close = QPushButton("ปิด")
        close.clicked.connect(self.close)
        row.addWidget(close)
        lay.addLayout(row)

        self.amount.textChanged.connect(self._recalc)
        self.vat.currentIndexChanged.connect(self._recalc)
        self.wht.currentTextChanged.connect(self._recalc)
        for _ in range(3):
            self.add_row()
        self._apply_preset_values([Decimal(30), Decimal(40), Decimal(30)])

    # ── ตาราง ──
    def _set_ro(self, r: int, c: int, text: str) -> None:
        it = QTableWidgetItem(text)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r, c, it)

    def add_row(self, name: str | None = None, pct: Decimal | None = None) -> None:
        self._busy = True
        r = self.table.rowCount()
        self.table.insertRow(r)
        n = QTableWidgetItem(name or f"งวดที่ {r + 1}")
        p = QTableWidgetItem("" if pct is None else fmt_num(pct))
        p.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r, 0, n)
        self.table.setItem(r, 1, p)
        for c in range(2, len(COLS)):
            self._set_ro(r, c, "")
        self._busy = False
        self._recalc()

    def del_row(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True) or ([self.table.rowCount() - 1] if self.table.rowCount() else [])
        self._busy = True
        for r in rows:
            self.table.removeRow(r)
        self._busy = False
        self._recalc()

    def _apply_preset(self, idx: int) -> None:
        if idx <= 0:
            return
        self._apply_preset_values(calc.PRESETS[self.preset.itemText(idx)])
        self.preset.setCurrentIndex(0)

    def _apply_preset_values(self, pcts: list[Decimal], names: list[str] | None = None) -> None:
        self._busy = True
        self.table.setRowCount(0)
        self._busy = False
        for i, p in enumerate(pcts):
            self.add_row(names[i] if names else None, p)

    def _read(self) -> tuple[Decimal | None, list[tuple[str, Decimal]], str | None]:
        err = None
        try:
            amount = calc.evaluate(self.amount.text()) if self.amount.text().strip() else None
        except CalcError as e:
            amount, err = None, f"มูลค่าสัญญา: {e}"
        rows: list[tuple[str, Decimal]] = []
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0).text().strip() or f"งวดที่ {r + 1}"
            txt = self.table.item(r, 1).text().strip().replace("%", "")
            try:
                pct = calc.evaluate(txt) if txt else Decimal(0)
            except CalcError:
                pct, err = Decimal(0), f"{name}: % ไม่ถูกต้อง"
            rows.append((name, pct))
        return amount, rows, err

    def _wht_rate(self) -> Decimal:
        t = calc.to_ascii_digits(self.wht.currentText()).replace("%", "").strip()
        try:
            return Decimal(0) if t in ("", "ไม่หัก") else Decimal(t)
        except Exception:
            return Decimal(0)

    def _compute(self):
        amount, rows, err = self._read()
        mode, rate = self.vat.currentData()
        if amount is None:
            return None, rows, err, amount
        res, sums = calc.compute_installments(amount, rows, Decimal(rate), mode == "incl", self._wht_rate())
        return (res, sums), rows, err, amount

    def _recalc(self, *_) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            out, rows, err, amount = self._compute()
            mode, _rate = self.vat.currentData()
            show_vat = mode != "none"
            show_wht = self._wht_rate() > 0
            self.table.setColumnHidden(2, not show_vat)
            self.table.setColumnHidden(3, not show_vat)
            self.table.setColumnHidden(4, not show_vat)
            self.table.setColumnHidden(5, not show_wht)
            self.table.setColumnHidden(6, not (show_vat or show_wht))
            if out is None:
                for r in range(self.table.rowCount()):
                    for c in range(2, len(COLS)):
                        self._set_ro(r, c, "")
                self.status.setText(err or "กรอกมูลค่าสัญญาเพื่อคำนวณ")
                self.status.setStyleSheet(f"color:{MUTED};")
                return
            res, sums = out
            for r, row in enumerate(res):
                vals = [fmt_money(row.base), fmt_money(row.vat), fmt_money(row.gross), fmt_money(row.wht), fmt_money(row.net)]
                for c, v in enumerate(vals, start=2):
                    self._set_ro(r, c, v)
            tp = sums["pct"]
            if tp == 100:
                msg, col = f"รวม 100% ✓   ยอดรวมทุกงวด {fmt_money(sums['gross'] if show_vat else sums['base'])} บาท", "#2B8A3E"
            elif tp < 100:
                msg, col = f"รวม {fmt_num(tp)}% — ยังขาดอีก {fmt_num(100 - tp)}% (ยังไม่ครบสัญญา)", "#E8590C"
            else:
                msg, col = f"รวม {fmt_num(tp)}% — เกินสัญญา {fmt_num(tp - 100)}%", "#D6336C"
            if err:
                msg, col = err, "#D6336C"
            self.status.setText(msg)
            self.status.setStyleSheet(f"color:{col};font-weight:600;")
        finally:
            self._busy = False

    # ── ดึงจากเอกสาร ──
    def extract(self, selected: bool) -> None:
        text = (self._selected_text() if selected else self._page_text()) if (self._selected_text and self._page_text) else ""
        if not text.strip():
            QMessageBox.information(self, "ดึงตัวเลข", "ไม่พบข้อความ — ลองลากคลุมข้อความที่ต้องการในเอกสารก่อน" if selected
                                    else "หน้านี้ไม่มีข้อความให้ดึง (อาจเป็นภาพสแกน) — กรอกตัวเลขเองได้เลย")
            return
        found = calc.extract_contract_numbers(text)
        if not found.amounts and not found.installments:
            QMessageBox.information(self, "ดึงตัวเลข", "ไม่พบจำนวนเงิน (…บาท) หรืองวดที่ระบุ % ในข้อความนี้ — กรอกเองได้เลย")
            return
        done = []
        if found.amounts:
            items = [f"{fmt_money(v)} บาท    ({ctx})" for v, ctx in found.amounts[:12]]
            choice, ok = QInputDialog.getItem(self, "เลือกมูลค่าสัญญา", "พบจำนวนเงินเหล่านี้ในเอกสาร — เลือกอันที่เป็นมูลค่าสัญญา:", items, 0, False)
            if ok:
                self.amount.setText(f"{found.amounts[items.index(choice)][0]:,}")
                done.append("มูลค่าสัญญา")
        if found.installments:
            desc = "\n".join(f"  {n}  =  {fmt_num(p)}%" for n, p in found.installments)
            if QMessageBox.question(self, "พบงวดชำระเงิน", f"พบงวดชำระในเอกสาร:\n{desc}\n\nใช้ตารางนี้แทนที่ตารางปัจจุบันหรือไม่?") == QMessageBox.StandardButton.Yes:
                self._apply_preset_values([p for _, p in found.installments], [n for n, _ in found.installments])
                done.append(f"{len(found.installments)} งวด")
        if done:
            self.status.setText("ดึงมาแล้ว: " + ", ".join(done) + " — โปรดตรวจเทียบกับสัญญาอีกครั้ง")

    # ── ส่งออก ──
    def _table_text(self) -> tuple[list[str], list[list[str]], list[str]] | None:
        out, rows, err, amount = self._compute()
        if out is None:
            QMessageBox.information(self, "คิดงวดเงิน", "กรอกมูลค่าสัญญาก่อน")
            return None
        res, sums = out
        mode, _ = self.vat.currentData()
        show_vat, show_wht = mode != "none", self._wht_rate() > 0
        idx = [0, 1] + ([2, 3, 4] if show_vat else [2]) + ([5] if show_wht else []) + ([6] if (show_vat or show_wht) else [])
        header = [COLS[i] for i in idx]
        if not show_vat:
            header[idx.index(2)] = "จำนวนเงิน"

        def line(name, pct, base, vat, gross, wht, net):
            full = [name, pct, base, vat, gross, wht, net]
            return [full[i] for i in idx]

        body = [line(r.name, f"{fmt_num(r.pct)}%", fmt_money(r.base), fmt_money(r.vat), fmt_money(r.gross), fmt_money(r.wht), fmt_money(r.net)) for r in res]
        foot = line("รวม", f"{fmt_num(sums['pct'])}%", fmt_money(sums["base"]), fmt_money(sums["vat"]), fmt_money(sums["gross"]), fmt_money(sums["wht"]), fmt_money(sums["net"]))
        return header, body, foot

    def copy_table(self) -> None:
        t = self._table_text()
        if t:
            header, body, foot = t
            QGuiApplication.clipboard().setText("\n".join("\t".join(r) for r in [header, *body, foot]))
            self.status.setText("คัดลอกตารางแล้ว — วางลง Excel ได้เลย")

    def insert_table(self) -> None:
        t = self._table_text()
        if t:
            header, body, foot = t
            amount = self.amount.text().strip()
            title = f"ตารางงวดการชำระเงิน — มูลค่าสัญญา {fmt_money(calc.evaluate(amount))} บาท"
            self.insertImage.emit(render_table_png(title, header, body, foot))
