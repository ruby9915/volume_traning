"""정규화 표에 넣을 함수적 종속 다이어그램(FDD)을 SVG로 그려 HTML로 저장한다.

usage: fdd.py <work_dir>
  <work_dir>/fddN.html, fdd_sizes.txt 를 만든다. 이어서 shots.sh 가 브라우저로 PNG(2배율)를 찍는다.
그림 내용은 content.py 의 NORMALIZATION[*]["fdd"] 에서 읽는다.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content as C  # noqa: E402


def fdd_svg(spec):
    """returns (svg, width, height). 결정자 상자(왼쪽) → 종속 속성 상자(오른쪽). back = 대체키 → 기본키(점선)."""
    keys, deps, back = spec["key"], list(spec["deps"]), spec.get("back")
    if back:  # 대체키를 맨 위로 올려 되돌아가는 화살표가 다른 선과 겹치지 않게 한다
        deps.remove(back)
        deps.insert(0, back)
    bh, gap, kw, dw, mid = 30, 10, 112, 150, 110
    top = 30 if back else 14
    list_h = len(deps) * bh + (len(deps) - 1) * gap
    composite = len(keys) > 1
    key_h = len(keys) * bh + (len(keys) - 1) * 8 + (20 if composite else 0)
    body_h = max(list_h, key_h)
    height = top + body_h + 14
    kx = 16
    key_w = kw + (20 if composite else 0)
    dx = kx + key_w + mid
    width = dx + dw + 16
    ky = top + (body_h - key_h) / 2
    dy0 = top + (body_h - list_h) / 2

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="Malgun Gothic, sans-serif" font-size="14">',
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#222"/></marker></defs>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff"/>',
    ]

    def box(x, y, w, h, label, bold=False):
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff" stroke="#222" stroke-width="1.2"/>')
        weight = ' font-weight="700"' if bold else ""
        out.append(f'<text x="{x + w / 2}" y="{y + h / 2 + 5}" text-anchor="middle"{weight}>{html.escape(label)}</text>')

    if composite:  # 복합키는 바깥 상자로 묶는다
        out.append(f'<rect x="{kx}" y="{ky}" width="{key_w}" height="{key_h}" fill="#f4f4f4" stroke="#222" stroke-width="1.2"/>')
        for i, k in enumerate(keys):
            box(kx + 10, ky + 10 + i * (bh + 8), kw, bh, k, bold=True)
    else:
        box(kx, ky, kw, bh, keys[0], bold=True)
    sx, sy = kx + key_w, ky + key_h / 2
    for i, d in enumerate(deps):
        y = dy0 + i * (bh + gap)
        box(dx, y, dw, bh, d)
        out.append(f'<line x1="{sx}" y1="{sy}" x2="{dx - 2}" y2="{y + bh / 2}" stroke="#222" stroke-width="1.1" marker-end="url(#a)"/>')
    if back:
        bx, kcx = dx + dw / 2, kx + key_w / 2
        out.append(f'<path d="M{bx},{dy0} L{bx},12 L{kcx},12 L{kcx},{ky - 2}" fill="none" stroke="#222" '
                   f'stroke-width="1.1" stroke-dasharray="5 3" marker-end="url(#a)"/>')
    out.append("</svg>")
    return "".join(out), int(width), int(height)


if __name__ == "__main__":
    work = sys.argv[1]
    os.makedirs(work, exist_ok=True)
    sizes = []
    for i, n in enumerate(C.NORMALIZATION, start=1):
        svg, w, h = fdd_svg(n["fdd"])
        sizes.append((w, h))
        page = f'<!doctype html><meta charset="utf-8"><style>html,body{{margin:0;background:#fff}}svg{{display:block}}</style>{svg}'
        open(os.path.join(work, f"fdd{i}.html"), "w", encoding="utf-8").write(page)
    open(os.path.join(work, "fdd_sizes.txt"), "w").write("\n".join(f"{w} {h}" for w, h in sizes))
    print("fdd sizes:", sizes)
