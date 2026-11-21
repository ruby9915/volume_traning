"""문서를 숨김 한글 인스턴스에 문자열로 넣고 쪽 이미지를 만든다 (파일 경로는 이미지 출력에만 쓴다).

usage: render.py <doc.hwp|doc.hml> <out_dir> [first last] [--save-hwp out.hwp] [--pages-of idx,idx,...]
  .hwp는 base64(HWP), .hml은 HWPML2X로 넣는다.
  --pages-of : 본문 최상위 문단 번호들의 인쇄 쪽 번호를 출력한다.
"""
import base64
import os
import sys

import pythoncom
import win32com.client

sys.stdout.reconfigure(encoding="utf-8")
args = sys.argv[1:]
doc, out = args[0], args[1]
nums = [a for a in args[2:4] if a.isdigit()]
out = os.path.abspath(out)
os.makedirs(out, exist_ok=True)

pythoncom.CoInitialize()
hwp = win32com.client.DispatchEx("HWPFrame.HwpObject")
try:
    if doc.lower().endswith(".hml"):
        ok = hwp.SetTextFile(open(doc, encoding="utf-8").read(), "HWPML2X", "")
    else:
        ok = hwp.SetTextFile(base64.b64encode(open(doc, "rb").read()).decode("ascii"), "HWP", "")
    print("load:", ok, "pages:", hwp.PageCount, flush=True)
    first = int(nums[0]) if nums else 1
    last = int(nums[1]) if len(nums) > 1 else hwp.PageCount
    for pg in range(first, min(last, hwp.PageCount) + 1):
        path = os.path.join(out, f"page_{pg:02d}.bmp").replace("/", "\\")
        print("page", pg, flush=True)
        if not hwp.CreatePageImage(path, pg - 1, 110, 24, "bmp"):
            print("image failed", pg)
    if "--pages-of" in args:
        for idx in args[args.index("--pages-of") + 1].split(","):
            hwp.SetPos(0, int(idx), 0)
            k = hwp.KeyIndicator()
            print(f"para {idx}: page {k[3]}")
    if "--save-hwp" in args:
        data = base64.b64decode(hwp.GetTextFile("HWP", ""))
        target = args[args.index("--save-hwp") + 1]
        open(target, "wb").write(data)
        print("saved", len(data), "bytes")
finally:
    hwp.Clear(1)
    hwp.Quit()
print("done")
