// SETTING.MD §4.2·§10 전 엔드포인트 request/response 타입 — 프론트·백엔드 공용 계약 (v2)

// ---------- 부위·타겟 (§10.2) ----------

export type Region = "chest" | "back" | "shoulders" | "arms" | "legs" | "core";

export const REGION_NAMES_KO: Record<Region, string> = {
  chest: "가슴",
  back: "등",
  shoulders: "어깨",
  arms: "팔",
  legs: "하체",
  core: "코어",
};

/** 타겟 코드 — 분류는 데이터(GET /api/targets)라 문자열. 유효성은 서버가 422로 판정 */
export type TargetCode = string;

export interface Target {
  code: TargetCode;
  name_ko: string;
  region: Region;
  level: 2 | 3; // 2 = 근육, 3 = 세부 (parent_code = 근육)
  parent_code: TargetCode | null;
}

// ---------- Auth (§10.1) ----------

export interface RegisterRequest {
  username: string;
  password: string;
  display_name?: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number; // seconds
}

export interface User {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
  created_at: string;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}

// ---------- Machines (§10.4) ----------

export interface Machine {
  id: number;
  brand: string;
  model: string;
  name_ko: string;
  target: TargetCode | null;
}

export interface MachineCreateRequest {
  brand: string;
  model: string;
  name_ko?: string;
  target?: TargetCode;
}

// ---------- Exercises (§10.3) ----------

export interface Exercise {
  id: number;
  name_ko: string;
  name_en: string | null;
  base_movement: string | null; // 계열 — 같은 동작의 변형을 합산하는 기준
  tags: string[]; // 장비·자세·그립·각도 등 자유 태그 (이름과 무관)
  default_target: TargetCode; // 기본 타겟 — 세트 저장 시 미지정이면 이 값
  default_target_ko: string;
  // §11.2 보조(협응) 근육 — 간접 볼륨 후보. 기본 타겟과 같은 근육은 없다
  secondary_targets: TargetCode[];
  secondary_targets_ko: string[];
  machine_id: number | null;
  machine_name: string | null;
  bodyweight_factor: number;
  load_multiplier: number;
  is_builtin: boolean;
  is_archived: boolean;
  is_own: boolean; // 내 커스텀 종목 (수정·삭제 가능). 내장은 관리자만
  note: string | null;
  aliases: string | null; // 검색 별칭, 쉼표 구분
}

export interface ExerciseCreateRequest {
  name_ko: string;
  name_en?: string | null;
  base_movement?: string | null;
  tags?: string[];
  default_target: TargetCode;
  secondary_targets?: TargetCode[]; // ≤5, 기본 타겟과 같으면 422
  machine_id?: number | null;
  bodyweight_factor?: number;
  load_multiplier?: number;
  note?: string | null;
  aliases?: string | null;
}

export type ExerciseUpdateRequest = Partial<ExerciseCreateRequest> & { is_archived?: boolean };

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

// GET/PUT /api/favorites — 순서 있는 종목 id 목록 (§10.3 즐겨찾기)
export interface Favorites {
  exercise_ids: number[];
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
  // §10.2 세트 타겟 — 미지정/null = 종목 기본 타겟
  target?: TargetCode | null;
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
  // v1 큐 항목(intent_muscle)은 무시된다 — 서버가 종목 기본 타겟을 채운다
  target?: TargetCode | null;
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
  target: TargetCode; // 항상 존재
  target_ko: string;
}

export interface SetUpdateRequest {
  weight_kg?: number;
  reps?: number;
  is_warmup?: boolean;
  target?: TargetCode | null; // null 전송 = 종목 기본 타겟으로 되돌리기
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
  // 부위 라벨 (§10.2): 세트 타겟을 부위로 합산해 1위(+2위가 25% 이상이면 함께 "하체·등").
  // 분할표를 두지 않고 그날 수행한 운동에서 도출. 유효 세트 없으면 전부 null
  main_region: Region | null;
  main_region_ko: string | null;
  region_label: string | null;
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
  target: TargetCode;
  target_ko: string;
}

export interface SessionExerciseGroup {
  exercise_id: number;
  name_ko: string;
  default_target: TargetCode; // 종목 기본 타겟 — 세트 타겟과 다를 때만 뱃지 표시
  sets: SessionSetRecord[];
}

// GET /api/sessions/{id} — 요약 필드(SessionSummary) + created_at + 종목별 그룹
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
    code: TargetCode; // 근육(level 2) — 세부는 근육으로 합산
    name_ko: string;
    region: Region;
    set_count: number;
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
  analytics: AnalyticsGate; // §11.1 고급 분석 준비도
}

// ---------- Advanced analytics (§11) ----------

/** 훈련 주(웜업 아닌 세트가 있는 ISO 주) 수 기준 게이트. ready=false면 고급 엔드포인트는 403 */
export interface AnalyticsGate {
  ready: boolean;
  weeks_of_data: number;
  required_weeks: number;
}

/** 고급 분석 403 detail — 프론트는 잠금 카드로 바꿔 보여 준다 */
export interface InsufficientDataDetail {
  code: "insufficient_data";
  weeks_of_data: number;
  required_weeks: number;
}

export interface MuscleWeekFrequency {
  code: TargetCode | Region;
  name_ko: string;
  region: Region;
  per_week: number[]; // weeks 순서(오래된 → 이번 주)와 같은 길이 — 그 부위를 자극한 세션 수
  avg_per_week: number; // 이번 주(진행 중) 제외 평균
  days_since_last: number | null; // 한 번도 없으면 null
  neglected: boolean; // 자극한 적 있고 neglect_days 이상 지남
}

// GET /api/stats/advanced/frequency?weeks=
export interface AdvancedFrequency {
  weeks: string[]; // week_start 오래된 → 이번 주
  neglect_days: number;
  regions: MuscleWeekFrequency[];
  muscles: MuscleWeekFrequency[]; // 근육(level 2)
}

export interface TrendPoint {
  week_start: string;
  volume_kg: number;
  set_count: number;
  ma4_kg: number | null; // 이번 주 포함 4주 이동평균 (첫 훈련 주부터 4주 미만이면 null)
  acwr: number | null; // 이번 주 / 직전 4주 평균 (직전 4주가 없거나 0이면 null)
  in_progress: boolean;
}

// GET /api/stats/advanced/trend?weeks=
export interface TrendStats {
  first_week: string | null;
  acwr_warn: number; // 이 값 초과 = 급증 경고 (완료 주만 판정)
  points: TrendPoint[];
}

export interface RepMaxCell {
  reps: number;
  best_weight_kg: number | null; // 정확히 그 횟수로 든 최고 중량
  best_date: string | null;
  implied_weight_kg: number | null; // 그 횟수 이상으로 든 최고 중량 (단조 감소)
}

export interface RepPrEvent {
  date: string;
  weight_kg: number;
  reps: number;
  prev_reps: number;
}

// GET /api/stats/advanced/rep-max?exercise_id=
export interface RepMaxStats {
  exercise_id: number;
  name_ko: string;
  cells: RepMaxCell[]; // reps 1..12
  rep_prs: RepPrEvent[]; // 최신순, 최대 20
}

export interface FatiguePoint {
  ordinal: number; // 세션 내 그 종목의 n번째 워킹 세트
  sessions: number;
  avg_reps: number;
  avg_weight_kg: number;
  rel_reps: number | null; // 1세트 대비 횟수 비율 평균
}

export interface BucketShare {
  bucket: string;
  sets: number;
  share: number; // 0~1
}

// GET /api/stats/advanced/fatigue?exercise_id=&from=&to=
export interface FatigueStats {
  exercise_id: number;
  name_ko: string;
  sessions_used: number;
  points: FatiguePoint[];
  rep_ranges: BucketShare[]; // 1-5 · 6-12 · 13-20 · 21+
}

// GET /api/stats/advanced/intensity?exercise_id?&from=&to=
export interface IntensityStats {
  sets_total: number; // 강도 계산 대상 세트 (weight>0, 웜업 제외, 러닝 e1RM 존재)
  avg_intensity_pct: number | null;
  zones: BucketShare[]; // <60% · 60-70% · 70-80% · 80-90% · 90%+
  rep_ranges: BucketShare[];
}

export interface AttributionPoint {
  code: TargetCode; // 근육(level 2)
  name_ko: string;
  region: Region;
  direct_sets: number; // = /stats/muscles level 2 set_count
  indirect_sets: number; // 가중 전
  fractional_sets: number; // direct + weight × indirect
  direct_volume_kg: number;
  indirect_volume_kg: number; // 가중 전
  fractional_volume_kg: number;
}

// GET /api/stats/advanced/attribution?from=&to=&include_warmup=&indirect_weight=
export interface AttributionStats {
  indirect_weight: number;
  points: AttributionPoint[];
}

export type VolumeGranularity = "day" | "week" | "month";

export interface VolumeStatsParams extends RangeParams {
  granularity: VolumeGranularity;
}

export interface VolumePoint {
  period: string; // day: 'YYYY-MM-DD' / week: week_start / month: 'YYYY-MM'
  total_volume: number;
  per_muscle: Record<TargetCode, number>; // 근육(level 2) 코드 → 볼륨 (100% 귀속)
  per_region: Record<Region, number>;
}

export interface VolumeStats {
  granularity: VolumeGranularity;
  points: VolumePoint[];
}

// 타겟 행 전부(level 2·3). level 2 = 자기 + 세부 합산, level 3 = 자기만
export interface MusclePoint {
  code: TargetCode;
  name_ko: string;
  region: Region;
  level: 2 | 3;
  parent_code: TargetCode | null;
  volume_kg: number;
  set_count: number;
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

// ---------- Admin (§10.5, 읽기 전용) ----------

export interface AdminUser {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
  created_at: string;
  session_count: number;
  set_count: number;
  last_date: string | null;
}
