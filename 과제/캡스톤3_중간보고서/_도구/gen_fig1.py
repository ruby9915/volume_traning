# -*- coding: utf-8 -*-
"""md의 업무 영역 분할도(코드 블록의 트리)를 읽어 조직도 모양의 PNG로 그린다.
사용: python -I -X utf8 gen_fig1.py <md> <결과 png>"""
import sys, io, re
from PIL import Image, ImageDraw, ImageFont

md = io.open(sys.argv[1], encoding='utf-8').read().split('\n')
out = sys.argv[2]

# ---- 트리 읽기 ----
start = next(i for i, s in enumerate(md) if s.startswith('### (2) 업무 영역 분할도'))
a = next(i for i in range(start, len(md)) if md[i].startswith('```'))
b = next(i for i in range(a + 1, len(md)) if md[i].startswith('```'))
lines = [s for s in md[a + 1:b] if s.strip()]
root = lines[0].strip()
tree = []                      # [(업무, [세부...])]
for s in lines[1:]:
    m = re.search(r'[├└]─ ?(.+)$', s)
    assert m, s
    depth = (s.index(m.group(0))) // 4 + 1
    name = m.group(1).strip()
    if depth == 1:
        tree.append((name, []))
    else:
        tree[-1][1].append(name)
assert len(tree) == 6, tree

# ---- 배치 (2배 해상도) ----
F = r'C:\Windows\Fonts' + '\\'
f_root = ImageFont.truetype(F + 'malgunbd.ttf', 34)
f_l1 = ImageFont.truetype(F + 'malgunbd.ttf', 30)
f_l2 = ImageFont.truetype(F + 'malgun.ttf', 28)

MARGIN = 40
COL_W, COL_GAP = 324, 30
L1_H, L2_H, L2_GAP = 76, 62, 20
ROOT_W, ROOT_H = 640, 84
V1, V2 = 46, 46                 # 루트-가로선, 가로선-1단계 간격
INDENT = 44                     # 2단계 상자의 들여쓰기
n = len(tree)
W = MARGIN * 2 + n * COL_W + (n - 1) * COL_GAP
max_child = max(len(c) for _, c in tree)
y_root = MARGIN
y_bar = y_root + ROOT_H + V1
y_l1 = y_bar + V2
y_l2 = y_l1 + L1_H + 30
H = y_l2 + max_child * (L2_H + L2_GAP) - L2_GAP + MARGIN

im = Image.new('RGB', (W, H), 'white')
d = ImageDraw.Draw(im)
LINE = (90, 90, 90)
LW = 3


def box(x, y, w, h, text, font, fill, outline=(70, 70, 70), width=3):
    d.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=fill, outline=outline, width=width)
    l, t, r, b_ = d.textbbox((0, 0), text, font=font)
    assert r - l <= w - 16, ('글자가 상자보다 김', text, r - l, w)
    d.text((x + (w - (r - l)) / 2 - l, y + (h - (b_ - t)) / 2 - t), text, font=font, fill=(20, 20, 20))


cx_root = W // 2
box(cx_root - ROOT_W // 2, y_root, ROOT_W, ROOT_H, root, f_root, (222, 235, 247), outline=(46, 84, 138), width=4)
d.line([cx_root, y_root + ROOT_H, cx_root, y_bar], fill=LINE, width=LW)
centers = [MARGIN + i * (COL_W + COL_GAP) + COL_W // 2 for i in range(n)]
d.line([centers[0], y_bar, centers[-1], y_bar], fill=LINE, width=LW)

for i, (name, children) in enumerate(tree):
    x = MARGIN + i * (COL_W + COL_GAP)
    cx = centers[i]
    d.line([cx, y_bar, cx, y_l1], fill=LINE, width=LW)
    box(x, y_l1, COL_W, L1_H, name, f_l1, (238, 238, 238))
    if not children:
        continue
    xs = x + 20                                   # 세로 줄기
    y_last = y_l2 + (len(children) - 1) * (L2_H + L2_GAP) + L2_H // 2
    d.line([xs, y_l1 + L1_H, xs, y_last], fill=LINE, width=LW)
    for k, c in enumerate(children):
        y = y_l2 + k * (L2_H + L2_GAP)
        d.line([xs, y + L2_H // 2, x + INDENT, y + L2_H // 2], fill=LINE, width=LW)
        box(x + INDENT, y, COL_W - INDENT, L2_H, c, f_l2, (255, 255, 255), width=2)

im.save(out, dpi=(200, 200))
print('saved', out, im.size, [(nm, len(c)) for nm, c in tree])
