export const DAY_START_HOUR = 3;

/** 요일 한글 — Date#getDay() 인덱스 (0 = 일요일) */
export const WEEKDAYS_KO = ["일", "월", "화", "수", "목", "금", "토"];

export function toDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** 오늘 날짜 — 하루 경계 03:00 (§5.3): 새벽 운동이 자정에 두 세션으로 쪼개지지 않게 */
export function todayStr(now: Date = new Date()): string {
  return toDateStr(new Date(now.getTime() - DAY_START_HOUR * 3_600_000));
}

export function parseDateStr(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function addDays(dateStr: string, days: number): string {
  const d = parseDateStr(dateStr);
  d.setDate(d.getDate() + days);
  return toDateStr(d);
}

/** ISO 월요일 시작 주의 월요일 날짜 (§6.1 week_start와 동일 규칙) */
export function weekStartStr(dateStr: string): string {
  const d = parseDateStr(dateStr);
  const offset = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - offset);
  return toDateStr(d);
}

/** "7/19 (토)" — 설정 체중 이력·PR 카드 */
export function formatKoreanDate(dateStr: string): string {
  const d = parseDateStr(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()} (${WEEKDAYS_KO[d.getDay()]})`;
}

/** "2026.7.19 (토)" — 세션 상세·이력 헤더 */
export function formatFullDate(dateStr: string): string {
  const d = parseDateStr(dateStr);
  return `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()} (${WEEKDAYS_KO[d.getDay()]})`;
}

/** "7/19" — 지난 기록 힌트·PR 피드·차트 축 라벨 */
export function formatShortDate(dateStr: string): string {
  const d = parseDateStr(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
