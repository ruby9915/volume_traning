"""안드로이드 7 이하용 PNG 앱 아이콘을 만든다 (Pillow 필요 — 이 PC에서는 anaconda3 의 python).

usage: python make_icons.py
안드로이드 8 이상은 res/mipmap-anydpi-v26 의 벡터 아이콘(drawable/ic_launcher_foreground.xml + 배경색)을 쓴다.
여기서 그리는 막대 모양은 그 벡터와 같은 좌표다. 아이콘을 바꾸면 두 곳을 함께 고친다.
"""
import os

from PIL import Image, ImageDraw

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "android", "app", "src", "main", "res")
BRAND = (0x0F, 0xA9, 0x6F, 255)  # res/values/colors.xml 의 brand
BARS = ((33, 57), (49, 47), (65, 35))  # 전경 벡터(108 기준)에서 각 막대의 왼쪽 위. 너비 10, 바닥 73
SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}


def draw(size: int, circle: bool) -> Image.Image:
    s = size * 8  # 크게 그린 뒤 줄여 가장자리를 부드럽게 한다
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if circle:
        d.ellipse([0, 0, s - 1, s - 1], fill=BRAND)
    else:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BRAND)
    k, off = s / 72.0, 18  # 벡터의 가운데 72 영역을 아이콘 전체로 옮긴다
    for x0, y0 in BARS:
        d.rounded_rectangle([(x0 - off) * k, (y0 - off) * k, (x0 + 10 - off) * k, (73 - off) * k],
                            radius=3 * k, fill=(255, 255, 255, 255))
    return im.resize((size, size), Image.LANCZOS)


for density, px in SIZES.items():
    folder = os.path.join(RES, f"mipmap-{density}")
    draw(px, circle=False).save(os.path.join(folder, "ic_launcher.png"))
    draw(px, circle=True).save(os.path.join(folder, "ic_launcher_round.png"))
print("icons written:", ", ".join(f"{d} {p}px" for d, p in SIZES.items()))
