"""중간보고서(HWP) 사본에 4장을 끼워 넣고 목차를 고쳐 새 HWP를 만든다.

새 숨김 한글 인스턴스에서만 작업하고, 문서는 문자열로 넣고 꺼낸다(사용자가 열어 둔 한글 창·원본 파일은 건드리지 않는다).

usage: final.py <src.hwp> <report.hml> <ch4.hml> <out_dir>
결과: <out_dir>/final.hwp, final.hml, page_NN.bmp(전체 쪽)

만드는 순서 (python 은 pywin32 가 있는 것, 이 PC에서는 anaconda3; <work> 는 임시 폴더의 절대 경로):
  1. python dump_hml.py  ../../캡스톤3_중간보고서/캡스톤3_중간보고서_작성본.hwp <work>/report.hml
  2. python fdd.py <work>  →  bash shots.sh <work>          (FDD 그림. 이미 ../FDD 에 있으면 건너뛴다)
  3. python make_ch4.py <work>/report.hml ../FDD <work>/ch4.hml
  4. python final.py <src.hwp> <work>/report.hml <work>/ch4.hml <work>/out
  5. python to_pdf.py <work>/out/final.hwp <미리보기.pdf>   (python bmp2png.py <work>/out 으로 쪽 그림 확인)
내용을 고칠 때는 content.py 만 고치고 3번부터 다시 한다.
INSERT_AT·TOC_PARA 는 원본 문단 번호다(inspect_hml.py find 로 확인). 원본이 바뀌면 아래 assert 가 알려 준다.
한글은 표를 '나누지 않음'으로 두면 쪽 끝에서 표가 밀리며 뒤 내용과 겹친다. 그래서 표는 모두 '셀 단위로 나눔'이다.
"""
import base64
import os
import re
import sys
import xml.etree.ElementTree as ET

import pythoncom
import win32com.client

sys.stdout.reconfigure(encoding="utf-8")
src, report_hml, ch4_hml, out = sys.argv[1:5]
out = os.path.abspath(out)
os.makedirs(out, exist_ok=True)

INSERT_AT = 243   # "별첨" 장 제목 문단 (inspect_hml.py find 로 확인)
TOC_PARA = 24     # 목차 표가 든 문단

report = open(report_hml, encoding="utf-8").read()
root = ET.fromstring(re.sub(r"^<\?xml[^>]*\?>", "", report))
paras = list(root.find("BODY").find("SECTION"))


def direct(p):
    return "".join((c.text or "") for t in p.findall("TEXT") for c in t.findall("CHAR"))


assert direct(paras[INSERT_AT]) == "별첨", direct(paras[INSERT_AT])
toc_rows = paras[TOC_PARA].find(".//TABLE").findall("ROW")
toc = [("".join(c.text or "" for c in r[0].iter("CHAR")), "".join(c.text or "" for c in r[1].iter("CHAR"))) for r in toc_rows]
assert toc[0][0] == "1. 주제 소개" and toc[14][0] == "별첨", toc[:2]

frag = open(ch4_hml, encoding="utf-8").read()
frag_root = ET.fromstring(re.sub(r"^<\?xml[^>]*\?>", "", frag))
frag_paras = list(frag_root.find("BODY").find("SECTION"))
ADDED = len(frag_paras) - 1          # 마지막 빈 문단은 "별첨" 문단과 합쳐진다
ch4_heads = [(i, direct(p)) for i, p in enumerate(frag_paras) if p.get("ParaShape") in ("18", "21") and direct(p)]
appendix = [(i, direct(p)) for i, p in enumerate(paras) if i >= INSERT_AT and p.get("ParaShape") in ("18", "21")
            and (direct(p) == "별첨" or direct(p).startswith("[별첨"))]
assert len(ch4_heads) == 7 and len(appendix) == 9, (ch4_heads, appendix)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def toc_fragment(entries):
    """entries: [(제목, 쪽, 장 여부)] → 목차 표 한 개짜리 HWPML 문서."""
    def cell(col, row, width, ps, cs, text):
        return (f'<CELL BorderFill="4" ColAddr="{col}" ColSpan="1" Dirty="false" Editable="false" HasMargin="true" Header="false" '
                f'Height="282" Protect="false" RowAddr="{row}" RowSpan="1" Width="{width}"><CELLMARGIN Bottom="75" Left="75" Right="75" Top="75"/>'
                '<PARALIST LineWrap="Break" LinkListID="0" LinkListIDNext="0" TextDirection="0" VertAlign="Center">'
                f'<P ParaShape="{ps}" Style="0"><TEXT CharShape="{cs}"><CHAR>{esc(text)}</CHAR></TEXT><TEXT CharShape="5"/></P></PARALIST></CELL>')
    rows = []
    for r, (title, page, is_chapter) in enumerate(entries):
        if is_chapter:
            rows.append("<ROW>" + cell(0, r, 44100, 7, 8, title) + cell(1, r, 3975, 8, 8, str(page)) + "</ROW>")
        else:
            rows.append("<ROW>" + cell(0, r, 44100, 9, 12, title) + cell(1, r, 3975, 10, 12, str(page)) + "</ROW>")
    table = (
        f'<P ParaShape="4" Style="0"><TEXT CharShape="5"><TABLE BorderFill="3" CellSpacing="0" ColCount="2" PageBreak="Cell" '
        f'RepeatHeader="true" RowCount="{len(rows)}"><SHAPEOBJECT InstId="1500900001" Lock="false" NumberingType="Table" '
        f'TextWrap="TopAndBottom" ZOrder="1"><SIZE Height="{len(rows) * 1217}" HeightRelTo="Absolute" Protect="false" Width="48075" '
        'WidthRelTo="Absolute"/><POSITION AffectLSpacing="false" AllowOverlap="false" FlowWithText="true" HoldAnchorAndSO="false" '
        'HorzAlign="Left" HorzOffset="0" HorzRelTo="Para" TreatAsChar="false" VertAlign="Top" VertOffset="0" VertRelTo="Para"/>'
        '<OUTSIDEMARGIN Bottom="141" Left="141" Right="141" Top="141"/></SHAPEOBJECT>'
        '<INSIDEMARGIN Bottom="150" Left="150" Right="150" Top="150"/>' + "".join(rows) + "</TABLE><CHAR/></TEXT></P>")
    head = report[report.index("<HEAD"):report.index("</HEAD>") + len("</HEAD>")]
    head = re.sub(r"<BINDATALIST.*?</BINDATALIST>", "", head, flags=re.S)
    decl = report[:report.index("<HWPML")]
    opening = re.match(r"<HWPML[^>]*>", report[report.index("<HWPML"):]).group(0)
    # 문단 하나짜리 조각이라, 넣으면 커서가 있는 (비워 둔) 목차 문단 안에 표만 들어간다
    return decl + opening + head + '<BODY><SECTION Id="0">' + table + "</SECTION></BODY><TAIL></TAIL></HWPML>"


pythoncom.CoInitialize()
hwp = win32com.client.DispatchEx("HWPFrame.HwpObject")
try:
    hwp.SetMessageBoxMode(0x00010000 | 0x00001000 | 0x00000001 | 0x00000010)   # 숨김 인스턴스가 대화상자에서 멈추지 않게
    assert hwp.SetTextFile(base64.b64encode(open(src, "rb").read()).decode("ascii"), "HWP", ""), "load failed"
    print("loaded, pages:", hwp.PageCount, flush=True)

    def page_of(para):
        hwp.SetPos(0, para, 0)
        return hwp.KeyIndicator()[3]

    assert page_of(INSERT_AT) == int(toc[14][1]), (page_of(INSERT_AT), toc[14])   # 원본 목차의 '별첨' 쪽과 같은지

    # 1) 4장 삽입
    hwp.SetPos(0, INSERT_AT, 0)
    assert hwp.SetTextFile(frag, "HWPML2X", "insertfile"), "chapter insert failed"
    print("chapter 4 inserted, pages:", hwp.PageCount, flush=True)

    def measure():
        ch4 = [(t, page_of(INSERT_AT + i)) for i, t in ch4_heads]
        app = [(t, page_of(i + ADDED)) for i, t in appendix]
        return ch4, app

    ch4_pages, app_pages = measure()
    entries = [(t, p, not t.startswith(" ")) for t, p in toc[:14]]
    entries += [(t if i == 0 else "     " + t, p, i == 0) for i, (t, p) in enumerate(ch4_pages)]
    entries += [(t if i == 0 else "     " + t, p, i == 0) for i, (t, p) in enumerate(app_pages)]

    # 2) 목차 표 교체: 목차 문단에 붙은 옛 표(컨트롤)만 지우고, 비워진 그 문단에 새 표를 넣는다
    ctrl, old = hwp.HeadCtrl, None
    while ctrl is not None:
        if ctrl.CtrlID == "tbl":
            anchor = ctrl.GetAnchorPos(0)
            if anchor.Item("List") == 0 and anchor.Item("Para") == TOC_PARA:
                old = ctrl
                break
        ctrl = ctrl.Next
    assert old is not None, "목차 표를 찾지 못함"
    assert hwp.DeleteCtrl(old), "목차 표 삭제 실패"
    hwp.SetPos(0, TOC_PARA, 0)
    assert hwp.SetTextFile(toc_fragment(entries), "HWPML2X", "insertfile"), "toc insert failed"
    print("toc replaced, pages:", hwp.PageCount, flush=True)

    again = measure()
    assert again == (ch4_pages, app_pages), "목차를 바꾼 뒤 쪽 번호가 달라짐"
    for t, p, c in entries:
        print(("  " if not c else "") + t.strip(), p)

    open(os.path.join(out, "final.hml"), "w", encoding="utf-8").write(hwp.GetTextFile("HWPML2X", ""))
    data = base64.b64decode(hwp.GetTextFile("HWP", ""))
    open(os.path.join(out, "final.hwp"), "wb").write(data)
    print("final.hwp:", len(data), "bytes", flush=True)
    for pg in range(1, hwp.PageCount + 1):
        path = os.path.join(out, f"page_{pg:02d}.bmp")
        if not hwp.CreatePageImage(path, pg - 1, 110, 24, "bmp"):
            print("image failed", pg)
finally:
    hwp.Clear(1)
    hwp.Quit()
print("done")
