// §3.6 종목 속성 체계 — 폼 빌더·검색 공용 유틸 (Log NewExerciseForm · Exercises 폼 공유)
// 불변식: 속성은 분류용 메타데이터일 뿐, 정체성은 exercise_id. 속성→부위/계수 자동 유도는 하지 않는다.

import type { Exercise, ExerciseCreateRequest } from "../../api/types";

export const ATTR_KEYS = ["base_movement", "equipment", "support", "grip", "angle"] as const;
export type AttrKey = (typeof ATTR_KEYS)[number];

export const ATTR_LABELS: Record<AttrKey, string> = {
  base_movement: "동작",
  equipment: "장비",
  support: "자세·지지",
  grip: "그립",
  angle: "각도",
};

export const ATTR_PLACEHOLDERS: Record<AttrKey, string> = {
  base_movement: "예: 벤치프레스",
  equipment: "예: 바벨",
  support: "예: 시티드",
  grip: "예: 와이드",
  angle: "예: 인클라인",
};

/** 폼 내부 draft — 전부 문자열, 빈 문자열 = 미지정 */
export interface AttrDraft {
  base_movement: string;
  equipment: string;
  support: string;
  grip: string;
  angle: string;
  aliases: string;
}

export const EMPTY_ATTRS: AttrDraft = {
  base_movement: "",
  equipment: "",
  support: "",
  grip: "",
  angle: "",
  aliases: "",
};

export function attrsFromExercise(ex: Exercise): AttrDraft {
  return {
    base_movement: ex.base_movement ?? "",
    equipment: ex.equipment ?? "",
    support: ex.support ?? "",
    grip: ex.grip ?? "",
    angle: ex.angle ?? "",
    aliases: ex.aliases ?? "",
  };
}

function norm(s: string | null | undefined): string | null {
  const t = (s ?? "").trim();
  return t ? t : null;
}

/** 요청 body용 변환: 빈 문자열 → null (백엔드 계약 — 빈 문자열은 422, null = 값 비우기) */
export function attrsToPayload(
  d: AttrDraft,
): Pick<
  ExerciseCreateRequest,
  "base_movement" | "equipment" | "support" | "grip" | "angle" | "aliases"
> {
  return {
    base_movement: norm(d.base_movement),
    equipment: norm(d.equipment),
    support: norm(d.support),
    grip: norm(d.grip),
    angle: norm(d.angle),
    aliases: norm(d.aliases),
  };
}

/** 이름 자동 조합 — 어순: 그립 → 지지 → 각도 → 장비 → 동작 (§3.6-2)
 *  예: "클로즈 그립 인클라인 바벨 벤치프레스". 제안일 뿐 강제가 아니다. */
export function composeName(d: AttrDraft): string {
  const grip = d.grip.trim();
  return [
    grip ? (grip.endsWith("그립") ? grip : `${grip} 그립`) : "",
    d.support.trim(),
    d.angle.trim(),
    d.equipment.trim(),
    d.base_movement.trim(),
  ]
    .filter(Boolean)
    .join(" ");
}

/** 이미 로드된 종목 목록에서 속성별 distinct 값 추출 — 자동완성 소스 (사용자 사전) */
export function distinctAttrValues(exercises: Exercise[], key: AttrKey): string[] {
  const set = new Set<string>();
  for (const e of exercises) {
    const v = e[key];
    if (v) set.add(v);
  }
  return [...set].sort((a, b) => a.localeCompare(b, "ko"));
}

/** 같은 5속성 조합의 활성 종목 검색 (§3.6-4 중복 경고 — 차단 아님, 클라이언트 비교) */
export function findDuplicateCombo(
  exercises: Exercise[],
  d: AttrDraft,
  excludeId?: number,
): Exercise | null {
  const target = ATTR_KEYS.map((k) => norm(d[k]));
  if (target.every((v) => v === null)) return null;
  return (
    exercises.find(
      (e) =>
        !e.is_archived &&
        e.id !== excludeId &&
        ATTR_KEYS.every((k, i) => norm(e[k]) === target[i]),
    ) ?? null
  );
}

/** 검색 haystack: name_ko / name_en / aliases / 속성값 전부 (§3.6 검색) */
export function exerciseMatchesQuery(ex: Exercise, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay: (string | null)[] = [
    ex.name_ko,
    ex.name_en,
    ex.base_movement,
    ex.equipment,
    ex.support,
    ex.grip,
    ex.angle,
    ...(ex.aliases ? ex.aliases.split(",") : []),
  ];
  return hay.some((s) => s != null && s.toLowerCase().includes(q));
}

/** §3.6 규율 문구 확인이 필요한 변경인지 — 분류 5속성만 비교 (aliases는 검색 전용이라 제외) */
export function classificationChanged(ex: Exercise, d: AttrDraft): boolean {
  return ATTR_KEYS.some((k) => norm(ex[k]) !== norm(d[k]));
}
