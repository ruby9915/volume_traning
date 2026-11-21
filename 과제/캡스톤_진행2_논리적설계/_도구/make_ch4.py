"""4장(논리적 설계)을 HWPML 조각 문서로 만든다.

중간보고서 HWPML의 HEAD(글자·문단·테두리 모양)를 그대로 쓰고, 본문만 4장으로 바꾼다.
그래서 삽입한 뒤의 표·문단 모양이 1~3장과 같다.

usage: make_ch4.py <report.hml> <fdd_dir> <out.hml> [--list] [--keep-norm]
  <report.hml> : dump_hml.py 로 꺼낸 중간보고서 HWPML
  <fdd_dir>    : fdd1.png ~ fdd3.png (fdd.py + shots.sh 로 만든 2배율 PNG)
  --list       : (5) 최종 릴레이션 스키마를 상자(표) 대신 문단으로
  --keep-norm  : 정규화 표를 쪽 경계에서 나누지 않음 — 한글에서 표가 다음 쪽으로 밀리며 캡션과 떨어지므로 쓰지 말 것
"""
import base64
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import content as C  # noqa: E402

report, fdd_dir, out_path = sys.argv[1:4]
FINAL_AS_BOX = "--list" not in sys.argv
NORM_BREAK = "None" if "--keep-norm" in sys.argv else "Table"   # 정규화 표를 쪽 경계에서 나눌지

# 중간보고서에서 쓰는 모양 ID (inspect_hml.py로 확인)
PS_CHAPTER, CS_CHAPTER = 18, 10      # "3. 개념적 설계" (쪽 나눔 포함)
PS_SECTION, CS_SECTION = 21, 11      # "(5) 제약조건 정의"
PS_BODY, CS_BODY = 13, 1             # 본문
PS_CAPTION = 23                      # "<표 38> ..."
PS_TABLE, CS_CTRL = 14, 5            # 표를 담는 문단
PS_SPACER, CS_SPACER = 15, 17        # 표 뒤 간격
PS_CENTER, PS_LEFT = 5, 6            # 셀 안 문단
CS_HEAD, CS_CELL = 14, 16            # 셀 글자 (머리 굵게 / 본문)
CS_CELL_U, CS_BODY_U = 21, 22        # 새로 추가: 밑줄
BF_CELL, BF_HEAD = 3, 5              # 테두리 / 테두리+회색
TABLE_W = 48000

src = open(report, encoding="utf-8").read()
head = src[src.index("<HEAD"):src.index("</HEAD>") + len("</HEAD>")]
decl = src[:src.index("<HWPML")]
hwpml_open = re.match(r"<HWPML[^>]*>", src[src.index("<HWPML"):]).group(0)


def clone_charshape(head, base_id, new_id):
    m = re.search(rf'<CHARSHAPE [^>]*Id="{base_id}"[^>]*>.*?</CHARSHAPE>', head, re.S)
    shape = m.group(0).replace(f'Id="{base_id}"', f'Id="{new_id}"', 1)
    assert "<UNDERLINE" not in shape
    return shape.replace("</CHARSHAPE>", '<UNDERLINE Color="0" Shape="Solid" Type="Bottom"/></CHARSHAPE>')


n_char = int(re.search(r'<CHARSHAPELIST Count="(\d+)"', head).group(1))
assert n_char == 21, n_char
extra = clone_charshape(head, CS_CELL, CS_CELL_U) + clone_charshape(head, CS_BODY, CS_BODY_U)
head = head.replace('<CHARSHAPELIST Count="21"', '<CHARSHAPELIST Count="23"').replace("</CHARSHAPELIST>", extra + "</CHARSHAPELIST>")
_binlist = '<BINDATALIST Count="3">' + "".join(f'<BINITEM BinData="{i}" Format="PNG" Type="Embedding"/>' for i in (1, 2, 3)) + "</BINDATALIST>"
head = re.sub(r"<BINDATALIST.*?</BINDATALIST>", lambda m: _binlist, head, flags=re.S)

_inst = [1500000000]
_z = [200]


def inst():
    _inst[0] += 7
    return _inst[0]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(s, cs):
    return f'<TEXT CharShape="{cs}"><CHAR>{esc(s)}</CHAR></TEXT>'


def p(inner, ps):
    return f'<P ParaShape="{ps}" Style="0">{inner}</P>'


def schema(s, cs, cs_u):
    out = []
    for i, part in enumerate(re.split(r"\[\[(.*?)\]\]", s)):
        if part:
            out.append(text(part, cs_u if i % 2 else cs))
    return "".join(out)


def cell_p(inner, ps):
    return p(inner + f'<TEXT CharShape="{CS_CTRL}"/>', ps)


def cell(col, row, width, paras, border=BF_CELL, colspan=1, rowspan=1, height=282):
    return (f'<CELL BorderFill="{border}" ColAddr="{col}" ColSpan="{colspan}" Dirty="false" Editable="false" HasMargin="true" '
            f'Header="false" Height="{height}" Protect="false" RowAddr="{row}" RowSpan="{rowspan}" Width="{width}">'
            '<CELLMARGIN Bottom="75" Left="75" Right="75" Top="75"/>'
            '<PARALIST LineWrap="Break" LinkListID="0" LinkListIDNext="0" TextDirection="0" VertAlign="Center">'
            f"{paras}</PARALIST></CELL>")


def th(col, row, width, label, **kw):
    return cell(col, row, width, cell_p(text(label, CS_HEAD), PS_CENTER), border=BF_HEAD, **kw)


def td(col, row, width, s, center=False, **kw):
    return cell(col, row, width, cell_p(text(s, CS_CELL) if s else "", PS_CENTER if center else PS_LEFT), **kw)


def td_schema(col, row, width, s, **kw):
    return cell(col, row, width, cell_p(schema(s, CS_CELL, CS_CELL_U), PS_LEFT), **kw)


def table(rows, ncols, page_break="Table", height=None):
    _z[0] += 1
    return p(
        f'<TEXT CharShape="{CS_CTRL}"><TABLE BorderFill="{BF_CELL}" CellSpacing="0" ColCount="{ncols}" PageBreak="{page_break}" '
        f'RepeatHeader="true" RowCount="{len(rows)}"><SHAPEOBJECT InstId="{inst()}" Lock="false" NumberingType="Table" '
        f'TextWrap="TopAndBottom" ZOrder="{_z[0]}"><SIZE Height="{height or len(rows) * 460}" HeightRelTo="Absolute" Protect="false" '
        f'Width="{TABLE_W}" WidthRelTo="Absolute"/><POSITION AffectLSpacing="false" AllowOverlap="false" FlowWithText="true" '
        'HoldAnchorAndSO="false" HorzAlign="Left" HorzOffset="0" HorzRelTo="Para" TreatAsChar="false" VertAlign="Top" '
        'VertOffset="0" VertRelTo="Para"/><OUTSIDEMARGIN Bottom="141" Left="141" Right="141" Top="141"/></SHAPEOBJECT>'
        '<INSIDEMARGIN Bottom="150" Left="150" Right="150" Top="150"/>'
        + "".join(f"<ROW>{''.join(r)}</ROW>" for r in rows) + "</TABLE><CHAR/></TEXT>", PS_TABLE)


def png_size(path):
    d = open(path, "rb").read(32)
    return struct.unpack(">II", d[16:24])


def picture(bin_id, path, name):
    pw, ph = png_size(path)           # 2배율로 찍은 PNG
    w, h = int(pw / 2 * 56.25), int(ph / 2 * 56.25)   # CSS px × 0.75 × 75 HWPUNIT
    _z[0] += 1
    return (
        f'<PICTURE Reverse="false"><SHAPEOBJECT InstId="{inst()}" Lock="false" NumberingType="Figure" ZOrder="{_z[0]}">'
        f'<SIZE Height="{h}" HeightRelTo="Absolute" Protect="false" Width="{w}" WidthRelTo="Absolute"/>'
        '<POSITION AffectLSpacing="false" AllowOverlap="false" FlowWithText="true" HoldAnchorAndSO="false" HorzAlign="Left" '
        'HorzOffset="0" HorzRelTo="Column" TreatAsChar="true" VertAlign="Top" VertOffset="0" VertRelTo="Para"/>'
        '<OUTSIDEMARGIN Bottom="0" Left="0" Right="0" Top="0"/>'
        f"<SHAPECOMMENT>{esc(name)}</SHAPECOMMENT></SHAPEOBJECT>"
        f'<SHAPECOMPONENT GroupLevel="0" HorzFlip="false" InstID="{inst()}" OriHeight="{h}" OriWidth="{w}" VertFlip="false" XPos="0" YPos="0">'
        f'<ROTATIONINFO Angle="0" CenterX="{w // 2}" CenterY="{h // 2}" Rotate="1"/><RENDERINGINFO>'
        '<TRANSMATRIX E1="1.00000" E2="0.00000" E3="0.00000" E4="0.00000" E5="1.00000" E6="0.00000"/>'
        '<SCAMATRIX E1="1.00000" E2="0.00000" E3="0.00000" E4="0.00000" E5="1.00000" E6="0.00000"/>'
        '<ROTMATRIX E1="1.00000" E2="0.00000" E3="0.00000" E4="0.00000" E5="1.00000" E6="0.00000"/></RENDERINGINFO></SHAPECOMPONENT>'
        f'<IMAGERECT X0="0" X1="{w}" X2="{w}" X3="0" Y0="0" Y1="0" Y2="{h}" Y3="{h}"/>'
        '<IMAGECLIP Bottom="0" Left="0" Right="0" Top="0"/><INSIDEMARGIN Bottom="0" Left="0" Right="0" Top="0"/>'
        f'<IMAGEDIM Height="0" Width="0"/><IMAGE Alpha="0" BinItem="{bin_id}" Bright="0" Contrast="0" Effect="RealPic"/><EFFECTS/></PICTURE>'
    ), h


def chapter(s):
    return p(text(s, CS_CHAPTER), PS_CHAPTER)


def section(s):
    return p(text(s, CS_SECTION), PS_SECTION)


def body(s):
    return p(text(s, CS_BODY), PS_BODY)


def caption(s):
    return p(text(s, CS_BODY), PS_CAPTION)


SPACER = p(text(" ", CS_SPACER), PS_SPACER)
W4 = [3000, 7500, 23500, 14000]


def schema_table(headers, rows):
    out = [[th(i, 0, w, h) for i, (h, w) in enumerate(zip(headers, W4))]]
    for r, (no, name, s, memo) in enumerate(rows, start=1):
        out.append([td(0, r, W4[0], str(no), center=True), td(1, r, W4[1], name, center=True),
                    td_schema(2, r, W4[2], s), td(3, r, W4[3], memo)])
    return table(out, 4)


parts = [chapter("4. 논리적 설계"), body(C.INTRO)]
parts += [section("(1) 개체 릴레이션 스키마"), body(C.S1_TEXT), caption("<표 39> 개체 릴레이션 스키마"),
          schema_table(["No", "개체", "릴레이션 스키마", "비고"],
                       [(i, n, s, m) for i, (n, s, m) in enumerate(C.ENTITY_RELATIONS, 1)]), SPACER]
parts += [section("(2) 관계 릴레이션 스키마"), body(C.S2_TEXT), caption("<표 40> 관계 릴레이션 스키마"),
          schema_table(["No", "관계", "릴레이션 스키마", "비고"], C.RELATIONSHIP_RELATIONS), SPACER, body(C.S2_TYPES)]
parts += [section("(3) 단순화된 릴레이션 스키마"), body(C.S3_TEXT_A), body(C.S3_TEXT_B),
          caption("<표 41> 단순화된 릴레이션 스키마"),
          schema_table(["No", "개체 및 관계", "릴레이션 스키마", "비고"],
                       [(i, n, s, m) for i, (n, s, m) in enumerate(C.SIMPLIFIED, 1)]), SPACER]

parts += [section("(4) 릴레이션 정규화"), body(C.S4_TEXT)]
WN = [7600, 4400, 36000]
wide = WN[1] + WN[2]
bins = []
for i, n in enumerate(C.NORMALIZATION, start=1):
    png = os.path.join(fdd_dir, f"fdd{i}.png")
    bins.append(png)
    pic, pic_h = picture(i, png, f"{n['name']} 릴레이션의 함수적 종속 다이어그램")
    rows = [
        [th(0, 0, WN[0], "릴레이션 스키마"), td_schema(1, 0, wide, n["schema"], colspan=2)],
        [th(0, 1, WN[0], "기본 키"), td(1, 1, wide, n["pk"], colspan=2)],
        [th(0, 2, WN[0], "대체 키"), td(1, 2, wide, n["ak"], colspan=2)],
        [th(0, 3, WN[0], "함수적 종속"),
         cell(1, 3, wide, "".join(cell_p(text(f, CS_CELL), PS_LEFT) for f in n["fds"]), colspan=2)],
        [th(0, 4, WN[0], "FDD", height=pic_h + 300),
         cell(1, 4, wide, p(f'<TEXT CharShape="{CS_CTRL}">{pic}<CHAR/></TEXT>', PS_LEFT), colspan=2, height=pic_h + 300)],
    ]
    for j, (nf, t) in enumerate(n["nf"]):
        r = 5 + j
        row = [th(0, r, WN[0], "정규형", rowspan=3, height=846)] if j == 0 else []
        row += [td(1, r, WN[1], nf, center=True), td(2, r, WN[2], t)]
        rows.append(row)
    parts += [caption(f"<표 {41 + i}> {n['name']} 릴레이션의 정규화 내용"), table(rows, 3, page_break=NORM_BREAK, height=pic_h + 3600), SPACER]
parts.append(body(C.S4_CLOSING))

parts += [section("(5) 최종 릴레이션 스키마"), body(C.S5_TEXT)]
if FINAL_AS_BOX:  # 쪽 경계에서 셀 안의 문단이 나뉘도록 PageBreak="Cell"
    lines = "".join(cell_p(schema(s, CS_CELL, CS_CELL_U), PS_LEFT) for _, s, _ in C.SIMPLIFIED)
    parts += [table([[cell(0, 0, TABLE_W, lines, height=20 * 300)]], 1, page_break="Cell", height=20 * 300), SPACER]
else:
    parts += [p(schema(s, CS_BODY, CS_BODY_U), PS_LEFT) for _, s, _ in C.SIMPLIFIED]

WC = [3000, 28500, 7000, 9500]
rows = [[th(i, 0, w, h) for i, (h, w) in enumerate(zip(["No", "제약조건", "제약 유형", "관련 릴레이션"], WC))]]
for r, (t, kind, rel) in enumerate(C.CONSTRAINTS, start=1):
    rows.append([td(0, r, WC[0], str(r), center=True), td(1, r, WC[1], t), td(2, r, WC[2], kind, center=True),
                 td(3, r, WC[3], rel, center=True)])
parts += [section("(6) 무결성 제약조건 정의"), body(C.S6_TEXT), caption("<표 45> 무결성 제약조건"), table(rows, 4), SPACER,
          body(C.S6_NOTE)]
# 끼워 넣을 때 조각의 마지막 문단은 커서가 있던 문단("별첨")과 합쳐진다.
# 그래서 장 제목 모양의 빈 문단으로 끝내, 합쳐진 뒤에도 "별첨"이 원래 모양(쪽 나눔 포함)을 갖게 한다.
parts.append(p(f'<TEXT CharShape="{CS_CHAPTER}"/>', PS_CHAPTER))

storage = "".join(
    f'<BINDATA Encoding="Base64" Id="{i}" Size="{os.path.getsize(f)}">{base64.b64encode(open(f, "rb").read()).decode()}</BINDATA>'
    for i, f in enumerate(bins, start=1))
doc = (decl + hwpml_open + head + '<BODY><SECTION Id="0">' + "".join(parts) + "</SECTION></BODY>"
       + f"<TAIL><BINDATASTORAGE>{storage}</BINDATASTORAGE></TAIL></HWPML>")

import xml.dom.minidom  # noqa: E402
xml.dom.minidom.parseString(re.sub(r"^<\?xml[^>]*\?>", "", doc).encode("utf-8"))  # 형식 오류면 여기서 멈춘다
open(out_path, "w", encoding="utf-8").write(doc)
print("fragment:", len(doc), "chars;", "paragraphs:", len(parts), "tables:", doc.count("<TABLE"), "pictures:", doc.count("<PICTURE"))
