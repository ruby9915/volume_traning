"""HWP를 숨김 한글 인스턴스에 문자열로 넣고 PDF로 저장한다(모양 확인용 미리보기).

usage: to_pdf.py <doc.hwp> <out.pdf>
"""
import base64
import os
import sys

import pythoncom
import win32com.client

sys.stdout.reconfigure(encoding="utf-8")
doc, out = sys.argv[1], os.path.abspath(sys.argv[2])
pythoncom.CoInitialize()
hwp = win32com.client.DispatchEx("HWPFrame.HwpObject")
try:
    hwp.SetMessageBoxMode(0x00010000 | 0x00001000 | 0x00000001 | 0x00000010)
    assert hwp.SetTextFile(base64.b64encode(open(doc, "rb").read()).decode("ascii"), "HWP", "")
    print("pages:", hwp.PageCount, flush=True)
    print("saveas:", hwp.SaveAs(out, "PDF", ""), flush=True)
finally:
    hwp.Clear(1)
    hwp.Quit()
print("done", os.path.exists(out), os.path.getsize(out) if os.path.exists(out) else 0)
