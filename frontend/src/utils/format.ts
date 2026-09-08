// 숫자 표기 유틸 — 화면마다 복사돼 있던 포맷 함수의 단일 정의.

/** 정수 kg 표기 (천단위 구분) — 4320.4 → "4,320" */
export function fmtInt(n: number): string {
  return Math.round(n).toLocaleString("ko-KR");
}

/** 소수 1자리 kg — 122.456 → "122.5" (PR 값·e1RM) */
export function fmtKg1(n: number): string {
  return (Math.round(n * 10) / 10).toLocaleString("ko-KR", { maximumFractionDigits: 1 });
}

/** 볼륨 축약 표기 — 48920 → "48.9k", 123456 → "123k" (시안 값 라벨 포맷) */
export function fmtK(v: number): string {
  if (v >= 1000) {
    const k = v / 1000;
    if (k >= 100) return `${Math.round(k)}k`;
    return `${k.toFixed(1).replace(/\.0$/, "")}k`;
  }
  return String(Math.round(v));
}

/** 중량 입력값 — 부동소수 오차 제거 후 그대로 (62.5, 20.25). 세트 행·요약 줄 */
export function fmtWeight(w: number): string {
  return String(Math.round(w * 100) / 100);
}

/** 경과 ms → "mm:ss" (휴식 타이머) */
export function fmtClock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
