"""HWP 문서를 HWPML(XML)로 꺼낸다 — 문단·표·글자 모양 ID를 살펴보거나 조각 문서의 HEAD로 쓰기 위해.

새 숨김 한글 인스턴스에 문서를 문자열(base64)로 넣고 꺼내므로, 열어 둔 한글 창이나 원본 파일은 건드리지 않는다.
usage: dump_hml.py <src.hwp> <out.hml>
"""
import base64
import sys

import pythoncom
import win32com.client

sys.stdout.reconfigure(encoding="utf-8")
src, out = sys.argv[1], sys.argv[2]
pythoncom.CoInitialize()
hwp = win32com.client.DispatchEx("HWPFrame.HwpObject")  # DispatchEx = 항상 새 프로세스
try:
    assert hwp.SetTextFile(base64.b64encode(open(src, "rb").read()).decode("ascii"), "HWP", ""), "load failed"
    ml = hwp.GetTextFile("HWPML2X", "")
    open(out, "w", encoding="utf-8").write(ml)
    print("pages:", hwp.PageCount, "| HWPML chars:", len(ml))
finally:
    hwp.Clear(1)  # 저장하지 않고 버림
    hwp.Quit()
