// 최근 사용 종목 id 목록 (localStorage) — ExercisePicker 내부 + Log의 openGroup에서 공용

const RECENT_KEY = "vt_recent_exercises";

export function readRecent(): number[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const arr: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr.filter((n): n is number => typeof n === "number") : [];
  } catch {
    return [];
  }
}

export function pushRecent(id: number): number[] {
  const next = [id, ...readRecent().filter((x) => x !== id)].slice(0, 20);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // 저장소 차단/용량 초과 시 최근 목록 persist만 포기 (세션 내 동작은 유지)
  }
  return next;
}
