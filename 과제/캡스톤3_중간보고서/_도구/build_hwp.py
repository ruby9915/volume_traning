# -*- coding: utf-8 -*-
"""작성본 md → 제출용 HWP (한글 2022 자동화).

사용법 (캡스톤3_중간보고서 폴더에서):
    python -X utf8 _도구/build_hwp.py 캡스톤3_중간보고서_작성본.md 캡스톤3_중간보고서_작성본.hwp .

하는 일:
  1. md를 build_docx.py와 같은 규칙으로 읽는다(작업 메모와 'PPT 요약 구성안' 이후는 넣지 않는다).
  2. 한글이 읽기 좋은 HTML로 바꾼다(표 너비는 px 절대값, 글꼴·음영·정렬은 속성으로 적는다).
  3. _도구/hwp_build.ps1 이 한글을 띄워 HTML을 열고, 쪽 여백·쪽 나눔·쪽 번호를 넣은 뒤 .hwp 와 .pdf 로 저장한다.
  4. 목차의 쪽 번호는 한 번 만든 PDF에서 제목이 있는 쪽을 찾아 넣고 다시 만든다(두 번 실행).

주의:
  - 한글(Hwp.exe)이나 한워드가 이미 열려 있으면 열린 문서를 건드리지 않으려고 멈춘다. 닫고 다시 실행한다.
  - docx를 한글에서 여는 방식은 이 PC(한컴오피스 2022)에서 한워드로 넘어가 HWP로 저장되지 않는다.
    HTML을 '끼워 넣기'하면 문자 코드 선택 창이 떠서 멈추므로 '열기'만 쓴다.
  - 결과 PDF는 <hwp 이름>_미리보기.pdf 로 같은 폴더에 남는다(모양 확인용, 제출물 아님).
"""
import html as _html
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

md_path, out_hwp, img_dir = sys.argv[1], sys.argv[2], sys.argv[3]
FONT = '맑은 고딕'
BODY_MM = 170.0                                   # A4 210 - 좌우 여백 20 × 2
TOTAL = BODY_MM / 25.4 * 72 - 1.0                 # 본문 너비(pt)
PX = 96.0 / 72.0                                  # 한글의 HTML 변환은 1px = 1/96 in
COURSE = '데이터베이스 설계'
FIG1 = '그림1_업무영역분할도.png'
M = '¤'                                      # 문단 표식 ¤..¤ (hwp_build.ps1 이 문단 모양으로 바꾼다)

# ================= md 읽기 (build_docx.py 와 같은 규칙) =================
raw = io.open(md_path, encoding='utf-8').read().split('\n')
blocks = []
i = 0
title = None
while i < len(raw):
    s = raw[i]
    if s.startswith('## PPT 요약 구성안'):
        break
    if s.startswith('# ') and title is None:
        title = s[2:].strip()
        i += 1
        continue
    if s.startswith('>') or s.strip() == '' or s.strip() == '---':
        i += 1
        continue
    if s.startswith('```'):
        j = i + 1
        while not raw[j].startswith('```'):
            j += 1
        blocks.append(('code', raw[i + 1:j]))
        i = j + 1
        continue
    if s.startswith('#### '):
        blocks.append(('h3', s[5:].strip()))
    elif s.startswith('### '):
        blocks.append(('h2', s[4:].strip()))
    elif s.startswith('## '):
        t = s[3:].strip()
        if t.startswith('별첨'):
            t = '별첨'
        blocks.append(('h1', t))
    elif s.startswith('|'):
        j = i
        rows = []
        while j < len(raw) and raw[j].startswith('|'):
            rows.append([c.strip() for c in re.split(r'(?<!\\)\|', raw[j].strip())[1:-1]])
            j += 1
        assert all(re.fullmatch(r':?-+:?', c) for c in rows[1]), rows[1]
        blocks.append(('table', rows[0], rows[2:]))
        i = j
        continue
    elif re.match(r'^<표 \d+> ', s):
        blocks.append(('tcap', s.strip()))
    elif re.match(r'^\[그림 \d+\] ', s):
        blocks.append(('fcap', s.strip()))
    elif s.startswith('!['):
        m = re.match(r'!\[(.*?)\]\((.*?)\)', s)
        blocks.append(('image', m.group(2)))
    elif s.startswith('- '):
        blocks.append(('bullet', s[2:].strip()))
    else:
        blocks.append(('para', s.strip()))
    i += 1

assert title
team = None
if blocks and blocks[0][0] == 'table' and blocks[0][1][0] == '학번':
    team = blocks.pop(0)


# ================= 표 열 너비 (build_docx.py 와 같은 계산) =================
def clean(t):
    return t.replace('`', '')


def plain(t):
    return re.sub(r'\*\*(.+?)\*\*', r'\1', clean(t))


def disp_w(s):
    w = 0.0
    for ch in s:
        o = ord(ch)
        if ch == ' ':
            w += 0.30
        elif o >= 0x1100 and not (0x2010 <= o <= 0x2027):
            w += 1.0
        elif ch in '·':
            w += 0.5
        else:
            w += 0.56
    return w


NOSHRINK_EM = 11.0


def header_em(h):
    toks = h.split(' ')
    full = disp_w(h)
    if len(toks) < 2 or full <= 4.5:
        return full * 1.08
    best = full
    for k in range(1, len(toks)):
        best = min(best, max(disp_w(' '.join(toks[:k])), disp_w(' '.join(toks[k:]))))
    return best * 1.08


def col_widths(header, rows, fs, total):
    pad = 10.0
    floor = 2.7 * fs
    ncol = len(header)
    nat, mn, eff = [], [], []
    for c in range(ncol):
        cell_w = [max(disp_w(ln) for ln in plain(r[c]).split('<br>')) for r in rows] or [0.0]
        hn = header_em(plain(header[c]))
        body_max = max(cell_w)
        em = max(body_max, hn)
        natural = max(em * fs + pad, floor)
        avg = sum(cell_w) / len(cell_w)
        effective = max(max(0.3 * body_max + 0.7 * avg, hn) * fs + pad, floor)
        toks = [t for r in rows for ln in plain(r[c]).split('<br>') for t in ln.split(' ') if t]
        tok = max([disp_w(t) for t in toks] + [disp_w(t) * 1.08 for t in plain(header[c]).split(' ')] + [1.0]) * fs + pad
        m = natural if em <= NOSHRINK_EM else max(min(tok, natural), floor)
        nat.append(natural)
        mn.append(m)
        eff.append(min(effective, natural))
    if sum(nat) <= total:
        extra = total - sum(nat)
        wsum = sum(nat)
        return [n + extra * n / wsum for n in nat]
    cap = 2.5 * total
    natc = [min(e, cap) for e in eff]
    if sum(mn) >= total:
        return [m * total / sum(mn) for m in mn]
    room = total - sum(mn)
    stretch = [max(n - m, 0.0) for n, m in zip(natc, mn)]
    for k in range(ncol):
        if nat[k] > mn[k] and stretch[k] < 1.0:
            stretch[k] = 1.0
    ssum = sum(stretch) or 1.0
    w = [m + room * s / ssum for m, s in zip(mn, stretch)]
    for _ in range(6):
        over = [(k, w[k] - nat[k]) for k in range(ncol) if w[k] > nat[k] + 0.01]
        if not over:
            break
        spare = sum(o for _, o in over)
        for k, _o in over:
            w[k] = nat[k]
        under = [k for k in range(ncol) if w[k] < nat[k] - 0.01]
        if not under:
            break
        us = sum(nat[k] - w[k] for k in under)
        for k in under:
            w[k] += spare * (nat[k] - w[k]) / us
    return w


# ================= HTML 조각 =================
def esc(t):
    return _html.escape(t, quote=False)


def inline(text):
    """`코드` 표시 제거, **굵게** → <b>, <br> 유지, 나머지는 HTML 이스케이프."""
    out = []
    for line in clean(text).split('<br>'):
        segs = []
        for seg in re.split(r'(\*\*.+?\*\*)', line):
            if not seg:
                continue
            if seg.startswith('**') and seg.endswith('**') and len(seg) > 4:
                segs.append('<b>%s</b>' % esc(seg[2:-2]))
            else:
                segs.append(esc(seg))
        out.append(''.join(segs))
    return '<br>'.join(out)


def run(inner, size, bold=False, color=None):
    s = '<font face="%s"%s><span style="font-family:\'%s\';font-size:%gpt">%s</span></font>' % (
        FONT, (' color="#%s"' % color) if color else '', FONT, size, inner)
    return '<b>%s</b>' % s if bold else s


def par(inner, size=10, align='left', bold=False, color=None, lh=150, mark='', style=''):
    return '<p align="%s" style="font-family:\'%s\';font-size:%gpt;line-height:%d%%;%s">%s</p>\n' % (
        align, FONT, size, lh, style,
        run(''.join(M + k + M for k in mark.split(',') if k) + inner, size, bold, color))


def blank(n=1, size=10):
    return par('&nbsp;', size) * n


def spacer():
    return '<p align="left" style="font-size:4pt;line-height:100%%">%s</p>\n' % run('&nbsp;', 4)


table_policy = []        # 표마다 한 글자: K 한 쪽에 묶음, C 행 사이에서만 나눔, T 묶음+가운데, N 그대로 (hwp_build.ps1 이 읽는다)


def table_html(header, rows, total=None, fs=None, merge_first_blank=False, policy=None):
    total = total or TOTAL
    ncol = len(header)
    if fs is None:
        fs = 9.0 if ncol <= 5 else (8.5 if ncol <= 7 else 8.0)
    widths = col_widths(header, rows, fs, total)
    px = [int(round(w * PX)) for w in widths]
    center = []
    for c in range(ncol):
        body = [plain(r[c]) for r in rows]
        lens = [max(disp_w(ln) for ln in b.split('<br>')) for b in body] or [0.0]
        center.append(all(x <= 13.5 for x in lens) and (ncol > 3 or all('<br>' not in b for b in body)))

    # 세로 병합: span[r][c] = 병합할 행 수(0이면 위 칸에 합쳐져 생략)
    span = [[1] * ncol for _ in rows]

    def vmerge(col, groups):
        for a, b in groups:               # a, b: rows 의 0-기반 번호
            if b > a:
                span[a][col] = b - a + 1
                for r in range(a + 1, b + 1):
                    span[r][col] = 0

    if merge_first_blank:
        groups, start = [], None
        for r, row in enumerate(rows):
            if row[0].strip():
                if start is not None:
                    groups.append((start, r - 1))
                start = r
        if start is not None:
            groups.append((start, len(rows) - 1))
        vmerge(0, groups)
    if '유형' in header and header.index('유형') == 1 and header[-1] == '트랜잭션':
        groups, start = [], 0
        for r in range(1, len(rows) + 1):
            if r == len(rows) or rows[r][1] != rows[start][1]:
                groups.append((start, r - 1))
                start = r
        vmerge(1, groups)

    # 표 정책: K 글자처럼 취급(작은 표: 캡션과 함께 통째로 다음 쪽으로), C 행 사이에서만 나눔,
    #          S 그대로 둠(큰 병합 칸이 있어 행 단위로 묶을 수 없는 표)
    n_chars = sum(len(plain(v)) for r in rows for v in r)
    big_merge = max(max(r) for r in span) > 6 if rows else False
    table_policy.append(policy or ('K' if (len(rows) <= 12 and n_chars <= 900) else ('S' if big_merge else 'C')))

    def cell(text, c, head=False, rowspan=1):
        al = 'center' if (head or center[c]) else 'left'
        attrs = 'width="%d" align="%s" valign="middle"' % (px[c], al)
        if head:
            attrs += ' bgcolor="#E7E6E6"'
        if rowspan > 1:
            attrs += ' rowspan="%d"' % rowspan
        return '<td %s><p align="%s" style="font-size:%gpt;line-height:125%%">%s</p></td>' % (
            attrs, al, fs, run(inline(text), fs, bold=head))

    out = ['<table border="1" cellspacing="0" cellpadding="2" width="%d" align="center" '
           'style="border-collapse:collapse">' % sum(px)]
    out.append('<tr>%s</tr>' % ''.join(cell(h, c, head=True) for c, h in enumerate(header)))
    for r, row in enumerate(rows):
        tds = [cell(v, c, rowspan=span[r][c]) for c, v in enumerate(row) if span[r][c]]
        out.append('<tr>%s</tr>' % ''.join(tds))
    out.append('</table>\n')
    return '\n'.join(out)


def image_html(path):
    w_px, h_px = Image.open(path).size
    w_mm = 168.0
    if h_px / w_px * w_mm > 205:           # 세로로 긴 그림은 쪽 안에 들어가게
        w_mm = 205 * w_px / h_px
    w = int(round(w_mm / 25.4 * 96))
    h = int(round(w * h_px / w_px))
    return ('<p align="center" style="line-height:100%%">%s<img src="%s" width="%d" height="%d"></p>\n'
            % (run(M + 'K' + M, 4), os.path.basename(path), w, h))


# ================= 문서 조립 =================
def build_html(toc_pages=None, breaks=()):
    """breaks: 앞에서 쪽을 나눌 블록 번호(쪽 끝에 캡션·머리행만 남는 표를 다음 쪽으로 넘긴다)."""
    del table_policy[:]
    main_title, _, sub_title = title.partition(' — ')
    o = ['<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"><title>%s</title></head><body>\n' % esc(main_title)]
    # ---- 표지
    o.append(blank(7))
    o.append(par(esc(COURSE), 14, 'center', color='404040'))
    o.append(blank(1, 6))
    o.append(par(esc(main_title), 26, 'center', bold=True, color='1F3864', lh=130))
    o.append(blank(1, 6))
    o.append(par(esc(sub_title), 18, 'center', bold=True, lh=130))
    o.append(blank(9))
    if team:
        o.append(table_html(team[1], team[2], total=110 / 25.4 * 72, fs=11, policy='T'))
    # ---- 목차
    o.append(par('목차', 16, 'left', bold=True, color='1F3864', mark='P', style='margin-bottom:10pt;'))
    o.append(blank(1, 6))
    toc_rows = []
    for b in blocks:
        if b[0] in ('h1', 'h2'):
            toc_rows.append(b)
    wl, wr = int(round((TOTAL - 40) * PX)), int(round(40 * PX))
    table_policy.append('N')
    o.append('<table border="0" cellspacing="0" cellpadding="2" width="%d" align="center">' % (wl + wr))
    for n, b in enumerate(toc_rows):
        big = b[0] == 'h1'
        text = esc(b[1]) if big else '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;' + esc(b[1])
        pg = '' if not toc_pages else str(toc_pages[n] or '')
        size = 11.5 if big else 10.5
        o.append('<tr><td width="%d" align="left"><p align="left" style="font-size:%gpt;line-height:%d%%">%s</p></td>'
                 '<td width="%d" align="right"><p align="right" style="font-size:%gpt;line-height:%d%%">%s</p></td></tr>'
                 % (wl, size, 190 if big else 140, run(text, size, bold=big), wr, size, 190 if big else 140,
                    run(pg or '&nbsp;', size, bold=big)))
    o.append('</table>\n')
    # ---- 본문
    prev = None
    for bi, b in enumerate(blocks):
        k = b[0]
        pb = 'P,' if bi in breaks else ''
        if k == 'h1':
            o.append(par(esc(b[1]), 16, 'left', bold=True, color='1F3864', lh=130, mark='H1'))
        elif k == 'h2':
            er = 'ER 다이어그램' in b[1] and '체크리스트' not in b[1]
            o.append(par(esc(b[1]), 13, 'left', bold=True, lh=130, mark=pb + ('Q' if er else 'H2')))
        elif k == 'h3':
            o.append(par(esc(b[1]), 11, 'left', bold=True, lh=130, mark=pb + 'H3'))
        elif k == 'tcap':
            o.append(par(inline(b[1]), 10, 'left', lh=130, mark=pb + 'C'))
        elif k == 'fcap':
            o.append(par(inline(b[1]), 10, 'center', lh=130))
            o.append(spacer())
        elif k == 'table':
            head, rows = b[1], b[2]
            o.append(table_html(head, rows, merge_first_blank=(head[0] in ('구분', '차수'))))
            o.append(spacer())
        elif k in ('image', 'code'):
            path = os.path.join(img_dir, FIG1 if k == 'code' else b[1])
            assert os.path.exists(path), path
            images.add(path)
            o.append(image_html(path))
        elif k == 'bullet':
            o.append(par('• ' + inline(b[1]), 10, 'justify', mark=pb.rstrip(','), style='margin-left:14pt;text-indent:-9pt;'))
        elif k == 'para':
            t = b[1]
            if re.match(r'^[①-⑮] ', t):           # 주요 기능 목록
                o.append(par(inline(t), 10, 'left', lh=140, mark=pb.rstrip(','), style='margin-left:18pt;text-indent:-13pt;'))
            else:
                o.append(par(inline(t), 10, 'justify', mark=pb.rstrip(',')))
        prev = b
    o.append('</body></html>\n')
    return ''.join(o), toc_rows


images = set()


def run_hwp(html_text, work, base):
    hp = os.path.join(work, 'report.html')
    with open(hp, 'w', encoding='utf-8') as f:
        f.write(html_text)
    with open(hp + '.tables', 'w', encoding='ascii') as f:
        f.write(''.join(table_policy))
    for p in images:
        shutil.copy(p, os.path.join(work, os.path.basename(p)))
    ps1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hwp_build.ps1')
    r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1,
                        '-Html', hp, '-OutBase', base, '-TimeoutSec', '600', '-HideCoverPageNum', '1'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    sys.stdout.write(r.stdout)
    if r.returncode == 2:
        sys.exit('한글 또는 한워드가 열려 있어 멈췄다. 모두 닫고 다시 실행한다.')
    if not (os.path.exists(base + '.hwp') and os.path.exists(base + '.pdf')):
        sys.exit('HWP를 만들지 못했다. 위 기록(%s.log)을 본다.' % base)


def heading_pages(pdf_path, toc_rows):
    """PDF에서 각 제목이 처음 나오는 쪽 번호(1부터). 찾지 못하면 None."""
    import pymupdf
    d = pymupdf.open(pdf_path)
    norm = lambda s: re.sub(r'\s+', '', s)
    texts = [norm(pg.get_text()) for pg in d]
    pages, cur = [], 2                       # 0=표지, 1=목차 다음부터
    for b in toc_rows:
        key = norm(b[1])
        hit = None
        for p in range(cur, len(texts)):
            if key in texts[p]:
                hit = p
                break
        if hit is None:
            pages.append(None)
        else:
            pages.append(hit + 1)
            cur = hit
    return pages, len(d)


def find_orphans(pdf_path):
    """쪽의 마지막 내용이 표 캡션·제목이거나 표의 머리행뿐이면, 그 표(캡션)를 다음 쪽으로 넘길 블록 번호를 돌려준다."""
    import pymupdf
    d = pymupdf.open(pdf_path)
    norm = lambda t: re.sub(r'\s+', '', t)
    btext = {}
    for bi, b in enumerate(blocks):
        if b[0] in ('h2', 'h3', 'tcap', 'para', 'bullet'):
            btext[bi] = norm(plain(b[1]))
    found = set()
    for pno in range(2, len(d)):
        pg = d[pno]
        lines = []
        for blk in pg.get_text('dict')['blocks']:
            for ln in blk.get('lines', []):
                t = ''.join(sp['text'] for sp in ln['spans']).strip()
                if t and not (ln['bbox'][1] > pg.rect.height - 70 and re.fullmatch(r'-\s*\d+\s*-', t)):
                    lines.append((ln['bbox'][1], ln['bbox'][3], t))
        if not lines:
            continue
        lines.sort()
        bands = sorted(set((round(x['rect'].y0, 1), round(x['rect'].y1, 1)) for x in pg.get_drawings()
                           if x.get('fill') and all(abs(c - 0.905) < 0.02 for c in x['fill'])))
        last_y = lines[-1][0]
        key = None
        if bands and bands[-1][0] - 3 <= last_y <= bands[-1][1] + 3:
            above = [l for l in lines if l[1] <= bands[-1][0] + 2]     # 머리행 위의 마지막 줄(보통 캡션)
            if above:
                key = norm(max(above)[2])
        else:
            key = norm(lines[-1][2])
        if not key or len(key) < 5:
            continue
        for bi, t in btext.items():
            nxt = blocks[bi + 1][0] if bi + 1 < len(blocks) else ''
            if blocks[bi][0] == 'tcap' and (t.startswith(key) or key.startswith(t)):
                found.add(bi)
                break
            if nxt == 'table' and blocks[bi][0] != 'tcap' and t.endswith(key):
                found.add(bi)
                break
    return found


def find_widows(pdf_path):
    """표의 끝자락 몇 줄만 넘어가 거의 빈 쪽이 생기면, 그 표가 속한 소절(제목·도입 문장·캡션)을 통째로 다음 쪽에서 시작하게 한다."""
    import pymupdf
    d = pymupdf.open(pdf_path)
    norm = lambda t: re.sub(r'\s+', '', t)
    caps = {norm(plain(b[1])): bi for bi, b in enumerate(blocks) if b[0] == 'tcap'}
    found = set()
    last_cap = None
    for pno in range(2, len(d)):
        pg = d[pno]
        lines = []
        for blk in pg.get_text('dict')['blocks']:
            for ln in blk.get('lines', []):
                t = ''.join(sp['text'] for sp in ln['spans']).strip()
                if t and not (ln['bbox'][1] > pg.rect.height - 70 and re.fullmatch(r'-\s*\d+\s*-', t)):
                    lines.append((ln['bbox'][1], ln['bbox'][3], t))
        lines.sort()
        page_caps = [caps[norm(t)] for _y0, _y1, t in lines if norm(t) in caps]
        bottom = max([l[1] for l in lines] + [0])
        has_image = bool(pg.get_image_info())
        ruled = any(x['rect'].height > 4 for x in pg.get_drawings())
        if lines and not page_caps and not has_image and ruled and bottom < pg.rect.height * 0.16 and last_cap is not None:
            bi = last_cap
            if bi >= 1 and blocks[bi - 1][0] == 'para' and bi >= 2 and blocks[bi - 2][0] in ('h2', 'h3'):
                bi -= 2
            elif bi >= 1 and blocks[bi - 1][0] in ('h2', 'h3'):
                bi -= 1
            found.add(bi)
        if page_caps:
            last_cap = page_caps[-1]
    return found


def main():
    out = os.path.abspath(out_hwp)
    work = tempfile.mkdtemp(prefix='hwp_build_')
    base = os.path.join(work, 'out')
    breaks = set()
    for attempt in range(12):                         # 쪽 끝에 홀로 남는 캡션·머리행이 없어질 때까지
        html1, toc_rows = build_html(None, breaks)
        run_hwp(html1, work, base)
        new = (find_orphans(base + '.pdf') | find_widows(base + '.pdf')) - breaks
        print('pass %d: 쪽 나눔 %d곳, 새로 찾은 홀로 남은 표 %d개 %s'
              % (attempt + 1, len(breaks), len(new), [blocks[i][1][:16] for i in sorted(new)]))
        if not new:
            break
        breaks.add(min(new))                          # 앞의 것 하나만 넘기고 다시 본다(뒤쪽 배치는 어차피 바뀐다)
        for ext in ('.hwp', '.pdf'):
            os.remove(base + ext)
    pages, n1 = heading_pages(base + '.pdf', toc_rows)
    missing = [b[1] for b, p in zip(toc_rows, pages) if p is None]
    if missing:
        print('목차 쪽 번호를 찾지 못한 제목 %d개: %s' % (len(missing), missing[:3]))
    else:
        for ext in ('.hwp', '.pdf'):
            os.remove(base + ext)
        html2, _ = build_html(pages, breaks)
        run_hwp(html2, work, base)
        pages2, n2 = heading_pages(base + '.pdf', toc_rows)
        if pages2 != pages:
            print('경고: 목차를 채운 뒤 쪽 번호가 달라졌다. 다시 실행해 맞춘다.', n1, n2)
        left = find_orphans(base + '.pdf') - breaks
        if left:
            print('경고: 쪽 끝에 홀로 남은 표가 있다:', [blocks[i][1][:20] for i in sorted(left)])
    shutil.copy(base + '.hwp', out)
    shutil.copy(base + '.pdf', os.path.splitext(out)[0] + '_미리보기.pdf')
    import pymupdf
    n = len(pymupdf.open(base + '.pdf'))
    n_tab = sum(1 for b in blocks if b[0] == 'table')
    print('saved', out, '| %d쪽, 블록 %d개, 표 %d개(+표지 1, 목차 1), 그림 %d개'
          % (n, len(blocks), n_tab, sum(1 for b in blocks if b[0] in ('image', 'code'))))
    print('work dir', work)


if __name__ == '__main__':
    main()
