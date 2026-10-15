"""สร้างไอคอนโปรแกรม assets/icon.png และ assets/icon.ico  (python make_icon.py)"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)
S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, S - 16, S - 16), radius=110, fill=(59, 91, 219, 255))
d.polygon([(S - 150, 16), (S - 16, 150), (S - 150, 150)], fill=(40, 66, 180, 255))
font = None
for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
    try:
        font = ImageFont.truetype(f, 190); break
    except OSError:
        pass
font = font or ImageFont.load_default()
d.text((S // 2, S // 2 + 40), "PDF", font=font, fill="white", anchor="mm")
img.save(OUT / "icon.png")
img.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon ok")
