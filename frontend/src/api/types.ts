// SETTING.MD §4.2 전 엔드포인트 request/response 타입 — 프론트·백엔드 공용 계약

// ---------- 부위 (§3.4) ----------

export type Region = "chest" | "back" | "shoulders" | "arms" | "legs" | "core";

export type MuscleCode =
  | "chest"
  | "back"
  | "lower_back"
  | "shoulders"
  | "biceps"
  | "triceps"
  | "forearms"
  | "quads"
  | "hamstrings"
  | "glutes"
  | "calves"
  | "abs";

export type MuscleRole = "primary" | "secondary";

export interface MuscleGroupInfo {
  code: MuscleCode;
  name_ko: string;
  region: Region;
}

export const MUSCLE_GROUPS: MuscleGroupInfo[] = [
  { code: "chest", name_ko: "가슴", region: "chest" },
  { code: "back", name_ko: "등", region: "back" },
  { code: "lower_back", name_ko: "허리(기립근)", region: "back" },
  { code: "shoulders", name_ko: "어깨", region: "shoulders" },
  { code: "biceps", name_ko: "이두", region: "arms" },
  { code: "triceps", name_ko: "삼두", region: "arms" },
  { code: "forearms", name_ko: "전완", region: "arms" },
  { code: "quads", name_ko: "대퇴사두", region: "legs" },
  { code: "hamstrings", name_ko: "햄스트링", region: "legs" },
  { code: "glutes", name_ko: "둔근", region: "legs" },
  { code: "calves", name_ko: "종아리", region: "legs" },
  { code: "abs", name_ko: "복근", region: "core" },
];

/** code → 한글 이름 (MUSCLE_GROUPS에서 파생) — 칩·뱃지 표기용 */
export const MUSCLE_NAME_KO: Record<MuscleCode, string> = Object.fromEntries(
  MUSCLE_GROUPS.map((m) => [m.code, m.name_ko]),
) as Record<MuscleCode, string>;

export const REGION_NAMES_KO: Record<Region, string> = {
  chest: "가슴",
  back: "등",
  shoulders: "어깨",
  arms: "팔",
  legs: "하체",
  core: "코어",
};

// ---------- Auth ----------

export interface LoginRequest {
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number; // seconds
}

// ---------- Exercises ----------

export interface ExerciseMuscle {
  code: MuscleCode;
  role: MuscleRole;
}

export interface Exercise {
  id: number;
  name_ko: string;
  name_en: string | null;
  bodyweight_factor: number;
  load_multiplier: number;
  is_builtin: boolean;
  is_archived: boolean;
  note: string | null;
  muscles: ExerciseMuscle[];
  // §3.6 종목 속성 — 분류용 메타데이터 (정체성은 exercise_id). 자유 텍스트, enum 없음.
  base_movement: string | null; // 동작: "벤치프레스", "로우" 등
  equipment: string | null; // 장비: "바벨", "덤벨", "케이블", "머신" 등
  support: string | null; // 자세/지지: "시티드", "스탠딩", "라잉" 등
  grip: string | null; // 그립: "클로즈", "와이드", "뉴트럴" 등
  angle: string | null; // 각도: "인클라인", "디클라인" 등
  aliases: string | null; // 검색 별칭, 쉼표 구분: "숄더프레스,밀리터리 프레스"
}

export interface ExerciseCreateRequest {
  name_ko: string;
  name_en?: string | null;
  muscles: ExerciseMuscle[]; // primary 1개 이상
  bodyweight_factor?: number;
  load_multiplier?: number;
  note?: string | null;
  // §3.6 속성 — 전부 선택 사항 (PATCH에서 null = 값 비우기)
  base_movement?: string | null;
  equipment?: string | null;
  support?: string | null;
  grip?: string | null;
  angle?: string | null;
  aliases?: string | null;
}

export type ExerciseUpdateRequest = Partial<ExerciseCreateRequest>;

// DELETE /api/exercises/{id}: 세트 있으면 archive, 없으면 hard delete
export interface ExerciseDeleteResponse {
  deleted: boolean;
  archived: boolean;
}

// POST /api/exercises 409 detail — 동명 아카이브 존재 시 복원 안내 (§3.5)
export interface ArchivedConflictDetail {
  code: "archived_exists";
  exercise_id: number;
  name_ko: string;
}

export interface LastRecordSet {
  weight_kg: number;
  reps: number;
  is_warmup: boolean;
}

// GET /api/exercises/{id}/last-record — 기록 없으면 null
export interface LastRecord {
  session_id: number;
  session_date: string;
  sets: LastRecordSet[];
}

// ---------- Sets ----------

export interface SaveSetInput {
  date: string; // 'YYYY-MM-DD' — 클라이언트가 03:00 경계로 산출 (todayStr)
  exercise_id: number;
  weight_kg: number;
  reps: number;
  is_warmup?: boolean;
  new_session?: boolean;
  note?: string;
  // §3.7A 기록 의도 주동근 — 미지정/null = 종목 기본 매핑 사용
  intent_muscle?: MuscleCode | null;
  // §3.7B 세션 직접 귀속 — 지정 시 lazy 생성 생략, 그 세션에 직접 추가 (date 불일치 시 422)
  session_id?: number;
}

export interface SetCreateRequest extends SaveSetInput {
  client_id: string; // UUID — 멱등 키 (§5.4)
}

export interface OutboxItem {
  client_id: string;
  date: string;
  exercise_id: number;
  weight_kg: number;
  reps: number;
  is_warmup: boolean;
  new_session: boolean;
  note?: string;
  // §3.7 — optional: 구버전에서 큐잉된 기존 localStorage 항목에는 없다
  intent_muscle?: MuscleCode | null;
  session_id?: number;
  queued_at: string; // ISO datetime
}

export interface WorkoutSet {
  id: number;
  client_id: string | null;
  session_id: number;
  exercise_id: number;
  set_index: number;
  weight_kg: number;
  reps: number;
  is_warmup: boolean;
  note: string | null;
  created_at: string;
  volume_kg: number;
  is_weight_pr: boolean;
  is_e1rm_pr: boolean;
  // §3.7A — null = 종목 기본 매핑
  intent_muscle: MuscleCode | null;
  intent_muscle_ko: string | null;
}

export interface SetUpdateRequest {
  weight_kg?: number;
  reps?: number;
  is_warmup?: boolean;
  intent_muscle?: MuscleCode | null; // §3.7A — null 전송 = 기본으로 되돌리기
}

// ---------- Sessions ----------

export interface SessionListParams {
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

export interface SessionSummary {
  id: number;
  date: string;
  note: string | null;
  total_volume: number;
  exercise_count: number;
  set_count: number;
  // 주부위: 세션 세트들의 가중 볼륨(primary 1.0/secondary 0.5, 웜업 제외)을
  // region별 합산해 최대 region. 유효 세트 없으면 둘 다 null.
  main_region: Region | null;
  main_region_ko: string | null; // 예: '가슴'
}

export interface SessionSetRecord {
  id: number;
  client_id: string | null;
  set_index: number;
  weight_kg: number;
  reps: number;
  is_warmup: boolean;
  volume_kg: number;
  note: string | null;
  created_at: string;
  // §3.7A — null = 종목 기본 매핑
  intent_muscle: MuscleCode | null;
  intent_muscle_ko: string | null;
}

export interface SessionExerciseGroup {
  exercise_id: number;
  name_ko: string;
  sets: SessionSetRecord[];
}

// GET /api/sessions/{id} — 요약 필드(SessionSummary) + created_at + 종목별 그룹
// (서버가 exercise_id + min(set_index) 순으로 그룹핑)
export interface SessionDetail extends SessionSummary {
  created_at: string;
  exercises: SessionExerciseGroup[];
}

export interface SessionUpdateRequest {
  date?: string;
  note?: string | null;
}

// ---------- Bodyweight ----------

export interface BodyWeightEntry {
  id: number;
  date: string;
  weight_kg: number;
}

export interface BodyWeightCreateRequest {
  date: string;
  weight_kg: number;
}

// ---------- Stats (§4.2 6종) ----------

export interface RangeParams {
  from?: string;
  to?: string;
  include_warmup?: boolean;
}

export interface WeekVolumePoint {
  week_start: string; // 그 주 월요일 (§6.1)
  volume_kg: number;
}

export interface PrEvent {
  date: string;
  exercise_id: number;
  exercise_name_ko: string;
  kind: "weight" | "e1rm";
  value: number;
  weight_kg: number;
  reps: number;
}

export interface StatsSummary {
  this_week: {
    week_start: string;
    volume_kg: number;
    prev_volume_kg: number;
    change_pct: number | null; // 전주 볼륨 0이면 null
    in_progress: boolean;
    session_count: number;
    set_count: number;
    pr_count: number;
  };
  weekly_sparkline: WeekVolumePoint[]; // 최근 8주
  muscle_sets_this_week: {
    code: MuscleCode;
    name_ko: string;
    region: Region;
    weighted_sets: number;
  }[];
  recent_prs: PrEvent[]; // 최근 3건
  frequency: {
    days_this_week: number;
    weekly_streak: number; // 주 1회 이상 연속 주 수
    days_since_last: number | null;
  };
  totals: {
    tonnage_kg: number;
    session_count: number;
    set_count: number;
    rep_count: number;
  };
}

export type VolumeGranularity = "day" | "week" | "month";

export interface VolumeStatsParams extends RangeParams {
  granularity: VolumeGranularity;
}

export interface VolumePoint {
  period: string; // day: 'YYYY-MM-DD' / week: week_start / month: 'YYYY-MM'
  total_volume: number;
  per_muscle: Partial<Record<MuscleCode, number>>; // 가중 볼륨
  per_region: Partial<Record<Region, number>>;
}

export interface VolumeStats {
  granularity: VolumeGranularity;
  points: VolumePoint[];
}

export interface MusclePoint {
  code: MuscleCode;
  name_ko: string;
  region: Region;
  volume_kg: number; // 가중
  set_count: number; // 가중
}

export interface MuscleStats {
  points: MusclePoint[];
}

export interface PrRecord {
  value: number;
  date: string;
  weight_kg: number;
  reps: number;
}

export interface ExerciseStatPoint {
  date: string;
  session_id: number;
  volume_kg: number;
  top_weight_kg: number;
  e1rm: number | null;
}

export interface ExerciseStats {
  exercise_id: number;
  name_ko: string;
  points: ExerciseStatPoint[];
  weight_pr: PrRecord | null;
  e1rm_pr: PrRecord | null;
}

export interface ExercisePrs {
  exercise_id: number;
  name_ko: string;
  weight_pr: PrRecord | null;
  e1rm_pr: PrRecord | null;
}

export interface PrStats {
  records: ExercisePrs[];
  feed: PrEvent[]; // 최근 PR 피드 (하루×종목×종류당 1건)
}

// GET /api/stats/family?base_movement= — §3.6 계열 합산 (웜업 제외, e1RM은 §6.1 규칙)
export interface FamilyExercise {
  id: number;
  name_ko: string;
}

export interface FamilyPoint {
  date: string;
  total_volume: number;
  top_e1rm: number | null; // 유효 세트(1≤reps≤12, weight>0) 없으면 null
}

export interface FamilyStats {
  base_movement: string;
  exercises: FamilyExercise[]; // 참여 활성 종목 (없으면 빈 배열 + points도 빈 배열, 404 아님)
  // 합산은 아카이브 종목의 과거 세트도 포함 (다른 stats와 동일 — 분해 후
  // 옛 통합 종목을 아카이브해도 계열 차트에서 과거 볼륨이 유지된다)
  points: FamilyPoint[];
}

export interface CalendarPoint {
  date: string;
  volume_kg: number;
  session_count: number;
}

export interface CalendarStats {
  points: CalendarPoint[];
}
