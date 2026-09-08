import { useSyncExternalStore } from "react";

/**
 * 테마 상태 관리 — localStorage persist + html.dark 클래스 적용.
 *
 * zustand store와 분리한 이유: index.html의 인라인 스크립트(첫 페인트 깜빡임 방지)가
 * 같은 localStorage 키를 앱 부트 전에 직접 읽어야 하므로, 직렬화 포맷이 단순 문자열이어야 한다.
 * (인라인 스크립트와 THEME_STORAGE_KEY·클래스 적용 로직을 반드시 동기화할 것)
 */

export type ThemePref = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "vt_theme";
export const THEME_OPTIONS: ThemePref[] = ["system", "light", "dark"];

/** 브라우저 주소창 색(meta theme-color) — index.css의 --color-bg와 동기 */
const META_COLOR = { light: "#f4f6f3", dark: "#0c0b0a" } as const;

const media = window.matchMedia("(prefers-color-scheme: dark)");
const listeners = new Set<() => void>();

function readStored(): ThemePref {
  // 저장소 전면 차단 환경(iOS WebView 일부 등)에서 localStorage 접근 자체가 throw할 수 있다.
  // 이 함수는 모듈 top-level에서 실행되므로 무방비면 import 단계 전면 백지가 된다 (index.html 인라인 스크립트와 동일 수준 방어).
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

let current: ThemePref = readStored();

/** 현재 저장된 테마 선택값 (light | dark | system) */
export function getThemePref(): ThemePref {
  return current;
}

/** 선택값을 실제 렌더링 테마로 해석 */
export function resolveTheme(pref: ThemePref = current): "light" | "dark" {
  if (pref === "system") return media.matches ? "dark" : "light";
  return pref;
}

/** html 클래스·meta theme-color에 즉시 반영 (README: 전환은 transition 없이) */
export function applyTheme(pref: ThemePref = current): void {
  const resolved = resolveTheme(pref);
  document.documentElement.classList.toggle("dark", resolved === "dark");
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", META_COLOR[resolved]);
}

/** 테마 선택 변경: localStorage 저장 + 즉시 적용 + 구독자 알림 */
export function setThemePref(pref: ThemePref): void {
  current = pref;
  try {
    if (pref === "system") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    // 저장 실패해도 세션 내 테마 적용은 계속 (다음 방문 시 system으로 복원될 뿐)
  }
  applyTheme(pref);
  listeners.forEach((l) => l());
}

/**
 * 앱 부트 시 1회 호출 — 저장값 적용 + system 모드용 prefers-color-scheme 리스너 부착.
 * 반환값은 리스너 해제 함수.
 */
export function initTheme(): () => void {
  applyTheme();
  const onSystemChange = () => {
    if (current === "system") applyTheme();
    listeners.forEach((l) => l());
  };
  media.addEventListener("change", onSystemChange);
  return () => media.removeEventListener("change", onSystemChange);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** React hook: 현재 선택값 구독 (Settings 토글 UI 등) */
export function useThemePref(): ThemePref {
  return useSyncExternalStore(subscribe, getThemePref);
}

/** React hook: 실제 렌더링 테마 구독 — 차트 그라디언트 등 JS에서 색 분기할 때 사용 */
export function useResolvedTheme(): "light" | "dark" {
  return useSyncExternalStore(subscribe, () => resolveTheme());
}
