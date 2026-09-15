// fetch 래퍼 + 전 엔드포인트 typed 함수 + localStorage outbox (§5.4)

import type {
  AdminUser,
  AdvancedFrequency,
  ArchivedConflictDetail,
  AttributionStats,
  BodyWeightCreateRequest,
  BodyWeightEntry,
  CalendarStats,
  Exercise,
  ExerciseCreateRequest,
  ExerciseDeleteResponse,
  ExerciseStats,
  ExerciseUpdateRequest,
  FamilyStats,
  FriendUser,
  FriendsOut,
  FatigueStats,
  BrandCount,
  Favorites,
  InsufficientDataDetail,
  IntensityStats,
  LastRecord,
  LoginResponse,
  Machine,
  MachineCreateRequest,
  MachineSearchParams,
  MuscleStats,
  OutboxItem,
  PasswordChangeRequest,
  PrStats,
  Profile,
  ProfileUpdateRequest,
  RangeParams,
  RegisterRequest,
  RepMaxStats,
  SaveSetInput,
  SessionDetail,
  SessionListParams,
  SessionSummary,
  SessionUpdateRequest,
  SetCreateRequest,
  SetUpdateRequest,
  StatsSummary,
  Target,
  TargetCode,
  TrendStats,
  User,
  VolumeStats,
  VolumeStatsParams,
  WorkoutSet,
} from "./types";
import { todayStr } from "../utils/date";

const TOKEN_KEY = "vt_token";
const TOKEN_EXP_KEY = "vt_token_exp";
const OUTBOX_KEY = "vt_outbox";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

/** 사용자 표시용 에러 문구 — 서버 detail 문자열 > "요청 실패 (HTTP n)" > fallback(네트워크 등) */
export function apiErrorMessage(e: unknown, fallback = "요청에 실패했습니다"): string {
  if (e instanceof ApiError) {
    if (typeof e.detail === "string") return e.detail;
    return `요청 실패 (HTTP ${e.status})`;
  }
  return fallback;
}

/** POST /api/exercises의 동명 아카이브 충돌(409 + detail.code="archived_exists")이면 detail, 아니면 null */
export function archivedConflictOf(e: unknown): ArchivedConflictDetail | null {
  if (
    e instanceof ApiError &&
    e.status === 409 &&
    e.detail !== null &&
    typeof e.detail === "object" &&
    (e.detail as { code?: unknown }).code === "archived_exists"
  ) {
    return e.detail as ArchivedConflictDetail;
  }
  return null;
}

/** 고급 분석 403(detail.code="insufficient_data")이면 detail, 아니면 null (§11.1) */
export function insufficientDataOf(e: unknown): InsufficientDataDetail | null {
  if (
    e instanceof ApiError &&
    e.status === 403 &&
    e.detail !== null &&
    typeof e.detail === "object" &&
    (e.detail as { code?: unknown }).code === "insufficient_data"
  ) {
    return e.detail as InsufficientDataDetail;
  }
  return null;
}

// ---------- 토큰 ----------

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string, expiresInSec?: number): void {
  localStorage.setItem(TOKEN_KEY, token);
  if (expiresInSec != null) {
    localStorage.setItem(TOKEN_EXP_KEY, String(Date.now() + expiresInSec * 1000));
  }
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_EXP_KEY);
}

// 재로그인 유도 배너용 (§4.1: 남은 수명 7일 미만이면 안내)
export function tokenRemainingDays(): number | null {
  const raw = localStorage.getItem(TOKEN_EXP_KEY);
  if (!raw || !getToken()) return null;
  return (Number(raw) - Date.now()) / 86_400_000;
}

function redirectToLogin(): void {
  if (window.location.pathname !== "/login" && window.location.pathname !== "/register") {
    window.location.href = "/login";
  }
}

// ---------- fetch 래퍼 ----------

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined);
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
}

async function api<T>(
  path: string,
  init: RequestInit = {},
  opts: { auth?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const useAuth = opts.auth !== false;
  const token = getToken();
  if (useAuth && token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(path, { ...init, headers });

  if (res.status === 401 && useAuth) {
    clearToken();
    redirectToLogin();
    throw new ApiError(401, "unauthorized");
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body === "object" && "detail" in body) detail = body.detail;
    } catch {
      // body 없음 — statusText 유지
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

// ---------- Auth (§10.1) ----------

export async function login(username: string, password: string): Promise<LoginResponse> {
  const res = await api<LoginResponse>(
    "/api/auth/login",
    { method: "POST", body: JSON.stringify({ username, password }) },
    { auth: false },
  );
  setToken(res.access_token, res.expires_in);
  void flushOutbox(); // 재로그인 후 대기 큐 재개 (§5.4-5)
  return res;
}

export async function register(body: RegisterRequest): Promise<LoginResponse> {
  const res = await api<LoginResponse>(
    "/api/auth/register",
    { method: "POST", body: JSON.stringify(body) },
    { auth: false },
  );
  setToken(res.access_token, res.expires_in);
  return res;
}

export function fetchMe(): Promise<User> {
  return api("/api/auth/me");
}

/** 비밀번호 변경은 인증 실패(401)를 "현재 비밀번호 오류"로 보여줘야 하므로 자동 리다이렉트를 우회 */
export async function changePassword(body: PasswordChangeRequest): Promise<void> {
  const token = getToken();
  const res = await fetch("/api/auth/password", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (res.status === 204) return;
  let detail: unknown = res.statusText;
  try {
    detail = (await res.json()).detail;
  } catch {
    // body 없음
  }
  throw new ApiError(res.status, detail);
}

export function logout(): void {
  clearToken();
  redirectToLogin();
}

// ---------- Targets / Machines (§10.2, §10.4) ----------

export function fetchTargets(): Promise<Target[]> {
  return api("/api/targets");
}

/** 아카이브 검색 — 파라미터 없으면 전체(1,400+). 폼·시트는 q/brand/limit으로 좁혀 부른다. */
export function fetchMachines(params: MachineSearchParams = {}): Promise<Machine[]> {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.brand) sp.set("brand", params.brand);
  if (params.region) sp.set("region", params.region);
  if (params.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return api(`/api/machines${qs ? `?${qs}` : ""}`);
}

export function fetchMachineBrands(): Promise<BrandCount[]> {
  return api("/api/machines/brands");
}

// ---------- 내 머신 (§10.4) ----------

export function fetchMyMachines(): Promise<Machine[]> {
  return api("/api/me/machines");
}

export function addMyMachine(machineId: number): Promise<Machine[]> {
  return api(`/api/me/machines/${machineId}`, { method: "POST" });
}

export function removeMyMachine(machineId: number): Promise<Machine[]> {
  return api(`/api/me/machines/${machineId}`, { method: "DELETE" });
}

export function createMachine(body: MachineCreateRequest): Promise<Machine> {
  return api("/api/machines", { method: "POST", body: JSON.stringify(body) });
}

// ---------- Exercises ----------

export function fetchExercises(includeArchived = false): Promise<Exercise[]> {
  return api(`/api/exercises${includeArchived ? "?include_archived=true" : ""}`);
}

export function createExercise(body: ExerciseCreateRequest): Promise<Exercise> {
  return api("/api/exercises", { method: "POST", body: JSON.stringify(body) });
}

export function updateExercise(id: number, body: ExerciseUpdateRequest): Promise<Exercise> {
  return api(`/api/exercises/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteExercise(id: number): Promise<ExerciseDeleteResponse> {
  return api(`/api/exercises/${id}`, { method: "DELETE" });
}

export function restoreExercise(id: number): Promise<Exercise> {
  return api(`/api/exercises/${id}/restore`, { method: "POST" });
}

export async function fetchLastRecord(exerciseId: number): Promise<LastRecord | null> {
  try {
    return await api<LastRecord>(`/api/exercises/${exerciseId}/last-record`);
  } catch (e) {
    // 계약(types.ts): 이전 기록 없음(404) = null — React Query 재시도·에러 상태 방지
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

// ---------- Favorites (§10.3) ----------

export function fetchFavorites(): Promise<Favorites> {
  return api("/api/favorites");
}

export function addFavorite(exerciseId: number): Promise<Favorites> {
  return api(`/api/favorites/${exerciseId}`, { method: "POST" });
}

export function removeFavorite(exerciseId: number): Promise<Favorites> {
  return api(`/api/favorites/${exerciseId}`, { method: "DELETE" });
}

export function replaceFavorites(exerciseIds: number[]): Promise<Favorites> {
  return api("/api/favorites", {
    method: "PUT",
    body: JSON.stringify({ exercise_ids: exerciseIds }),
  });
}

// ---------- Outbox (§5.4) ----------

type OutboxListener = (items: OutboxItem[]) => void;
const outboxListeners = new Set<OutboxListener>();

function readOutbox(): OutboxItem[] {
  try {
    const raw = localStorage.getItem(OUTBOX_KEY);
    return raw ? (JSON.parse(raw) as OutboxItem[]) : [];
  } catch {
    return [];
  }
}

function writeOutbox(items: OutboxItem[]): void {
  localStorage.setItem(OUTBOX_KEY, JSON.stringify(items));
  for (const l of outboxListeners) l(items);
}

function removeFromOutbox(clientId: string): void {
  writeOutbox(readOutbox().filter((i) => i.client_id !== clientId));
}

export function getOutbox(): OutboxItem[] {
  return readOutbox();
}

// §10.2 소급 적용 — 아직 전송 대기(outbox) 중인 세트는 id가 없어 PATCH 불가.
// 큐 항목의 target을 직접 갱신해 flush 시 새 타겟으로 전송되게 한다.
// (한계: 바로 이 순간 POST가 진행 중인 항목은 이전 타겟으로 저장될 수 있다 — 좁은 경쟁 창)
export function updateOutboxTarget(clientIds: string[], target: TargetCode | null): void {
  const idSet = new Set(clientIds);
  const items = readOutbox();
  if (!items.some((i) => idSet.has(i.client_id))) return;
  writeOutbox(
    items.map((i) => (idSet.has(i.client_id) ? { ...i, target: target ?? undefined } : i)),
  );
}

// 전송 대기 세트 구독 (회색+스피너 표기용). 구독 즉시 현재 상태로 1회 호출.
export function subscribeOutbox(listener: OutboxListener): () => void {
  outboxListeners.add(listener);
  listener(readOutbox());
  return () => {
    outboxListeners.delete(listener);
  };
}

function genClientId(): string {
  // LAN dev(http)는 secure context가 아니라 randomUUID가 없을 수 있음
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`;
}

function postSet(item: OutboxItem): Promise<WorkoutSet> {
  const payload: SetCreateRequest = {
    client_id: item.client_id,
    date: item.date,
    exercise_id: item.exercise_id,
    weight_kg: item.weight_kg,
    reps: item.reps,
    is_warmup: item.is_warmup,
    new_session: item.new_session,
    note: item.note,
    // undefined면 JSON.stringify가 필드 자체를 생략 → 서버가 종목 기본 타겟 (v1 큐 항목 호환)
    target: item.target,
    technique: item.technique ?? null,
    session_id: item.session_id,
  };
  return api("/api/sets", { method: "POST", body: JSON.stringify(payload) });
}

// 4xx(401 제외) = 서버가 영구 거부한 항목 — 큐에 남기면 flush가 영원히 막힌다
function isPermanentReject(e: unknown): boolean {
  return e instanceof ApiError && e.status !== 401 && e.status >= 400 && e.status < 500;
}

// flush 중 영구 거부로 드롭된 세트 — silent 유실 방지용 알림 버퍼 (§5.4)
export interface FlushFailure {
  item: OutboxItem;
  detail: string;
}
const flushFailures: FlushFailure[] = [];
type FailureListener = (failures: FlushFailure[]) => void;
const failureListeners = new Set<FailureListener>();

function notifyFlushFailure(item: OutboxItem, e: unknown): void {
  const detail =
    e instanceof ApiError && typeof e.detail === "string"
      ? e.detail
      : "서버가 요청을 거부했습니다";
  flushFailures.push({ item, detail });
  for (const l of failureListeners) l([...flushFailures]);
}

// 구독 즉시 백로그 전달 — 앱 로드 flush가 UI 마운트보다 먼저 끝나도 유실 없음
export function subscribeFlushFailures(listener: FailureListener): () => void {
  failureListeners.add(listener);
  if (flushFailures.length > 0) listener([...flushFailures]);
  return () => {
    failureListeners.delete(listener);
  };
}

export function dismissFlushFailures(): void {
  flushFailures.length = 0;
  for (const l of failureListeners) l([]);
}

let flushPromise: Promise<void> | null = null;

// 진행 중이면 그 Promise를 반환 — 호출부가 flush 완료를 기다릴 수 있어 순서 역전 방지
export function flushOutbox(): Promise<void> {
  if (!getToken()) return Promise.resolve();
  if (flushPromise) return flushPromise;
  flushPromise = (async () => {
    try {
      for (;;) {
        const [item] = readOutbox(); // 매회 재조회 — flush 중 추가된 항목도 순서대로 처리
        if (!item) return;
        try {
          await postSet(item); // client_id 멱등 — 재전송 안전
          removeFromOutbox(item.client_id);
        } catch (e) {
          if (isPermanentReject(e)) {
            notifyFlushFailure(item, e);
            removeFromOutbox(item.client_id);
            continue;
          }
          return; // 401·네트워크·5xx: 큐 보존하고 중단 (§5.4-5)
        }
      }
    } finally {
      flushPromise = null;
    }
  })();
  return flushPromise;
}

// 세트 저장 — outbox 선기록 후 전송. 반환 null = 오프라인 큐 대기(나중에 flush로 동기화).
export async function saveSet(input: SaveSetInput): Promise<WorkoutSet | null> {
  const item: OutboxItem = {
    client_id: genClientId(),
    date: input.date,
    exercise_id: input.exercise_id,
    weight_kg: input.weight_kg,
    reps: input.reps,
    is_warmup: input.is_warmup ?? false,
    new_session: input.new_session ?? false,
    note: input.note,
    target: input.target,
    technique: input.technique ?? null,
    session_id: input.session_id,
    queued_at: new Date().toISOString(),
  };
  writeOutbox([...readOutbox(), item]);
  try {
    if (readOutbox().length > 1) {
      await flushOutbox(); // 밀린 항목 먼저 — set_index 순서 보존
      // flush가 중단됐고 내 앞에 미전송 항목이 남았으면 직접 전송하지 않는다 (순서 역전 방지)
      const pos = readOutbox().findIndex((i) => i.client_id === item.client_id);
      if (pos > 0) return null;
    }
    const saved = await postSet(item); // flush가 이미 보냈어도 멱등이라 안전
    removeFromOutbox(item.client_id);
    return saved;
  } catch (e) {
    if (isPermanentReject(e)) {
      removeFromOutbox(item.client_id);
      throw e; // validation 오류는 호출부가 사용자에게 보여준다
    }
    return null; // 오프라인·서버 다운·401: 큐 보존
  }
}

// ---------- Sets / Sessions / Bodyweight ----------

export function updateSet(id: number, body: SetUpdateRequest): Promise<WorkoutSet> {
  return api(`/api/sets/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteSet(id: number): Promise<void> {
  return api(`/api/sets/${id}`, { method: "DELETE" });
}

export function fetchSessions(params: SessionListParams = {}): Promise<SessionSummary[]> {
  return api(`/api/sessions${qs({ ...params })}`);
}

export function fetchSession(id: number, userId?: number): Promise<SessionDetail> {
  return api(`/api/sessions/${id}${qs({ user_id: userId })}`);
}

export function updateSession(id: number, body: SessionUpdateRequest): Promise<SessionSummary> {
  return api(`/api/sessions/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteSession(id: number): Promise<void> {
  return api(`/api/sessions/${id}`, { method: "DELETE" });
}

export function fetchBodyweight(limit?: number, userId?: number): Promise<BodyWeightEntry[]> {
  return api(`/api/bodyweight${qs({ limit, user_id: userId })}`);
}

export function saveBodyweight(body: BodyWeightCreateRequest): Promise<BodyWeightEntry> {
  return api("/api/bodyweight", { method: "POST", body: JSON.stringify(body) });
}

// ---------- Stats ----------

// 조회 함수의 userId(§13): 친구의 데이터를 볼 때 user_id로 붙는다. 내 것이면 undefined.
export function fetchStatsSummary(userId?: number): Promise<StatsSummary> {
  return api(`/api/stats/summary${qs({ user_id: userId })}`);
}

export function fetchStatsVolume(params: VolumeStatsParams): Promise<VolumeStats> {
  return api(`/api/stats/volume${qs({ ...params })}`);
}

export function fetchStatsMuscles(params: RangeParams = {}): Promise<MuscleStats> {
  return api(`/api/stats/muscles${qs({ ...params })}`);
}

export function fetchStatsExercise(id: number, params: RangeParams = {}): Promise<ExerciseStats> {
  return api(`/api/stats/exercises/${id}${qs({ ...params })}`);
}

export function fetchStatsPrs(userId?: number): Promise<PrStats> {
  return api(`/api/stats/prs${qs({ user_id: userId })}`);
}

// §3.6 계열 합산 — 같은 base_movement 종목들의 날짜별 합산 볼륨 + 최고 e1RM
export function fetchFamily(baseMovement: string, userId?: number): Promise<FamilyStats> {
  return api(`/api/stats/family${qs({ base_movement: baseMovement, user_id: userId })}`);
}

export function fetchStatsCalendar(months = 6, userId?: number): Promise<CalendarStats> {
  return api(`/api/stats/calendar${qs({ months, user_id: userId })}`);
}

// ---------- Advanced analytics (§11) — 4주 미만이면 403 insufficient_data ----------

export function fetchAdvancedFrequency(weeks = 8, userId?: number): Promise<AdvancedFrequency> {
  return api(`/api/stats/advanced/frequency${qs({ weeks, user_id: userId })}`);
}

export function fetchAdvancedTrend(weeks = 16, userId?: number): Promise<TrendStats> {
  return api(`/api/stats/advanced/trend${qs({ weeks, user_id: userId })}`);
}

export function fetchRepMax(exerciseId: number, userId?: number): Promise<RepMaxStats> {
  return api(`/api/stats/advanced/rep-max${qs({ exercise_id: exerciseId, user_id: userId })}`);
}

export function fetchFatigue(
  exerciseId: number,
  params: { from?: string; to?: string; user_id?: number } = {},
): Promise<FatigueStats> {
  return api(`/api/stats/advanced/fatigue${qs({ exercise_id: exerciseId, ...params })}`);
}

export function fetchIntensity(
  params: { exercise_id?: number; from?: string; to?: string; user_id?: number } = {},
): Promise<IntensityStats> {
  return api(`/api/stats/advanced/intensity${qs({ ...params })}`);
}

export function fetchAttribution(
  params: RangeParams & { indirect_weight?: number } = {},
): Promise<AttributionStats> {
  return api(`/api/stats/advanced/attribution${qs({ ...params })}`);
}

// ---------- 프로필·친구 (§13) ----------

export function fetchProfile(username: string): Promise<Profile> {
  return api(`/api/profile/${encodeURIComponent(username)}`);
}

export function updateProfile(body: ProfileUpdateRequest): Promise<User> {
  return api("/api/me/profile", { method: "PATCH", body: JSON.stringify(body) });
}

export function searchUsers(q: string): Promise<FriendUser[]> {
  return api(`/api/users/search${qs({ q })}`);
}

export function fetchFriends(): Promise<FriendsOut> {
  return api("/api/friends");
}

export function requestFriend(username: string): Promise<FriendsOut> {
  return api("/api/friends/requests", { method: "POST", body: JSON.stringify({ username }) });
}

export function acceptFriendRequest(requestId: number): Promise<FriendsOut> {
  return api(`/api/friends/requests/${requestId}/accept`, { method: "POST" });
}

export function declineFriendRequest(requestId: number): Promise<FriendsOut> {
  return api(`/api/friends/requests/${requestId}/decline`, { method: "POST" });
}

export function removeFriend(userId: number): Promise<FriendsOut> {
  return api(`/api/friends/${userId}`, { method: "DELETE" });
}

// ---------- Admin (§10.5) ----------

export function fetchAdminUsers(): Promise<AdminUser[]> {
  return api("/api/admin/users");
}

export function fetchAdminUserSessions(
  userId: number,
  params: SessionListParams = {},
): Promise<SessionSummary[]> {
  return api(`/api/admin/users/${userId}/sessions${qs({ ...params })}`);
}

export function fetchAdminUserSession(userId: number, sessionId: number): Promise<SessionDetail> {
  return api(`/api/admin/users/${userId}/sessions/${sessionId}`);
}

export function fetchAdminUserBodyweight(userId: number): Promise<BodyWeightEntry[]> {
  return api(`/api/admin/users/${userId}/bodyweight`);
}

// ---------- Export ----------

export async function downloadExport(kind: "db" | "csv"): Promise<void> {
  const token = getToken();
  const res = await fetch(`/api/export/${kind}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (res.status === 401) {
    clearToken();
    redirectToLogin();
    throw new ApiError(401, "unauthorized");
  }
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download =
    kind === "db" ? `app-${todayStr().replaceAll("-", "")}.db` : `sets-${todayStr()}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ---------- flush 트리거: 앱 로드 시 + online 복귀 시 (§5.4-1) ----------

window.addEventListener("online", () => {
  void flushOutbox();
});
void flushOutbox();
