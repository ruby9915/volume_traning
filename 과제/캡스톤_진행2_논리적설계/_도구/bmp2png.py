"""24비트 BMP → PNG (표준 라이브러리). usage: bmp2png.py <dir>  — dir 안의 *.bmp를 같은 이름의 .png로."""
import glob
import os
import struct
import sys
import zlib


def convert(path):
    d = open(path, "rb").read()
    assert d[:2] == b"BM"
    off = struct.unpack_from("<I", d, 10)[0]
    w, h, _, bpp = struct.unpack_from("<iiHH", d, 18)
    assert bpp in (24, 32), bpp
    n = bpp // 8
    stride = (w * n + 3) & ~3
    top_down = h < 0
    h = abs(h)
    rows = []
    for y in range(h):
        src = y if top_down else h - 1 - y
        line = d[off + src * stride: off + src * stride + w * n]
        rgb = bytearray(w * 3)
        rgb[0::3] = line[2::n]
        rgb[1::3] = line[1::n]
        rgb[2::3] = line[0::n]
        rows.append(b"\x00" + bytes(rgb))

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))
    out = os.path.splitext(path)[0] + ".png"
    open(out, "wb").write(png)
    return out, w, h


for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.bmp"))):
    print(*convert(f))
