// 4-B 새 버전 안내 — 열려 있는 앱(특히 홈 화면 앱)은 배포돼도 스스로 새 번들을 받지 않는다.
// 5분마다·화면 복귀 때 index.html을 no-store로 받아 스크립트 해시가 바뀌었으면 배너를 띄운다.
import { useEffect, useState } from "react";

const CHECK_MS = 5 * 60_000;

function currentBundle(): string | null {
  const el = document.querySelector<HTMLScriptElement>('script[src*="/assets/index-"]');
  return el ? new URL(el.src, location.href).pathname : null;
}

async function servedBundle(): Promise<string | null> {
  try {
    const res = await fetch("/", { cache: "no-store", headers: { Accept: "text/html" } });
    if (!res.ok) return null;
    const html = await res.text();
    const m = html.match(/src="([^"]*\/assets\/index-[^"]+\.js)"/);
    return m ? new URL(m[1], location.href).pathname : null;
  } catch {
    return null;
  }
}

export default function UpdateBanner() {
  const [stale, setStale] = useState(false);

  useEffect(() => {
    const mine = currentBundle();
    if (!mine) return;
    let cancelled = false;
    const check = async () => {
      const served = await servedBundle();
      if (!cancelled && served && served !== mine) setStale(true);
    };
    const timer = setInterval(() => void check(), CHECK_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void check();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  if (!stale) return null;
  return (
    <div className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-2" role="status">
      <button
        type="button"
        onClick={() => location.reload()}
        className="touch-target rounded-full bg-accent px-4 text-sm font-bold text-on-accent shadow-card"
      >
        새 버전이 있습니다 · 새로고침
      </button>
    </div>
  );
}
