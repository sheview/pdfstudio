"""ตรรกะเครื่องคิดเลข / งวดเงินสัญญา (ไม่ผูกกับหน้าต่าง เพื่อทดสอบง่าย)

ใช้ Decimal ทั้งหมด (ไม่ใช้ float) เพื่อไม่ให้เศษสตางค์เพี้ยน
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
CENT = Decimal("0.01")


def to_ascii_digits(s: str) -> str:
    return s.translate(_THAI_DIGITS)


def q2(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_money(v: Decimal | float | int) -> str:
    return f"{q2(Decimal(v)):,.2f}"


def fmt_num(v: Decimal) -> str:
    """แสดงผลเครื่องคิดเลข: มีคอมมาคั่นหลักพัน ตัดศูนย์ท้ายทศนิยมที่ไม่จำเป็น (สูงสุด 8 ตำแหน่ง)"""
    v = v.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP).normalize()
    s = f"{v:f}"
    if "." in s:
        a, b = s.split(".")
        return f"{int(a):,}.{b}"
    return f"{int(s):,}"


def parse_amount(s: str) -> Decimal:
    s = to_ascii_digits(s).replace(",", "").replace(" ", "").replace("บาท", "")
    if not s:
        return Decimal(0)
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise ValueError(f"อ่านตัวเลขไม่ได้: {s}") from e


# ───────────────────────── ตัวคิดเลขนิพจน์ (ปลอดภัย ไม่ใช้ eval) ─────────────────────────
class CalcError(ValueError):
    pass


def evaluate(expr: str) -> Decimal:
    """คำนวณนิพจน์ เช่น  12,500,000 * 30%   (1,000+250)/4   100 + 7%   — รองรับ + - * / ( ) ^ % และเลขไทย

    "%" หลังตัวเลข = หารร้อย;  "A + B%" และ "A - B%" ถือเป็นบวก/ลบ B เปอร์เซ็นต์ของ A (แบบเครื่องคิดเลขทั่วไป)
    """
    s = to_ascii_digits(expr).replace(",", "").replace("×", "*").replace("÷", "/").replace("−", "-").replace("x", "*").replace("X", "*")
    s = s.replace("^", "**").strip()
    if not s:
        raise CalcError("ยังไม่ได้ป้อนตัวเลข")
    # ตัวเลขตามด้วย % → (ตัวเลข/100) ; "A +/- B%" → A*(1 +/- B/100)
    s = re.sub(r"(\d+(?:\.\d+)?|\))\s*([+\-])\s*(\d+(?:\.\d+)?)\s*%", lambda m: f"{m.group(1)}*(1{m.group(2)}{m.group(3)}/100)", s)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", s)
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError as e:
        raise CalcError("รูปแบบนิพจน์ไม่ถูกต้อง") from e
    return _ev(tree.body)


def _ev(n: ast.AST) -> Decimal:
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return Decimal(str(n.value))
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
        v = _ev(n.operand)
        return -v if isinstance(n.op, ast.USub) else v
    if isinstance(n, ast.BinOp):
        a, b = _ev(n.left), _ev(n.right)
        if isinstance(n.op, ast.Add):
            return a + b
        if isinstance(n.op, ast.Sub):
            return a - b
        if isinstance(n.op, ast.Mult):
            return a * b
        if isinstance(n.op, ast.Div):
            if b == 0:
                raise CalcError("หารด้วยศูนย์ไม่ได้")
            return a / b
        if isinstance(n.op, ast.Pow):
            if b != b.to_integral_value() or abs(b) > 20:
                raise CalcError("ยกกำลังได้เฉพาะจำนวนเต็มไม่เกิน 20")
            return a ** int(b)
    raise CalcError("ใช้ได้เฉพาะ + − × ÷ ( ) ^ %")


# ───────────────────────── ดึงตัวเลขจากข้อความสัญญา ─────────────────────────
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
_MONEY_RE = re.compile(rf"({_NUM})\s*(?:บาท|baht|Baht|THB)", re.I)
_PCT_RE = re.compile(rf"(?:ร้อยละ|เปอร์เซ็นต์|เปอร์เซนต์)\s*({_NUM})|({_NUM})\s*(?:%|เปอร์เซ็นต์|เปอร์เซนต์)")
_INST_RE = re.compile(r"งวด(?:ที่)?\s*(\d{1,2})")


@dataclass
class Found:
    amounts: list[tuple[Decimal, str]]            # (จำนวนเงิน, ข้อความรอบๆ)
    installments: list[tuple[str, Decimal]]       # (ชื่องวด, เปอร์เซ็นต์)


def extract_contract_numbers(text: str) -> Found:
    """หาจำนวนเงิน (…บาท) และงวดที่ระบุเปอร์เซ็นต์ (งวดที่ N … ร้อยละ P) จากข้อความ — ผลเป็นข้อเสนอแนะ ต้องให้คนตรวจ"""
    t = to_ascii_digits(text).replace("​", "")
    t = re.sub(r"[ \t]+", " ", t)
    amounts: list[tuple[Decimal, str]] = []
    seen: set[Decimal] = set()
    for m in _MONEY_RE.finditer(t):
        try:
            v = parse_amount(m.group(1))
        except ValueError:
            continue
        if v <= 0 or v in seen:
            continue
        seen.add(v)
        a, b = max(0, m.start() - 30), min(len(t), m.end() + 10)
        amounts.append((v, re.sub(r"\s+", " ", t[a:b]).strip()))
    amounts.sort(key=lambda x: x[0], reverse=True)

    insts: list[tuple[str, Decimal]] = []
    flat = re.sub(r"\s+", " ", t)
    # แบ่งเป็นช่วงต่อ "งวดที่ N" แล้วหา % ตัวแรกในแต่ละช่วง
    marks = list(_INST_RE.finditer(flat))
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else min(len(flat), m.end() + 220)
        seg = flat[m.end():min(end, m.end() + 220)]
        p = _PCT_RE.search(seg)
        if p:
            val = parse_amount(p.group(1) or p.group(2))
            if 0 < val <= 100:
                name = f"งวดที่ {int(m.group(1))}"
                if all(n != name for n, _ in insts):
                    insts.append((name, val))
    return Found(amounts, insts)


# ───────────────────────── คำนวณงวดเงิน ─────────────────────────
@dataclass
class InstallmentRow:
    name: str
    pct: Decimal
    base: Decimal        # ก่อน VAT
    vat: Decimal
    gross: Decimal       # รวม VAT
    wht: Decimal         # หัก ณ ที่จ่าย
    net: Decimal         # ยอดรับสุทธิ


def compute_installments(contract: Decimal, rows: list[tuple[str, Decimal]], vat_rate: Decimal = Decimal(0),
                         vat_included: bool = False, wht_rate: Decimal = Decimal(0)) -> tuple[list[InstallmentRow], dict]:
    """คิดเงินแต่ละงวดตาม % ของมูลค่าสัญญา

    - vat_included=True  : มูลค่าสัญญาเป็นราคารวม VAT แล้ว → แยก VAT ออกมา
    - vat_included=False : มูลค่าสัญญาเป็นราคาก่อน VAT → บวก VAT เพิ่ม
    - หัก ณ ที่จ่ายคิดจากยอดก่อน VAT
    - เศษสตางค์จากการปัดไปรวมที่งวดสุดท้าย เมื่อรวม % ครบ 100 พอดี ผลรวมจะตรงกับมูลค่าสัญญาเป๊ะ
    """
    rate = vat_rate / 100
    total_pct = sum((p for _, p in rows), Decimal(0))
    if vat_included:
        total_gross = q2(contract)
        total_base = q2(contract / (1 + rate)) if rate else q2(contract)
    else:
        total_base = q2(contract)
        total_gross = q2(contract * (1 + rate))
    out: list[InstallmentRow] = []
    acc_base = acc_gross = Decimal(0)
    for i, (name, pct) in enumerate(rows):
        last = i == len(rows) - 1 and total_pct == 100
        if last:
            base, gross = total_base - acc_base, total_gross - acc_gross
        else:
            base, gross = q2(total_base * pct / 100), q2(total_gross * pct / 100)
        acc_base += base
        acc_gross += gross
        vat = gross - base
        wht = q2(base * wht_rate / 100)
        out.append(InstallmentRow(name, pct, base, vat, gross, wht, gross - wht))
    sums = {
        "pct": total_pct,
        "base": sum((r.base for r in out), Decimal(0)),
        "vat": sum((r.vat for r in out), Decimal(0)),
        "gross": sum((r.gross for r in out), Decimal(0)),
        "wht": sum((r.wht for r in out), Decimal(0)),
        "net": sum((r.net for r in out), Decimal(0)),
        "remaining_pct": Decimal(100) - total_pct,
    }
    return out, sums


PRESETS = {
    "100% (งวดเดียว)": [Decimal(100)],
    "50 / 50": [Decimal(50), Decimal(50)],
    "30 / 40 / 30": [Decimal(30), Decimal(40), Decimal(30)],
    "40 / 30 / 30": [Decimal(40), Decimal(30), Decimal(30)],
    "30 / 30 / 40": [Decimal(30), Decimal(30), Decimal(40)],
    "25 × 4 งวด": [Decimal(25)] * 4,
    "20 × 5 งวด": [Decimal(20)] * 5,
}
