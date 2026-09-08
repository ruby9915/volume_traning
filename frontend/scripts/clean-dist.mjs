// fs.rm(recursive)가 비ASCII 경로 + Node 24.13.0(Windows)에서 네이티브 크래시를
// 일으키므로 unlink/rmdir로 직접 재귀 삭제한다.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "dist");

function rmrf(p) {
  if (!fs.existsSync(p)) return;
  for (const e of fs.readdirSync(p, { withFileTypes: true })) {
    const f = path.join(p, e.name);
    if (e.isDirectory()) rmrf(f);
    else fs.unlinkSync(f);
  }
  fs.rmdirSync(p);
}

rmrf(dist);
