"""중간보고서 HWPML의 구조를 살핀다 (그림 base64는 잘라서 출력).

usage: inspect_hml.py <report.hml> <cmd> [args]
  outline            루트/HEAD/BODY 구조와 최상위 문단 수
  find <text>        본문 최상위 문단 가운데 text를 포함한 문단의 번호와 속성
  para <n> [m]       최상위 문단 n(~m)의 XML (긴 텍스트·base64는 축약)
  shapes <ids...>    CHARSHAPE / PARASHAPE / BORDERFILL / STYLE 정의
"""
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
path, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]
raw = open(path, encoding="utf-8").read()
raw = re.sub(r"^<\?xml[^>]*\?>", "", raw)
root = ET.fromstring(raw)


def text_of(el):
    return "".join(t.text or "" for t in el.iter("CHAR"))


def short(el, limit=4000):
    s = ET.tostring(el, encoding="unicode")
    s = re.sub(r">([A-Za-z0-9+/=\s]{300,})<", lambda m: f">[base64 {len(m.group(1))}]<", s)
    return s if len(s) <= limit else s[:limit] + f"... [{len(s)} chars]"


body = root.find("BODY")
section = body.find("SECTION")
paras = list(section)

if cmd == "outline":
    print("root", root.tag, root.attrib)
    for ch in root:
        print(" ", ch.tag, ch.attrib, "children:", [c.tag for c in ch][:12])
    head = root.find("HEAD")
    mt = head.find("MAPPINGTABLE")
    for ch in mt:
        print("   MAPPINGTABLE/", ch.tag, ch.attrib, len(ch))
    print("sections:", len(body.findall("SECTION")), "top-level children:", len(paras), {p.tag for p in paras})
    tail = root.find("TAIL")
    if tail is not None:
        print("TAIL children:", [(c.tag, c.attrib, len(c)) for c in tail])
        for b in tail.iter("BINDATA"):
            print("   BINDATA", b.attrib, len(b.text or ""))
elif cmd == "find":
    for i, p in enumerate(paras):
        t = text_of(p)
        if args[0] in t:
            direct = "".join((c.text or "") for tx in p.findall("TEXT") for c in tx.findall("CHAR"))
            print(i, p.attrib, "| direct:", direct[:70], "| tables:", len(list(p.iter("TABLE"))))
elif cmd == "para":
    a = int(args[0]); b = int(args[1]) if len(args) > 1 else a
    for i in range(a, b + 1):
        print(f"--- [{i}]", short(paras[i], int(args[2]) if len(args) > 2 else 4000))
elif cmd == "shapes":
    mt = root.find("HEAD").find("MAPPINGTABLE")
    kind, ids = args[0], set(args[1:])
    for el in mt.iter(kind):
        if el.get("Id") in ids or not ids:
            print(short(el, 3000))
