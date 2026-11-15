# -*- coding: utf-8 -*-
"""[그림 2] ER 다이어그램의 draw.io 원본을 만든다.

사용법 (이 폴더의 상위, 즉 캡스톤3_중간보고서 폴더에서):
    python -X utf8 _도구/gen_erd.py .            # 그림2_ERD.drawio 만 만든다
    python -X utf8 _도구/gen_erd.py . --png      # draw.io Desktop으로 PNG 두 장도 내보낸다

만드는 파일:
    그림2_ERD.drawio        쪽 1 = Crow's Foot 보고서용(세로), 쪽 2 = Crow's Foot PPT용(가로), 쪽 3 = Chen 표기(가로)
    그림2_ERD.png           쪽 1 내보내기 (보고서 [그림 2])
    그림2_ERD_PPT용.png     쪽 2 내보내기 (16:9 슬라이드 한 장에 맞춘 배치)
    그림3_ERD_Chen.png      쪽 3 내보내기 (보고서 [그림 3], ERD PPT의 Chen 표기 슬라이드)

내용의 기준은 작성본의 <표 19> 최종 개체 목록과 <표 21> 최종 관계 목록이다.
개체·속성·관계를 고치면 아래 ENTITIES / RELS 만 고치고 다시 실행한다.
두 쪽은 같은 ENTITIES / RELS 에서 만들어지므로 내용이 서로 어긋나지 않는다.
세로 배치의 좌표는 W04 과제의 과제_개념설계ERD.drawio 와 같다(16번 선만 추가).
"""
import os
import subprocess
import sys
from xml.sax.saxutils import quoteattr

TITLE = "헬스 운동 볼륨 기록·분석 시스템 ERD — Crow's Foot(IE) 표기"

# (id, 이름, 식별자 행, 속성 행)  — <표 19>. (FK) 행은 <표 21>의 1:N 관계를 나타낸다.
ENTITIES = [
    ("user", "사용자", ["사용자ID"],
     ["아이디", "비밀번호해시", "표시이름", "키", "소개", "기록공개여부", "관리자여부", "가입일"]),
    ("body", "신체 기록", ["사용자ID (FK)", "날짜"],
     ["체중", "골격근량", "체지방량"]),
    ("muscle", "근육 부위", ["부위ID"],
     ["코드", "이름", "대분류", "단계", "상위부위ID (FK)"]),
    ("ex", "종목", ["종목ID"],
     ["이름", "영문명", "계열", "변형태그 {다중값}", "별칭 {다중값}", "체중계수", "중량배수",
      "내장여부", "기본타겟부위ID (FK)", "소유사용자ID (FK)"]),
    ("sess", "운동 세션", ["세션ID"],
     ["날짜", "메모", "사용자ID (FK)"]),
    ("gym", "헬스장", ["헬스장ID"],
     ["이름", "주소", "위도", "경도", "외부장소ID"]),
    ("set", "세트", ["세트ID"],
     ["순번", "중량", "횟수", "웜업여부", "운동방식", "클라이언트키", "세션ID (FK)", "종목ID (FK)",
      "타겟부위ID (FK)", "머신ID (FK)"]),
    ("mach", "머신", ["머신ID"],
     ["브랜드", "모델명", "한글명", "출처", "참고타겟부위ID (FK)"]),
]

ONE = "ERmandOne"        # || 정확히 1
ZONE = "ERzeroToOne"     # O| 0 또는 1
MANY = "ERzeroToMany"    # O< 0 이상

# 번호: (이름, 앞 개체, 뒤 개체, 앞쪽 끝 기호, 뒤쪽 끝 기호, 식별 관계 여부, 관계 설명 속성, 역할 이름)  — <표 21>
RELS = {
    1: ("수행한다", "user", "sess", ONE, MANY, False, "", None),
    2: ("포함한다", "sess", "set", ONE, MANY, False, "", None),
    3: ("기록된다", "ex", "set", ONE, MANY, False, "", None),
    4: ("타겟이 된다", "muscle", "set", ONE, MANY, False, "", None),
    5: ("세분된다", "muscle", "muscle", ZONE, MANY, False, "", ("상위", "세부")),
    6: ("기본 타겟이다", "muscle", "ex", ONE, MANY, False, "", None),
    7: ("보조로 자극한다", "ex", "muscle", MANY, MANY, False, "", None),
    8: ("즐겨찾는다", "user", "ex", MANY, MANY, False, "{정렬순서}", None),
    9: ("만든다", "user", "ex", ZONE, MANY, False, "", None),
    10: ("사용된다", "mach", "set", ZONE, MANY, False, "", None),
    11: ("담는다", "user", "mach", MANY, MANY, False, "{담은일시}", None),
    12: ("보유한다", "gym", "mach", MANY, MANY, False, "{등록자, 등록일}", None),
    13: ("등록한다", "user", "gym", MANY, MANY, False, "{이용구분, 마지막방문일}", None),
    14: ("친구 요청한다", "user", "user", MANY, MANY, False,
         "{상태, 요청일, 응답일, 공개등급(요청자→상대), 공개등급(상대→요청자)}", ("요청자", "상대")),
    15: ("기록한다", "user", "body", ONE, MANY, True, "", None),
    16: ("참고 타겟이다", "muscle", "mach", ZONE, MANY, False, "", None),
}
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯"

LEGEND_WIDE = [       # 세로 배치: 넓은 상자
    "<b>범례</b>&nbsp; ★ 식별자 · (FK) 외래키 · {다중값} 다중값 속성",
    "관계 이름 아래 { } = 관계 설명 속성 · 번호 = 최종 관계 목록의 관계 번호",
    "실선 = 식별 관계 · 점선 = 비식별 관계",
    "|| 정확히 1(필수) · O| 0 또는 1(선택) · O&lt; 0 이상(선택)",
    "M:N 관계 6개(⑦⑧⑪⑫⑬⑭)는 논리적 설계에서 연관 개체로 분해",
    "유도 속성(볼륨·추정 1RM 등)은 저장하지 않아 제외",
]
LEGEND_NARROW = [     # 가로 배치: 오른쪽 좁은 상자
    "<b>범례</b>",
    "★ 식별자 · (FK) 외래키",
    "{다중값} 다중값 속성",
    "관계 이름 아래 { } = 관계 설명 속성",
    "번호 = 최종 관계 목록의 관계 번호",
    "실선 = 식별 관계 · 점선 = 비식별 관계",
    "|| 정확히 1(필수) · O| 0 또는 1(선택)",
    "O&lt; 0 이상(선택)",
    "M:N 관계 6개(⑦⑧⑪⑫⑬⑭)는",
    "논리적 설계에서 연관 개체로 분해",
    "유도 속성(볼륨·추정 1RM 등)은",
    "저장하지 않아 제외",
]

ROW_H, HEAD_H, DIV_H = 26, 30, 8


def entity_height(pk, attrs):
    return HEAD_H + ROW_H * len(pk) + DIV_H + ROW_H * len(attrs)


# ---------------------------------------------------------------- 배치
# edges[번호] = (exitX, exitY, entryX, entryY, 경유점, 라벨 위치 x(-1~1), 라벨 y 오프셋)
# 라벨 y 오프셋: 선을 가리지 않게 선 위쪽에 두려면 왼쪽→오른쪽 선은 +16, 오른쪽→왼쪽 선은 -16
PORTRAIT = {
    "name": "ERD_보고서용(세로)",
    "w": 200, "font": 12, "head_font": 13, "edge_font": 12, "sub_font": 10, "role_font": 10,
    "title": (40, 10, 640, 36, 18),
    "legend": (40, 1100, 560, 94, 11),
    "legend_lines": LEGEND_WIDE,
    "pos": {"user": (340, 120), "body": (40, 120), "muscle": (40, 490), "ex": (340, 490),
            "sess": (640, 490), "gym": (940, 490), "set": (640, 870), "mach": (940, 870)},
    "edges": {
        1: (1, 0.75, 0.5, 0, [(740, 324)], 0, 0),
        2: (0.5, 1, 0.5, 0, [], 0, 0),
        3: (0.5, 1, 0, 0.1852, [(440, 930)], 0, 0),
        4: (0.5, 1, 0, 0.4938, [(140, 1030)], 0, 0),
        5: (0.3, 0, 0.7, 0, [(100, 442), (180, 442)], 0, 0),
        6: (1, 0.3, 0, 0.1796, [], 0, 16),
        7: (0, 0.4191, 1, 0.7, [], 0, -16),
        8: (0.3, 1, 0.3, 0, [], 0, 0),
        9: (0.7, 1, 0.7, 0, [], 0, 0),
        10: (0, 0.5, 1, 0.2994, [], 0, -16),
        11: (1, 0.25, 1, 0.5, [(1190, 188), (1190, 967)], -0.6, 0),
        12: (0.5, 1, 0.5, 0, [], 0, 0),
        13: (1, 0.5, 0.5, 0, [(1040, 256)], 0, 0),
        14: (0.3, 0, 0.7, 0, [(400, 72), (480, 72)], 0, 0),
        15: (0, 0.2206, 1, 0.3571, [], 0, -16),
        16: (0.2, 1, 0.5, 1, [(80, 1076), (620, 1076), (620, 1226), (1040, 1226)], 0.56, 0),
    },
}

LANDSCAPE = {
    "name": "ERD_PPT용(가로)",
    "w": 210, "font": 15, "head_font": 16, "edge_font": 14, "sub_font": 12, "role_font": 12,
    "title": (40, 10, 760, 36, 20),
    "legend": (1385, 120, 290, 206, 13),
    "legend_lines": LEGEND_NARROW,
    "pos": {"body": (40, 120), "user": (410, 120), "sess": (750, 266), "gym": (1090, 198),
            "muscle": (40, 520), "ex": (410, 520), "set": (750, 520), "mach": (1090, 520)},
    "edges": {
        1: (1, 0.757, 0, 0.423, [], 0, 16),
        2: (0.5, 1, 0.5, 0, [], 0, 0),
        3: (1, 0.188, 0, 0.188, [], 0, 16),
        4: (0.62, 1, 0.5, 1, [(170, 886), (855, 886)], 0, 0),
        5: (0.3, 0, 0.7, 0, [(103, 472), (187, 472)], 0, 0),
        6: (1, 0.237, 0, 0.142, [], 0, 16),
        7: (0, 0.451, 1, 0.753, [], 0, -16),
        8: (0.3, 1, 0.3, 0, [], -0.25, 0),
        9: (0.7, 1, 0.7, 0, [], 0.35, 0),
        10: (0, 0.546, 1, 0.327, [], 0, -16),
        11: (1, 0.11, 1, 0.34, [(1345, 150), (1345, 586)], -0.55, 0),
        12: (0.5, 1, 0.5, 0, [], 0, 0),
        13: (1, 0.368, 0, 0.113, [], 0, 0),
        14: (0.3, 0, 0.7, 0, [(473, 72), (557, 72)], 0, 0),
        15: (0, 0.243, 1, 0.393, [], 0, -16),
        16: (0.25, 1, 0.5, 1, [(92, 930), (1195, 930)], 0.1, 0),
    },
}


# ---------------------------------------------------------------- XML
def cell(cid, value, style, parent, geom, vertex=True, extra=""):
    kind = 'vertex="1"' if vertex else 'edge="1"'
    return ('<mxCell id=%s value=%s style=%s parent=%s %s%s>%s</mxCell>'
            % (quoteattr(cid), quoteattr(value), quoteattr(style), quoteattr(parent), kind, extra, geom))


def geom(x, y, w, h):
    return '<mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry"/>' % (x, y, w, h)


def build_page(lay, page_id):
    out = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    tx, ty, tw, th, tfs = lay["title"]
    out.append(cell("title", TITLE,
                    "text;html=1;align=left;verticalAlign=middle;fontSize=%d;fontStyle=1;" % tfs,
                    "1", geom(tx, ty, tw, th)))
    w, fs = lay["w"], lay["font"]
    row = ("text;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;spacingLeft=6;"
           "spacingRight=4;overflow=hidden;rotatable=0;points=[[0,0.5],[1,0.5]];"
           "portConstraint=eastwest;fontSize=%d;html=1;" % fs)
    for eid, name, pk, attrs in ENTITIES:
        x, y = lay["pos"][eid]
        out.append(cell(eid, name,
                        "swimlane;fontStyle=1;childLayout=stackLayout;horizontal=1;startSize=%d;"
                        "horizontalStack=0;resizeParent=1;resizeParentMax=0;resizeLast=0;collapsible=0;"
                        "marginBottom=0;fillColor=#dae8fc;strokeColor=#6c8ebf;swimlaneFillColor=#ffffff;"
                        "fontSize=%d;html=1;" % (HEAD_H, lay["head_font"]),
                        "1", geom(x, y, w, entity_height(pk, attrs))))
        cy = HEAD_H
        for i, p in enumerate(pk):
            out.append(cell("%s_pk%d" % (eid, i), "★ " + p, row + "fontStyle=1;", eid, geom(0, cy, w, ROW_H)))
            cy += ROW_H
        out.append(cell(eid + "_div", "",
                        "line;strokeWidth=1;fillColor=none;align=left;verticalAlign=middle;spacingTop=-1;"
                        "spacingLeft=3;spacingRight=3;rotatable=0;labelPosition=right;points=[];"
                        "portConstraint=eastwest;strokeColor=inherit;", eid, geom(0, cy, w, DIV_H)))
        cy += DIV_H
        for i, a in enumerate(attrs):
            out.append(cell("%s_a%d" % (eid, i), a, row, eid, geom(0, cy, w, ROW_H)))
            cy += ROW_H

    for no in sorted(RELS):
        name, src, tgt, sa, ea, identifying, sub, roles = RELS[no]
        ex_, ey_, nx_, ny_, pts, lx, ly = lay["edges"][no]
        label = "%s %s" % (CIRCLED[no - 1], name)
        if sub:
            label += '<br><font style="font-size:%dpx">%s</font>' % (lay["sub_font"], sub)
        style = ("edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
                 "startArrow=%s;startFill=0;endArrow=%s;endFill=0;dashed=%d;strokeWidth=1.5;fontSize=%d;"
                 "labelBackgroundColor=#ffffff;exitX=%s;exitY=%s;exitDx=0;exitDy=0;"
                 "entryX=%s;entryY=%s;entryDx=0;entryDy=0;"
                 % (sa, ea, 0 if identifying else 1, lay["edge_font"], ex_, ey_, nx_, ny_))
        g = '<mxGeometry relative="1" as="geometry"'
        if lx:
            g = g.replace('relative="1"', 'x="%s" relative="1"' % lx)
        if ly:
            g = g.replace('relative="1"', 'y="%s" relative="1"' % ly)
        if pts:
            g += '><Array as="points">' + "".join('<mxPoint x="%s" y="%s"/>' % p for p in pts) + '</Array></mxGeometry>'
        else:
            g += '/>'
        rid = "r%02d" % no
        out.append(cell(rid, label, style, "1", g, vertex=False,
                        extra=' source=%s target=%s' % (quoteattr(src), quoteattr(tgt))))
        if roles:
            for k, (text, pos, dx) in enumerate(((roles[0], -0.82, -26), (roles[1], 0.82, 22))):
                out.append(cell("%s_role%d" % (rid, k), text,
                                "edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];"
                                "fontSize=%d;fontColor=#444444;labelBackgroundColor=none;" % lay["role_font"],
                                rid,
                                '<mxGeometry x="%s" relative="1" as="geometry"><mxPoint x="%s" y="0" as="offset"/>'
                                '</mxGeometry>' % (pos, dx),
                                extra=' connectable="0"'))

    lx_, ly_, lw, lh, lfs = lay["legend"]
    lines = lay["legend_lines"]
    out.append(cell("legend", "<br>".join(lines),
                    "rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=top;fillColor=#f5f5f5;"
                    "strokeColor=#999999;fontSize=%d;spacingLeft=8;spacingTop=4;" % lfs,
                    "1", geom(lx_, ly_, lw, lh)))

    return ('<diagram id=%s name=%s><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" '
            'tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" pageWidth="1654" '
            'pageHeight="1169" math="0" shadow="0"><root>%s</root></mxGraphModel></diagram>'
            % (quoteattr(page_id), quoteattr(lay["name"]), "".join(out)))


# ================================================================ Chen 표기 (쪽 3)
# 같은 ENTITIES / RELS 에서 만든다. (FK) 행은 그리지 않는다(관계가 나타낸다).
CHEN_NAME = {4: "타겟이<br>된다", 6: "기본<br>타겟이다", 7: "보조로<br>자극한다", 14: "친구<br>요청한다", 16: "참고<br>타겟이다"}
DW, DH = 130, 56          # 마름모 크기
OFF_Y = 40                # 제목 자리만큼 전체를 아래로 내린다

CHEN_LEGEND = [
    "<b>범례 (Chen 표기)</b>",
    "사각형 = 개체 · 이중 사각형 = 약한 개체 · 마름모 = 관계 · 이중 마름모 = 식별 관계",
    "타원 = 속성 · 밑줄 = 식별자 · 점선 밑줄 = 부분 식별자 · 이중 타원 = 다중값 속성",
    "선 옆의 1 · N · M = 대응 수 · 이중선 = 필수 참여(그 개체의 모든 인스턴스가 참여)",
    "마름모의 번호 = 최종 관계 목록의 관계 번호 · 유도 속성(볼륨·추정 1RM 등)은 저장하지 않아 제외",
]

CHEN = {
    "name": "ERD_Chen(가로)",
    "title": (40, 8, 900, 34, 20),
    "legend": (1245, 30, 600, 104, 12),
    # 개체: 중심 x, 중심 y, 너비, 높이
    "ent": {"user": (640, 225, 140, 90), "body": (200, 225, 130, 64), "muscle": (200, 560, 140, 64),
            "ex": (640, 560, 140, 64), "sess": (1080, 560, 140, 64), "gym": (1520, 560, 140, 64),
            "set": (1080, 900, 140, 64), "mach": (1520, 900, 140, 64)},
    # 개체 속성 타원: (중심 x, 중심 y, 선이 나가는 쪽 L/R/T/B). 식별자, 그다음 속성 순서. FK 제외.
    # 줄이나 열 하나로만 놓고 개체 쪽 꼭짓점에서 선을 내어, 선이 다른 타원을 지나지 않게 한다.
    "attr": {
        "user": [(620, 42, "B"), (732, 42, "B"), (844, 42, "B"), (956, 42, "B"), (1068, 42, "B"),
                 (1140, 84, "L"), (1140, 118, "L"), (1140, 152, "L"), (1140, 186, "L")],
        "body": [(10, 171, "R"), (10, 207, "R"), (10, 243, "R"), (10, 279, "R")],
        "muscle": [(10, 488, "R"), (10, 524, "R"), (10, 560, "R"), (10, 596, "R"), (10, 632, "R")],
        "ex": [(830, 440 + 36 * k, "L") for k in range(9)],
        "sess": [(1280, 524, "L"), (1280, 560, "L"), (1280, 596, "L")],
        "gym": [(1670, 470 + 36 * k, "L") for k in range(6)],
        "set": [(756 + 108 * k, 990, "T") for k in range(7)],
        "mach": [(1700, 950 + 36 * k, "L") for k in range(5)],
    },
    # 관계: 마름모 중심, 앞 개체 쪽 선(개체 위의 점, 경유점들, 마름모 꼭짓점 L/R/T/B), 뒤 개체 쪽 선(꼭짓점, 경유점들, 개체 위의 점)
    "rel": {
        1: ((1080, 400), ((710, 261), [(1080, 261)], "T"), ("B", [], (1080, 528))),
        2: ((1080, 730), ((1080, 592), [], "T"), ("B", [], (1080, 868))),
        3: ((860, 882), ((640, 592), [(640, 882)], "L"), ("R", [], (1010, 882))),
        4: ((440, 918), ((255, 592), [(255, 918)], "L"), ("R", [], (1010, 918))),
        5: ((200, 440), ((135, 528), [], "L"), ("R", [], (265, 528))),
        6: ((360, 540), ((270, 540), [], "L"), ("R", [], (570, 540))),
        7: ((480, 580), ((570, 580), [], "R"), ("L", [], (270, 580))),
        8: ((595, 345), ((595, 270), [], "T"), ("B", [], (595, 528))),
        9: ((685, 455), ((685, 270), [], "T"), ("B", [], (685, 528))),
        10: ((1300, 900), ((1450, 900), [], "R"), ("L", [], (1150, 900))),
        11: ((1790, 740), ((710, 215), [(1790, 215)], "T"), ("B", [(1790, 900)], (1590, 900))),
        12: ((1520, 730), ((1520, 592), [], "T"), ("B", [], (1520, 868))),
        13: ((1520, 390), ((710, 238), [(1520, 238)], "T"), ("B", [], (1520, 528))),
        14: ((480, 120), ((580, 180), [(580, 120)], "R"), ("B", [(480, 200)], (570, 200))),
        15: ((390, 225), ((570, 225), [], "R"), ("L", [], (265, 225))),
        16: ((700, 1085), ((235, 592), [(235, 1085)], "L"), ("R", [(1520, 1085)], (1520, 932))),
    },
    # 관계 설명 속성 타원: (중심 x, 중심 y, 선이 나가는 쪽)
    "rattr": {8: [(450, 345, "R")], 11: [(1665, 770, "R")], 12: [(1380, 712, "R"), (1380, 748, "R")],
              13: [(1380, 372, "R"), (1380, 408, "R")],
              14: [(290, 30, "R"), (290, 64, "R"), (290, 98, "R"), (290, 132, "R"), (290, 166, "R")]},
}


def _kor_w(text):
    w = 0.0
    for ch in text:
        w += 13.0 if ord(ch) >= 0x1100 else 7.6
    return w


def build_chen(page_id):
    lay = CHEN
    out = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    tx, ty, tw, th, tfs = lay["title"]
    out.append(cell("title", TITLE.replace("Crow's Foot(IE) 표기", "Chen 표기"),
                    "text;html=1;align=left;verticalAlign=middle;fontSize=%d;fontStyle=1;" % tfs, "1", geom(tx, ty, tw, th)))
    box = {}                                    # id -> (x0, y0, w, h)

    port = {"L": (0, 0.5), "R": (1, 0.5), "T": (0.5, 0), "B": (0.5, 1)}

    def oval(cid, text, cx, cy, side, kind="", owner=None):
        w = max(92, int(_kor_w(text) + 30))
        h = 30
        value = text
        style = "ellipse;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#555555;fontSize=13;"
        if kind == "key":
            value = "<u>%s</u>" % text
        elif kind == "partial":
            value = '<span style="border-bottom:1px dashed #000000">%s</span>' % text
        elif kind == "multi":
            style = "ellipse;shape=doubleEllipse;margin=3;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#555555;fontSize=13;"
            w += 8
        y = cy + OFF_Y
        out.append(cell(cid, value, style, "1", geom(cx - w / 2.0, y - h / 2.0, w, h)))
        px_, py_ = port[side]
        line = "endArrow=none;html=1;strokeColor=#555555;exitX=%s;exitY=%s;exitDx=0;exitDy=0;" % (px_, py_)
        if owner in box:                        # 개체: 타원의 나가는 점에서 가장 가까운 상자 위의 점으로
            x0, y0, bw, bh = box[owner]
            sx, sy = cx - w / 2.0 + px_ * w, y - h / 2.0 + py_ * h
            nx_, ny_ = min(max(sx, x0), x0 + bw), min(max(sy, y0), y0 + bh)
            line += "entryX=%.4f;entryY=%.4f;entryDx=0;entryDy=0;" % ((nx_ - x0) / bw, (ny_ - y0) / bh)
        out.append(cell(cid + "_l", "", line, "1", '<mxGeometry relative="1" as="geometry"/>', vertex=False,
                        extra=' source=%s target=%s' % (quoteattr(cid), quoteattr(owner))))

    # ---- 개체와 속성
    for eid, name, pk, attrs in ENTITIES:
        cx, cy, w, h = lay["ent"][eid]
        box[eid] = (cx - w / 2.0, cy + OFF_Y - h / 2.0, w, h)
        weak = any("(FK)" in p_ for p_ in pk)
        style = "whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;fontSize=15;"
        if weak:
            style = "shape=ext;margin=3;double=1;" + style
        out.append(cell(eid, name, style, "1", geom(*box[eid])))
        items = [(p_, "partial" if weak else "key") for p_ in pk if "(FK)" not in p_]
        for a in attrs:
            if "(FK)" in a:
                continue
            if "{다중값}" in a:
                items.append((a.replace("{다중값}", "").strip(), "multi"))
            else:
                items.append((a, ""))
        pos = lay["attr"][eid]
        assert len(pos) == len(items), (eid, len(pos), len(items))
        for k, ((text, kind), (ax, ay, side)) in enumerate(zip(items, pos)):
            oval("%s_at%d" % (eid, k), text, ax, ay, side, kind, eid)

    # ---- 관계
    tips = {"L": (0, 0.5), "R": (1, 0.5), "T": (0.5, 0), "B": (0.5, 1)}

    def tip_xy(d, t):
        cx, cy = d
        return {"L": (cx - DW / 2.0, cy), "R": (cx + DW / 2.0, cy), "T": (cx, cy - DH / 2.0), "B": (cx, cy + DH / 2.0)}[t]

    def rel_edge(eid_, ent, ent_pt, wps, did, d, t, text, double, ent_is_source, flip):
        x0, y0, w, h = box[ent]
        ex_, ey_ = (ent_pt[0] - x0) / w, (ent_pt[1] + OFF_Y - y0) / h
        tx_, ty_ = tips[t]
        pts = [ent_pt] + list(wps) + [tip_xy(d, t)] if ent_is_source else [tip_xy(d, t)] + list(wps) + [ent_pt]
        length = sum(((pts[k + 1][0] - pts[k][0]) ** 2 + (pts[k + 1][1] - pts[k][1]) ** 2) ** 0.5 for k in range(len(pts) - 1))
        style = "edgeStyle=none;rounded=0;html=1;endArrow=none;startArrow=none;strokeWidth=1.5;"
        if double:
            style += "shape=link;width=4;"
        if ent_is_source:
            style += "exitX=%.4f;exitY=%.4f;exitDx=0;exitDy=0;entryX=%s;entryY=%s;entryDx=0;entryDy=0;" % (ex_, ey_, tx_, ty_)
            src, tgt = ent, did
            lx = -1 + 2 * min(26.0, length * 0.45) / length
        else:
            style += "exitX=%s;exitY=%s;exitDx=0;exitDy=0;entryX=%.4f;entryY=%.4f;entryDx=0;entryDy=0;" % (tx_, ty_, ex_, ey_)
            src, tgt = did, ent
            lx = 1 - 2 * min(26.0, length * 0.45) / length
        g = '<mxGeometry relative="1" as="geometry">'
        if wps:
            g += '<Array as="points">' + "".join('<mxPoint x="%s" y="%s"/>' % (x, y + OFF_Y) for x, y in wps) + '</Array>'
        g += '</mxGeometry>'
        out.append(cell(eid_, "", style, "1", g, vertex=False, extra=' source=%s target=%s' % (quoteattr(src), quoteattr(tgt))))
        out.append(cell(eid_ + "_c", text,
                        "edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];fontSize=13;fontStyle=1;"
                        "labelBackgroundColor=none;", eid_,
                        '<mxGeometry x="%.3f" y="%d" relative="1" as="geometry"><mxPoint as="offset"/></mxGeometry>'
                        % (lx, (-1 if flip else 1) * (12 + 3.4 * max(0, len(text) - 1))), extra=' connectable="0"'))

    for no in sorted(RELS):
        name, src, tgt, sa, ea, identifying, sub, roles = RELS[no]
        d, a_spec, b_spec = lay["rel"][no]
        did = "c%02d" % no
        label = "%s %s" % (CIRCLED[no - 1], CHEN_NAME.get(no, name))
        style = "rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#b89a3c;fontSize=12;spacing=0;"
        if identifying:
            style = "shape=rhombus;double=1;perimeter=rhombusPerimeter;margin=3;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#b89a3c;fontSize=12;spacing=0;"
        out.append(cell(did, label, style, "1", geom(d[0] - DW / 2.0, d[1] + OFF_Y - DH / 2.0, DW, DH)))
        front = "1" if sa in (ONE, ZONE) else "M"
        back = "N"
        if roles:
            front, back = "%s (%s)" % (front, roles[0]), "%s (%s)" % (back, roles[1])
        (a_pt, a_wps, a_tip), (b_tip, b_wps, b_pt) = a_spec, b_spec
        # 앞 개체는 모두 선택 참여, 뒤 개체는 앞쪽 끝 기호가 '정확히 1'일 때 필수 참여
        rel_edge(did + "_a", src, a_pt, a_wps, did, d, a_tip, front, False, True, no in (5, 8, 9))
        rel_edge(did + "_b", tgt, b_pt, b_wps, did, d, b_tip, back, sa == ONE, False, no in (5, 2, 12, 13, 1))
        ras = [t.strip() for t in sub.strip("{}").split(", ")] if sub else []
        pos = lay["rattr"].get(no, [])
        assert len(pos) == len(ras), (no, ras)
        for k, (text, (ax, ay, side)) in enumerate(zip(ras, pos)):
            oval("%s_at%d" % (did, k), text, ax, ay, side, "", did)

    lx_, ly_, lw, lh, lfs = lay["legend"]
    out.append(cell("legend", "<br>".join(CHEN_LEGEND),
                    "rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=top;fillColor=#f5f5f5;"
                    "strokeColor=#999999;fontSize=%d;spacingLeft=8;spacingTop=4;" % lfs,
                    "1", geom(lx_, ly_ + OFF_Y, lw, lh)))
    return ('<diagram id=%s name=%s><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" '
            'tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" pageWidth="1654" '
            'pageHeight="1169" math="0" shadow="0"><root>%s</root></mxGraphModel></diagram>'
            % (quoteattr(page_id), quoteattr(lay["name"]), "".join(out)))


def find_drawio():
    cands = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "draw.io", "draw.io.exe"),
             os.path.join(os.environ.get("ProgramFiles", ""), "draw.io", "draw.io.exe")]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out_dir = os.path.abspath(args[0] if args else ".")
    assert len(ENTITIES) == 8 and sorted(RELS) == list(range(1, 17))
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n<mxfile host="app.diagrams.net" type="device">'
           + build_page(PORTRAIT, "erd-report") + build_page(LANDSCAPE, "erd-slide")
           + build_chen("erd-chen") + '</mxfile>\n')
    src = os.path.join(out_dir, "그림2_ERD.drawio")
    with open(src, "w", encoding="utf-8", newline="\n") as f:
        f.write(xml)
    print("wrote", src)
    if "--png" in sys.argv:
        exe = find_drawio()
        if not exe:
            sys.exit("draw.io Desktop을 찾지 못했다. 그림2_ERD.drawio를 draw.io에서 열어 쪽별로 PNG(배율 200%)로 내보낸다.")
        for page, name in ((1, "그림2_ERD.png"), (2, "그림2_ERD_PPT용.png"), (3, "그림3_ERD_Chen.png")):
            dst = os.path.join(out_dir, name)
            subprocess.run([exe, "--export", "--format", "png", "--scale", "2", "--border", "20",
                            "--page-index", str(page), "--output", dst, src], check=True)
            print("exported", dst)


if __name__ == "__main__":
    main()
