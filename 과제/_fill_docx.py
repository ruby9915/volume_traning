# -*- coding: utf-8 -*-
"""요구사항정의서_초안.md(정본) → 과제 양식 docx 사본 채우기.

원본 양식은 읽기만 하고, 결과는 과제_요구사항정의서_작성본.docx 로 저장한다.
"""
import copy
import re
import sys

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table

BASE = sys.argv[1]
SRC = BASE + "/과제_요구사항정의서.docx"
OUT = BASE + "/과제_요구사항정의서_작성본.docx"
MD = BASE + "/요구사항정의서_초안.md"
FONT = "맑은 고딕"

md = open(MD, encoding="utf-8").read()


def between(text, start, end_pattern):
    i = text.index(start) + len(start)
    m = re.search(end_pattern, text[i:])
    return text[i : i + m.start()] if m else text[i:]


def table_rows(block, first_cell_pattern):
    rows = []
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if re.fullmatch(first_cell_pattern, cells[0]):
            rows.append(cells)
    return rows


overview = between(md, "## 1. 주제 개요\n", r"\n## ").strip()
narrative = [l.strip() for l in between(md, "### 제출용 업무 서술", r"\n### ").splitlines()[1:] if l.strip()]
reqs = table_rows(between(md, "## 3. 요구사항 명세표", r"\n## "), r"REQ-[FN]-\d+")
entities = table_rows(between(md, "### 엔티티 후보", r"\n### "), r"\d+")
relations = table_rows(between(md, "### 관계 후보", r"\n## "), r"\d+")
assert len(reqs) == 43 and len(entities) == 8 and len(relations) == 15, (len(reqs), len(entities), len(relations))
assert all(len(r) == 7 for r in reqs)

d = docx.Document(SRC)
body = d.element.body


def make_run(text, size_half_pt=19, bold=False):
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for a in ("w:ascii", "w:eastAsia", "w:hAnsi"):
        fonts.set(qn(a), FONT)
    rpr.append(fonts)
    b = OxmlElement("w:b")
    if not bold:
        b.set(qn("w:val"), "0")
    rpr.append(b)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(size_half_pt))
    rpr.append(sz)
    r.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    r.append(t)
    return r


def make_par(segments, size_half_pt=20, space_after=80):
    """segments: [(text, bold), ...]"""
    p = OxmlElement("w:p")
    ppr = OxmlElement("w:pPr")
    sp = OxmlElement("w:spacing")
    sp.set(qn("w:after"), str(space_after))
    ppr.append(sp)
    p.append(ppr)
    for text, bold in segments:
        p.append(make_run(text, size_half_pt, bold))
    return p


def set_cell(tc, text, size_half_pt=19, bold=False):
    paras = tc.findall(qn("w:p"))
    p = paras[0]
    for extra in paras[1:]:
        tc.remove(extra)
    for r in p.findall(qn("w:r")):
        p.remove(r)
    if text:
        p.append(make_run(text, size_half_pt, bold))


def par_text(el):
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


children = list(body.iterchildren())
tables = [c for c in children if c.tag == qn("w:tbl")]
t_head, t_req, t_ent, t_rel, t_rubric = tables


def blanks_after(heading_prefix):
    """heading_prefix 로 시작하는 문단 뒤에 이어지는 밑줄 문단들."""
    out, seen = [], False
    for c in body.iterchildren():
        if c.tag != qn("w:p"):
            if seen and out:
                break
            continue
        txt = par_text(c)
        if txt.startswith(heading_prefix):
            seen = True
            continue
        if seen:
            if txt.startswith("____"):
                out.append(c)
            elif out:
                break
    return out


# --- 머리표: 선정 주제 ---
head_cells = t_head.findall(qn("w:tr"))[1].findall(qn("w:tc"))
set_cell(head_cells[2], "헬스 운동 볼륨 기록·분석 시스템")

# --- 1절 ---
b1 = blanks_after("1. 주제 개요")
anchor = b1[0]
anchor.addprevious(make_par([(overview, False)], 20))
for b in b1:
    body.remove(b)

# --- 2절 ---
b2 = blanks_after("2. 입력 자료")
anchor = b2[0]
for line in narrative:
    m = re.match(r"(\[[^\]]+\])\s*(.*)", line)
    segs = [(m.group(1) + " ", True), (m.group(2), False)] if m else [(line, False)]
    anchor.addprevious(make_par(segs, 20))
for b in b2:
    body.remove(b)

# --- 3절 명세표 ---
rows = t_req.findall(qn("w:tr"))
proto = copy.deepcopy(rows[1])
for r in rows[1:]:
    t_req.remove(r)
for req in reqs:
    tr = copy.deepcopy(proto)
    for tc, text in zip(tr.findall(qn("w:tc")), req):
        set_cell(tc, text)
    t_req.append(tr)

# --- 4절 엔티티 ---
rows = t_ent.findall(qn("w:tr"))
proto = copy.deepcopy(rows[1])
for r in rows[1:]:
    t_ent.remove(r)
for e in entities:
    tr = copy.deepcopy(proto)
    for tc, text in zip(tr.findall(qn("w:tc")), [e[0], e[1], e[2]]):
        set_cell(tc, text)
    t_ent.append(tr)
note = "근거 요구: " + " / ".join("%s(%s)" % (e[1], e[3]) for e in entities)
n1 = make_par([("※ ", True), (note, False)], 18, 40)
n2 = make_par(
    [("※ ", True), ("헬스장은 신규 엔티티다. 세트의 사용 머신, 사용자의 키, 신체 기록의 골격근량·체지방량은 인터뷰에서 새로 나온 속성이다.", False)],
    18,
    160,
)
t_ent.addnext(n1)
n1.addnext(n2)

# --- 4절 관계 ---
rows = t_rel.findall(qn("w:tr"))
proto = copy.deepcopy(rows[1])
for r in rows[1:]:
    t_rel.remove(r)
for r_ in relations:
    tr = copy.deepcopy(proto)
    for tc, text in zip(tr.findall(qn("w:tc")), r_[:5]):
        set_cell(tc, text)
    t_rel.append(tr)
note = "근거 요구: " + " / ".join("%s번(%s)" % (r_[0], r_[5]) for r_ in relations)
m1 = make_par([("※ ", True), (note, False)], 18, 40)
m2 = make_par(
    [
        ("※ ", True),
        (
            "5번과 14번은 자기참조 관계다. 10번은 선택 관계로, 머신 없이도 세트를 저장할 수 있다. "
            "관계 속성: 8번 정렬 순서, 12번 등록자·등록일, 13번 이용 구분(정기/1일), 14번 상태(요청/수락)·공개 등급(일반/상세)·요청일·응답일. "
            "M:N 관계 6건(7, 8, 11, 12, 13, 14번)은 논리설계에서 교차 테이블이 된다.",
            False,
        ),
    ],
    18,
    160,
)
t_rel.addnext(m1)
m1.addnext(m2)

# --- 팀원 정보 표 ---
team_par = [c for c in body.iterchildren() if c.tag == qn("w:p") and par_text(c).startswith("*팀 진행시")][0]
t_team = copy.deepcopy(t_head)
trs = t_team.findall(qn("w:tr"))
for tc, text in zip(trs[0].findall(qn("w:tc")), ["학번", "이름", "역할", "담당"]):
    for t in tc.iter(qn("w:t")):
        t.text = text
for tc in trs[1].findall(qn("w:tc")):
    set_cell(tc, "")
t_team.append(copy.deepcopy(trs[1]))
team_par.addnext(t_team)


def set_widths(tbl, widths, repeat_header=False):
    """열 너비를 고정한다(양식의 tcW 가 자동 맞춤에 묻혀 열이 균등해지는 문제 방지)."""
    tblpr = tbl.find(qn("w:tblPr"))
    for tag in ("w:tblW", "w:jc", "w:tblLayout"):
        for old in tblpr.findall(qn(tag)):
            tblpr.remove(old)
    style = tblpr.find(qn("w:tblStyle"))
    tblw = OxmlElement("w:tblW")
    tblw.set(qn("w:w"), str(sum(widths)))
    tblw.set(qn("w:type"), "dxa")
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    style.addnext(tblw)
    tblw.addnext(jc)
    jc.addnext(layout)
    grid = tbl.find(qn("w:tblGrid"))
    for g, w in zip(grid.findall(qn("w:gridCol")), widths):
        g.set(qn("w:w"), str(w))
    for i, tr in enumerate(tbl.findall(qn("w:tr"))):
        for old in tr.findall(qn("w:trPr")):
            tr.remove(old)
        trpr = OxmlElement("w:trPr")
        trpr.append(OxmlElement("w:cantSplit"))
        if i == 0 and repeat_header:
            trpr.append(OxmlElement("w:tblHeader"))
        tr.insert(0, trpr)
        for tc, w in zip(tr.findall(qn("w:tc")), widths):
            tcw = tc.find(qn("w:tcPr")).find(qn("w:tcW"))
            tcw.set(qn("w:w"), str(w))
            tcw.set(qn("w:type"), "dxa")


set_widths(t_req, [1080, 2850, 900, 1000, 1000, 800, 1780], repeat_header=True)
set_widths(t_ent, [600, 1800, 6240])
set_widths(t_rel, [600, 1800, 2440, 1800, 2000])

d.save(OUT)
print("saved", OUT)
print("reqs", len(reqs), "entities", len(entities), "relations", len(relations), "narrative paragraphs", len(narrative))
