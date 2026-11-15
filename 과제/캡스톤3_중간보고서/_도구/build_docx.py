# -*- coding: utf-8 -*-
"""작성본 md → 제출용 docx (한글에서 열어 HWP로 저장하기 위한 원고).
- 작업 메모(> 인용문)와 'PPT 요약 구성안' 이후는 넣지 않는다.
- 업무 영역 분할도의 코드 블록은 그림1 PNG로 바꾼다.
사용: python -I -X utf8 build_docx.py <md> <docx> <그림 폴더>"""
import sys, io, re, os
from docx import Document
from docx.shared import Pt, Mm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

md_path, out_path, img_dir = sys.argv[1], sys.argv[2], sys.argv[3]
FONT = '맑은 고딕'
PAGE_W, PAGE_H, MARGIN = 210, 297, 20                 # mm
TOTAL = (PAGE_W - 2 * MARGIN) / 25.4 * 72 - 1.0       # 본문 너비(pt)
COURSE = '데이터베이스 설계'
FIG1 = '그림1_업무영역분할도.png'

# ================= md 읽기 =================
raw = io.open(md_path, encoding='utf-8').read().split('\n')
blocks = []
i = 0
title = None
in_appendix = False
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

# ================= 문서 기본 설정 =================
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Mm(PAGE_W), Mm(PAGE_H)
sec.left_margin = sec.right_margin = Mm(MARGIN)
sec.top_margin, sec.bottom_margin = Mm(22), Mm(20)
sec.footer_distance = Mm(10)
sec.different_first_page_header_footer = True


def style_font(style, size, bold=None, color=None):
    f = style.font
    f.name = FONT
    f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if color:
        f.color.rgb = RGBColor.from_string(color)
    rpr = style.element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts')
        rpr.insert(0, rf)
    for a in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
        rf.set(qn('w:' + a), FONT)
    for a in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
        if rf.get(qn('w:' + a)) is not None:
            del rf.attrib[qn('w:' + a)]


# OOXML 스키마가 정한 자식 요소 순서 (한글의 docx 변환기가 순서에 엄격할 수 있어 지킨다)
ORDER = {
    'pPr': ['pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl', 'numPr',
            'suppressLineNumbers', 'pBdr', 'shd', 'tabs', 'suppressAutoHyphens', 'kinsoku', 'wordWrap',
            'overflowPunct', 'topLinePunct', 'autoSpaceDE', 'autoSpaceDN', 'bidi', 'adjustRightInd', 'snapToGrid',
            'spacing', 'ind', 'contextualSpacing', 'mirrorIndents', 'suppressOverlap', 'jc', 'textDirection',
            'textAlignment', 'textboxTightWrap', 'outlineLvl', 'divId', 'cnfStyle', 'rPr', 'sectPr', 'pPrChange'],
    'tblPr': ['tblStyle', 'tblpPr', 'tblOverlap', 'bidiVisual', 'tblStyleRowBandSize', 'tblStyleColBandSize', 'tblW',
              'jc', 'tblCellSpacing', 'tblInd', 'tblBorders', 'shd', 'tblLayout', 'tblCellMar', 'tblLook'],
    'tcPr': ['cnfStyle', 'tcW', 'gridSpan', 'hMerge', 'vMerge', 'tcBorders', 'shd', 'noWrap', 'tcMar',
             'textDirection', 'tcFitText', 'vAlign', 'hideMark'],
    'trPr': ['cnfStyle', 'divId', 'gridBefore', 'gridAfter', 'wBefore', 'wAfter', 'cantSplit', 'trHeight',
             'tblHeader', 'tblCellSpacing', 'jc', 'hidden'],
}


def put(parent, kind, el):
    """parent(pPr/tblPr/tcPr/trPr) 안에 el을 스키마 순서에 맞는 자리에 넣는다. 같은 요소가 있으면 바꾼다."""
    order = ORDER[kind]
    name = el.tag.split('}')[1]
    old = parent.find(el.tag)
    if old is not None:
        parent.remove(old)
    idx = order.index(name)
    later = set(order[idx + 1:])
    for child in list(parent):
        if child.tag.split('}')[1] in later:
            child.addprevious(el)
            return el
    parent.append(el)
    return el


def sort_children(parent, kind):
    order = ORDER[kind]
    kids = list(parent)
    kids.sort(key=lambda ch: order.index(ch.tag.split('}')[1]) if ch.tag.split('}')[1] in order else 999)
    for ch in kids:
        parent.remove(ch)
    for ch in kids:
        parent.append(ch)


def set_wrap(ppr, word_level):
    """한글 줄바꿈 단위: 낱말(True) / 글자(False, '한글 단어 잘림 허용')"""
    el = OxmlElement('w:wordWrap')
    el.set(qn('w:val'), '1' if word_level else '0')
    put(ppr, 'pPr', el)


def char_wrap(pf_owner):
    ppr = pf_owner.get_or_add_pPr()
    set_wrap(ppr, False)
    # Word가 한글과 숫자·영문 사이를 자동으로 벌려 보이게 하는 기능을 끈다 (한글 프로그램과 같은 모양)
    for tag in ('w:autoSpaceDE', 'w:autoSpaceDN'):
        el = OxmlElement(tag)
        el.set(qn('w:val'), '0')
        put(ppr, 'pPr', el)


st = doc.styles
normal = st['Normal']
style_font(normal, 10)
normal.paragraph_format.space_before = Pt(0)
normal.paragraph_format.space_after = Pt(4)
normal.paragraph_format.line_spacing = 1.35
char_wrap(normal.element)
# 문서 기본 언어
rpr_def = doc.styles.element.find(qn('w:docDefaults')).find(qn('w:rPrDefault')).find(qn('w:rPr'))
lang = rpr_def.find(qn('w:lang'))
if lang is None:
    lang = OxmlElement('w:lang')
    rpr_def.append(lang)
lang.set(qn('w:val'), 'en-US')
lang.set(qn('w:eastAsia'), 'ko-KR')
rf = rpr_def.find(qn('w:rFonts'))
if rf is not None:
    for a in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
        rf.set(qn('w:' + a), FONT)
    for a in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
        if rf.get(qn('w:' + a)) is not None:
            del rf.attrib[qn('w:' + a)]

for name, size, color, before, after in (('Heading 1', 16, '1F3864', 0, 10), ('Heading 2', 13, '000000', 14, 6),
                                         ('Heading 3', 11, '000000', 10, 4)):
    h = st[name]
    style_font(h, size, bold=True, color=color)
    h.font.italic = False
    pf = h.paragraph_format
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    pf.keep_with_next = True
    pf.line_spacing = 1.2
    char_wrap(h.element)
st['Heading 1'].paragraph_format.page_break_before = True

from docx.enum.style import WD_STYLE_TYPE
for name, align, before, after in (('표 캡션', WD_ALIGN_PARAGRAPH.LEFT, 8, 3), ('그림 캡션', WD_ALIGN_PARAGRAPH.CENTER, 4, 10)):
    s_ = st.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    s_.base_style = normal
    style_font(s_, 10)
    pf = s_.paragraph_format
    pf.alignment = align
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    pf.keep_with_next = (name == '표 캡션')
    pf.line_spacing = 1.2


# ================= 글자 넣기 =================
def clean(t):
    return t.replace('`', '')


def add_runs(par, text, size=None, bold=None, color=None):
    text = clean(text)
    for li, line in enumerate(text.split('<br>')):
        if li:
            par.add_run().add_break()
        for seg in re.split(r'(\*\*.+?\*\*)', line):
            if not seg:
                continue
            if seg.startswith('**') and seg.endswith('**') and len(seg) > 4:
                r = par.add_run(seg[2:-2])
                r.bold = True
            else:
                r = par.add_run(seg)
                if bold:
                    r.bold = True
            if size:
                r.font.size = Pt(size)
            if color:
                r.font.color.rgb = RGBColor.from_string(color)
    return par


# ================= 표 =================
def disp_w(s):
    """글자 너비(em 단위 근사): 한글·전각 1.0, 영문·숫자 0.56, 공백 0.3"""
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


def plain(t):
    return re.sub(r'\*\*(.+?)\*\*', r'\1', clean(t))


NOSHRINK_EM = 11.0        # 이보다 짧은 열(이름·번호·근거 등)은 줄이지 않아 낱말이 중간에 꺾이지 않게 한다


def header_em(h):
    """머리글 너비(em). 낱말이 둘 이상이면 두 줄로 나눴을 때의 너비를 쓴다."""
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
    if sum(nat) <= total:                      # 다 들어가면 남는 폭을 넓은 열에 나눠 준다
        extra = total - sum(nat)
        wsum = sum(nat)
        return [n + extra * n / wsum for n in nat]
    cap = 2.5 * total
    natc = [min(e, cap) for e in eff]
    if sum(mn) >= total:                       # 최소 폭만으로도 넘치면 비례 축소
        return [m * total / sum(mn) for m in mn]
    room = total - sum(mn)
    stretch = [max(n - m, 0.0) for n, m in zip(natc, mn)]
    for k in range(ncol):                      # 줄일 수 있는 열은 조금이라도 늘어날 몫을 준다
        if nat[k] > mn[k] and stretch[k] < 1.0:
            stretch[k] = 1.0
    ssum = sum(stretch) or 1.0
    w = [m + room * s / ssum for m, s in zip(mn, stretch)]
    # 본래 폭보다 넓어진 열이 있으면 남는 만큼을 다른 열에 돌린다
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


def set_cell_border_shade(cell, fill=None):
    tcPr = cell._tc.get_or_add_tcPr()
    if fill:
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), fill)
        put(tcPr, 'tcPr', shd)


def add_table(header, rows, total=None, fs=None, align=WD_TABLE_ALIGNMENT.CENTER, merge_first_blank=False):
    total = total or TOTAL
    ncol = len(header)
    if fs is None:
        fs = 9.0 if ncol <= 5 else (8.5 if ncol <= 7 else 8.0)
    widths = col_widths(header, rows, fs, total)
    t = doc.add_table(rows=1 + len(rows), cols=ncol)
    t.style = 'Table Grid'
    t.alignment = align
    t.autofit = False
    tblPr = t._tbl.tblPr
    lay = OxmlElement('w:tblLayout')
    lay.set(qn('w:type'), 'fixed')
    put(tblPr, 'tblPr', lay)
    tblW = OxmlElement('w:tblW')
    tblW.set(qn('w:type'), 'dxa')
    tblW.set(qn('w:w'), str(int(round(sum(widths) * 20))))
    put(tblPr, 'tblPr', tblW)
    mar = OxmlElement('w:tblCellMar')
    for side, v in (('top', 28), ('left', 70), ('bottom', 28), ('right', 70)):
        e = OxmlElement('w:' + side)
        e.set(qn('w:w'), str(v))
        e.set(qn('w:type'), 'dxa')
        mar.append(e)
    put(tblPr, 'tblPr', mar)
    grid = t._tbl.tblGrid
    for k, gc in enumerate(grid.findall(qn('w:gridCol'))):
        gc.set(qn('w:w'), str(int(round(widths[k] * 20))))

    # 가운데 맞출 열: 본문 칸이 모두 짧을 때
    # 낱말 단위로 줄바꿈할 열: 칸의 글이 대체로 짧은 열(이름·목록). 긴 글 열은 글자 단위로 줄바꿈한다.
    center, word_wrap = [], []
    for c in range(ncol):
        body = [plain(r[c]) for r in rows]
        lens = [max(disp_w(ln) for ln in b.split('<br>')) for b in body] or [0.0]
        center.append(all(x <= 13.5 for x in lens) and (ncol > 3 or all('<br>' not in b for b in body)))
        word_wrap.append(sum(lens) / len(lens) <= 14.0)

    def fill(cell, text, c, is_head):
        cell.width = Pt(widths[c])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        pf = p.paragraph_format
        pf.space_before = pf.space_after = Pt(0)
        pf.line_spacing = 1.15
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER if (is_head or center[c]) else WD_ALIGN_PARAGRAPH.LEFT
        if is_head or word_wrap[c]:
            set_wrap(p._p.get_or_add_pPr(), True)
        add_runs(p, text, size=fs, bold=is_head)
        if is_head:
            set_cell_border_shade(cell, 'E7E6E6')
            pf.keep_with_next = True           # 머리행만 쪽 끝에 남지 않게 첫 행과 묶는다

    # 작은 표는 쪽 사이에서 갈라지지 않게 행들을 서로 묶는다
    n_chars = sum(len(plain(v)) for r in rows for v in r)
    keep_together = len(rows) <= 12 and n_chars <= 900

    all_rows = t.rows
    for c, h in enumerate(header):
        fill(all_rows[0].cells[c], h, c, True)
    trPr = all_rows[0]._tr.get_or_add_trPr()
    th = OxmlElement('w:tblHeader')
    trPr.append(th)
    for r, row in enumerate(rows, 1):
        cells = all_rows[r].cells
        for c, v in enumerate(row):
            fill(cells[c], v, c, False)
            if keep_together and r < len(rows):
                cells[c].paragraphs[0].paragraph_format.keep_with_next = True
        trp = all_rows[r]._tr.get_or_add_trPr()
        cs = OxmlElement('w:cantSplit')
        trp.append(cs)

    # 세로 병합
    def vmerge(col, groups):
        for a, b in groups:
            if b > a:
                top = t.cell(a, col)
                keep = top.text
                m = top.merge(t.cell(b, col))
                # 병합으로 생긴 빈 문단 제거
                paras = m.paragraphs
                for extra in paras[1:]:
                    if not extra.text.strip():
                        extra._p.getparent().remove(extra._p)
                m.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    if merge_first_blank:
        groups, start = [], None
        for r, row in enumerate(rows, 1):
            if row[0].strip():
                if start is not None:
                    groups.append((start, r - 1))
                start = r
        if start is not None:
            groups.append((start, len(rows)))
        vmerge(0, groups)
    if '유형' in header and header.index('유형') == 1 and header[-1] == '트랜잭션':
        col = 1
        groups, start = [], 1
        for r in range(2, len(rows) + 2):
            if r == len(rows) + 1 or rows[r - 1][col] != rows[start - 1][col]:
                groups.append((start, r - 1))
                start = r
        # 같은 유형이 이어지는 칸은 글자를 한 번만 남긴다
        for a, b in groups:
            for r in range(a + 1, b + 1):
                cell = t.cell(r, col)
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.text = ''
        vmerge(col, groups)
    return t


def spacer(pt=4):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = Pt(pt)
    return p


# ================= 표지 =================
main_title, _, sub_title = title.partition(' — ')
for _ in range(7):
    doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
add_runs(p, COURSE, size=14, color='404040')
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(10)
add_runs(p, main_title, size=26, bold=True, color='1F3864')
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(14)
add_runs(p, sub_title, size=18, bold=True)
for _ in range(9):
    doc.add_paragraph()
if team:
    add_table(team[1], team[2], total=110 / 25.4 * 72, fs=11)

# ================= 목차 =================
toc_h = doc.add_paragraph()
toc_h.paragraph_format.page_break_before = True
toc_h.paragraph_format.space_after = Pt(14)
add_runs(toc_h, '목차', size=16, bold=True, color='1F3864')
for b in blocks:
    if b[0] == 'h1':
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(3)
        add_runs(p, b[1], size=11.5, bold=True)
    elif b[0] == 'h2':
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Mm(8)
        p.paragraph_format.space_after = Pt(2)
        add_runs(p, b[1], size=10.5)

# ================= 본문 =================
prev = None
in_fig1 = False
for b in blocks:
    k = b[0]
    if k == 'h1':
        doc.add_heading(b[1], level=1)
    elif k == 'h2':
        h = doc.add_heading(b[1], level=2)
        if prev and prev[0] == 'h1':
            h.paragraph_format.space_before = Pt(4)
        if 'ER 다이어그램' in b[1] and '체크리스트' not in b[1]:
            h.paragraph_format.page_break_before = True      # 설명·그림·캡션이 한 쪽에 모이게
            h.paragraph_format.space_before = Pt(0)
    elif k == 'h3':
        doc.add_heading(b[1], level=3)
    elif k == 'tcap':
        doc.add_paragraph(style='표 캡션')
        add_runs(doc.paragraphs[-1], b[1])
    elif k == 'fcap':
        doc.add_paragraph(style='그림 캡션')
        add_runs(doc.paragraphs[-1], b[1])
    elif k == 'table':
        head, rows = b[1], b[2]
        add_table(head, rows, merge_first_blank=(head[0] in ('구분', '차수')))
        spacer(6)
    elif k in ('image', 'code'):
        path = os.path.join(img_dir, FIG1 if k == 'code' else b[1])
        assert os.path.exists(path), path
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.0
        from PIL import Image
        w_px, h_px = Image.open(path).size
        w_mm = 168.0
        if h_px / w_px * w_mm > 205:           # 세로로 긴 그림은 쪽 안에 들어가게
            w_mm = 205 * w_px / h_px
        p.add_run().add_picture(path, width=Mm(w_mm))
    elif k == 'bullet':
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Mm(5.5)
        pf.first_line_indent = Mm(-3.5)
        pf.space_after = Pt(2.5)
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        add_runs(p, '• ' + b[1])
    elif k == 'para':
        p = doc.add_paragraph()
        t = b[1]
        if re.match(r'^[①-⑮] ', t):           # 주요 기능 목록
            p.paragraph_format.left_indent = Mm(6.5)
            p.paragraph_format.first_line_indent = Mm(-4.5)
            p.paragraph_format.space_after = Pt(1.5)
        else:
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if prev and prev[0] == 'table':
                p.paragraph_format.space_before = Pt(2)
        add_runs(p, t)
    prev = b

# ================= 쪽 번호 =================
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = fp.add_run()
run.font.size = Pt(9)
for tag, val in (('begin', None), (None, 'PAGE'), ('end', None)):
    if tag:
        e = OxmlElement('w:fldChar')
        e.set(qn('w:fldCharType'), tag)
    else:
        e = OxmlElement('w:instrText')
        e.set(qn('xml:space'), 'preserve')
        e.text = val
    run._r.append(e)

# ================= 요소 순서 정리 (스키마 순서) =================
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
for root in (doc.element, doc.styles.element):
    for kind in ('pPr', 'tblPr', 'tcPr', 'trPr'):
        for el in root.iter(W + kind):
            sort_children(el, kind)
# 검증: 순서가 어긋난 곳이 남아 있지 않은지
bad = 0
for root in (doc.element, doc.styles.element):
    for kind in ('pPr', 'tblPr', 'tcPr', 'trPr'):
        order = ORDER[kind]
        for el in root.iter(W + kind):
            idx = [order.index(ch.tag.split('}')[1]) for ch in el if ch.tag.split('}')[1] in order]
            unknown = [ch.tag.split('}')[1] for ch in el if ch.tag.split('}')[1] not in order]
            if idx != sorted(idx) or unknown:
                bad += 1
                print('순서 문제', kind, [ch.tag.split('}')[1] for ch in el])
assert bad == 0

doc.core_properties.title = '%s — %s' % (main_title, sub_title)
doc.core_properties.author = ''
doc.save(out_path)
n_tab = sum(1 for b in blocks if b[0] == 'table')
print('saved', out_path, '| 블록 %d개, 표 %d개(+표지 1), 그림 %d개' % (len(blocks), n_tab, sum(1 for b in blocks if b[0] in ('image', 'code'))))
