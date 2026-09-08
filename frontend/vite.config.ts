import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// emptyOutDir: false — Node 24.13.0 on Windows crashes (0xC0000409) in
// fs.rm(recursive) when the project path contains non-ASCII characters.
// dist cleanup is done by scripts/clean-dist.mjs in the npm build script.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    emptyOutDir: false,
  },
  server: {
    host: true,
    proxy: {
      // localhost 대신 127.0.0.1: 이 PC에서 localhost의 IPv6 우선 해석이 간헐적 타임아웃을 유발
      "/api": "http://127.0.0.1:8000",
    },
  },
});
