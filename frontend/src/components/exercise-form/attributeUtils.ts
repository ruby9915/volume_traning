// §10.3 종목 폼·검색 공용 유틸 (v2) — 계열(base_movement)은 전용 필드, 나머지는 자유 태그.
// 이름 자동 조합은 없다: 이름은 통용명을 그대로 쓰고, 태그는 분류·검색에만 쓰인다.

import type { Exercise } from "../../api/types";

/** 태그 입력 문자열("바벨, 시티드") → 정리된 배열 (공백 제거·중복 제거·빈 값 제외) */
export function parseTags(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(/[,\n]/)) {
    const t = raw.trim();
    if (t && !out.includes(t)) out.push(t);
  }
  return out;
}

/** 이미 로드된 종목 목록에서 계열(base_movement) distinct 값 — 자동완성 소스 */
export function distinctBaseMovements(exercises: Exercise[]): string[] {
  const set = new Set<string>();
  for (const e of exercises) if (e.base_movement) set.add(e.base_movement);
  return [...set].sort((a, b) => a.localeCompare(b, "ko"));
}

/** 이미 로드된 종목 목록에서 태그 distinct 값 (빈도순) — 태그 자동완성 소스 */
export function distinctTags(exercises: Exercise[]): string[] {
  const count = new Map<string, number>();
  for (const e of exercises) for (const t of e.tags) count.set(t, (count.get(t) ?? 0) + 1);
  return [...count.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ko")).map(([t]) => t);
}

/** 검색 haystack: name_ko / name_en / aliases / 계열 / 태그 / 머신 (§10.3 검색) */
export function exerciseMatchesQuery(ex: Exercise, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay: (string | null)[] = [
    ex.name_ko,
    ex.name_en,
    ex.base_movement,
    ex.machine_name,
    ...ex.tags,
    ...(ex.aliases ? ex.aliases.split(",") : []),
  ];
  return hay.some((s) => s != null && s.toLowerCase().includes(q));
}
