import os, sys
os.environ["QT_QPA_PLATFORM"]="offscreen"
sys.path.insert(0, "/home/claude/pdfstudio")
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.theme import apply_app_font, stylesheet
from tests.make_samples import make_sample
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
app = QApplication([]); apply_app_font(app); app.setStyleSheet(stylesheet())
from app.dialogs import MergeDialog, TextDialog, SplitDialog
from app.signatures import SignatureDialog
from app.textrender import TextStyle
a = make_sample(str(out/"a.pdf"), "Document A", 3); b = make_sample(str(out/"b.pdf"), "Document B", 2)
d = MergeDialog(None, [a, b, a], str(out)); d.show(); QTest.qWait(200); d.grab().save(str(out/"d_merge.png"))
t = TextDialog(None, "ใส่ข้อความ", "ทดสอบข้อความ ที่นี่", TextStyle(size=20, color="#1C7ED6")); t.show(); QTest.qWait(200); t.grab().save(str(out/"d_text.png"))
s = SplitDialog(None, 5, "1-3"); s.show(); QTest.qWait(100); s.grab().save(str(out/"d_split.png"))
g = SignatureDialog(None); g.show(); QTest.qWait(100); g.grab().save(str(out/"d_sig.png"))
print("ok")
