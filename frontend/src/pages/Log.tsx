import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiErrorMessage,
  deleteSet,
  fetchBodyweight,
  fetchExercises,
  fetchLastRecord,
  fetchSession,
  fetchSessions,
  getOutbox,
  saveBodyweight,
  saveSet,
  subscribeOutbox,
  updateOutboxTarget,
  updateSet,
} from "../api/client";
import type {
  Exercise,
  OutboxItem,
  SessionDetail,
  TargetCode,
  WorkoutSet,
} from "../api/types";
import type { Technique } from "../api/types";
import { useTargets } from "../hooks/useTargets";
import { useAppStore } from "../store";
import { useResolvedTheme } from "../theme";
import { WEEKDAYS_KO, formatShortDate, parseDateStr, todayStr } from "../utils/date";
import { fmtClock, fmtInt, fmtWeight } from "../utils/format";
import { validateSetInput } from "../utils/setInput";
import Button from "../components/Button";
import Card from "../components/Card";
import DashedAddButton from "../components/DashedAddButton";
import FlushFailuresBanner from "../components/FlushFailuresBanner";
import Modal from "../components/Modal";
import Spinner from "../components/Spinner";
import Stepper from "../components/Stepper";
import ExercisePicker from "../components/exercise-picker/ExercisePicker";
import { pushRecent } from "../components/exercise-picker/recentExercises";
import TargetBackfillModal from "../components/target/TargetBackfillModal";
import TargetChipButton from "../components/target/TargetChipButton";
import TechniqueChip, { TechniqueBadge } from "../components/TechniqueChip";
import TargetSheet from "../components/target/TargetSheet";
import { useTargetBackfill } from "../components/target/useTargetBackfill";

function parseTs(s: string): number {
  const iso = s.includes("T") ? s : s.replace(" ", "T") + "Z";
  const t = Date.parse(iso);
  return Number.isNaN(t) ? Date.now() : t;
}

const WEEKDAYS_EN = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

/** 다크 IRON 헤더 날짜: "07.21" */
function headerDateIron(dateStr: string): string {
  const d = parseDateStr(dateStr);
  return `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

/** 라이트 FRESH 헤더 날짜: "7월 21일 (화)" */
function headerDateFresh(dateStr: string): string {
  const d = parseDateStr(dateStr);
  return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEKDAYS_KO[d.getDay()]})`;
}

function weekdayEn(dateStr: string): string {
  return WEEKDAYS_EN[parseDateStr(dateStr).getDay()];
}

function setLabel(weight: number, reps: number, warmup: boolean): string {
  return `${warmup ? "W " : ""}${fmtWeight(weight)}×${reps}`;
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

interface LSet {
  key: string;
  id: number | null;
  client_id: string | null;
  weight_kg: number;
  reps: number;
  is_warmup: boolean;
  volume_kg: number | null;
  target: TargetCode; // §10.2 세트 타겟 (전송 대기 세트는 카드 타겟 또는 종목 기본)
  technique: Technique | null; // §14 운동 방식
  created_ms: number;
  pending: boolean;
  prW: boolean;
  prE: boolean;
}

interface LGroup {
  exercise_id: number;
  name_ko: string;
  default_target: TargetCode;
  sets: LSet[];
}

// §10.2 소급 적용 대상 — ids = 저장된 세트(PATCH), clientIds = 전송 대기(outbox) 세트(큐 직접 갱신)
interface TargetBackfillTarget {
  code: TargetCode;
  ids: number[];
  clientIds: string[];
}

/* 시안에 없는 기존 요소 — 퀵칩과 같은 필/칩 톤으로 배치 */
function WarmupToggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={on}
      className={`touch-target rounded-chip border px-4 text-xs font-semibold ${
        on ? "border-accent/40 bg-accent-glow text-accent" : "border-line text-muted"
      }`}
    >
      웜업
    </button>
  );
}

function SetEditor({
  set: s,
  defaultTarget,
  weightStep,
  onSaved,
  onDeleted,
  onCancel,
}: {
  set: LSet;
  defaultTarget: TargetCode;
  weightStep: number;
  onSaved: (updated: WorkoutSet) => void;
  onDeleted: () => void;
  onCancel: () => void;
}) {
  const [w, setW] = useState(s.weight_kg);
  const [r, setR] = useState(s.reps);
  const [warm, setWarm] = useState(s.is_warmup);
  const [technique, setTechnique] = useState<Technique | null>(s.technique);
  const [target, setTarget] = useState<TargetCode>(s.target);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    const v = validateSetInput(w, r);
    if (v) {
      setErr(v);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      onSaved(await updateSet(s.id as number, { weight_kg: w, reps: r, is_warmup: warm, target, technique }));
    } catch (e) {
      setErr(apiErrorMessage(e));
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("이 세트를 삭제할까요?")) return;
    setBusy(true);
    setErr(null);
    try {
      await deleteSet(s.id as number);
      onDeleted();
    } catch (e) {
      setErr(apiErrorMessage(e));
      setBusy(false);
    }
  };

  return (
    <div className="rounded-sub bg-well p-3 dark:bg-surface-sunken">
      {/* 모바일 가로 넘침 방지 — ± 버튼(44px 고정)×4가 한 행에 안 들어가므로 스테퍼는
          세로 스택, 웜업 토글·타겟 칩은 별도 행 배치 */}
      <div className="flex flex-col gap-2">
        <Stepper label="중량(kg)" value={w} step={weightStep} onChange={setW} min={0} max={500} />
        <Stepper
          label="횟수"
          value={r}
          step={1}
          onChange={(v) => setR(Math.round(v))}
          min={1}
          max={100}
          inputMode="numeric"
        />
      </div>
      <div className="mt-3 flex items-center gap-3">
        <WarmupToggle on={warm} onToggle={() => setWarm(!warm)} />
        <TechniqueChip value={technique} onChange={setTechnique} />
        {/* §10.2 개별 세트 타겟 변경 */}
        <TargetChipButton value={target} defaultCode={defaultTarget} onClick={() => setSheetOpen(true)} />
      </div>
      {err ? <p className="mt-2 text-center text-sm text-danger">{err}</p> : null}
      <div className="mt-3 flex gap-2">
        <Button variant="danger" onClick={() => void remove()} disabled={busy}>
          삭제
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy} className="ml-auto">
          취소
        </Button>
        <Button onClick={() => void save()} disabled={busy}>
          저장
        </Button>
      </div>
      <TargetSheet
        open={sheetOpen}
        value={target}
        defaultCode={defaultTarget}
        onClose={() => setSheetOpen(false)}
        onSelect={(code) => {
          setTarget(code);
          setSheetOpen(false);
        }}
      />
    </div>
  );
}

function BodyweightModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setValue("");
      setErr(null);
      setBusy(false);
    }
  }, [open]);

  const save = async () => {
    const n = parseFloat(value);
    if (Number.isNaN(n) || n <= 0 || n > 300) {
      setErr("체중을 올바르게 입력하세요 (kg)");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await saveBodyweight({ date: todayStr(), weight_kg: Math.round(n * 10) / 10 });
      onSaved();
    } catch (e) {
      setErr(apiErrorMessage(e));
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="체중 입력">
      <p className="text-sm text-muted">
        맨몸 운동의 볼륨 계산에 체중이 사용됩니다. 현재 체중을 입력해 주세요.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <input
          type="text"
          inputMode="decimal"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="예: 72.5"
          className="min-h-12 w-full rounded-xl border border-line bg-bg px-4 text-lg"
        />
        <span className="text-muted">kg</span>
      </div>
      {err ? <p className="mt-2 text-sm text-danger">{err}</p> : null}
      <div className="mt-4 flex gap-2">
        <Button variant="ghost" onClick={onClose} disabled={busy}>
          나중에
        </Button>
        <Button full onClick={() => void save()} disabled={busy}>
          저장
        </Button>
      </div>
    </Modal>
  );
}

export default function Log() {
  const queryClient = useQueryClient();
  const {
    activeExerciseId,
    stepper,
    restStartedAt,
    weightStep,
    restTargetSeconds,
    targets,
    setActiveExercise,
    setStepper,
    setTarget,
    startRest,
    endSession,
  } = useAppStore();
  const { nameOf } = useTargets();

  const [serverSession, setServerSession] = useState<SessionDetail | null>(null);
  const [savedSets, setSavedSets] = useState<WorkoutSet[]>([]);
  const [outbox, setOutbox] = useState<OutboxItem[]>(() => getOutbox());
  const [bwCheckPending, setBwCheckPending] = useState(false);
  const [boundary, setBoundary] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [bwModalOpen, setBwModalOpen] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [targetSheetOpen, setTargetSheetOpen] = useState(false);

  const boundaryRef = useRef(false);
  const needNewSessionRef = useRef(false);
  const postBoundaryIdsRef = useRef<Set<string>>(new Set());
  const newSessionIdRef = useRef<number | null>(null);
  const prFlagsRef = useRef(new Map<string, { w: boolean; e: boolean }>());
  const awaitLastRecordRef = useRef<number | null>(null);
  const bwPromptedRef = useRef(false);
  const prevOutboxLen = useRef(0);

  const today = todayStr();
  const now = useNow(restStartedAt != null);
  // 스테퍼 라벨 등 토큰으로 표현 불가능한 테마별 문구 분기용
  const isDark = useResolvedTheme() === "dark";

  const refreshSession = useCallback(async () => {
    try {
      const day = todayStr();
      const sessions = await fetchSessions({ from: day, to: day, limit: 10 });
      if (sessions.length === 0) {
        if (!boundaryRef.current) setServerSession(null);
        return;
      }
      const latest = sessions.reduce((a, b) => (b.id > a.id ? b : a));
      const detail = await fetchSession(latest.id);
      const serverClientIds = new Set<string>();
      for (const g of detail.exercises)
        for (const s of g.sets) if (s.client_id) serverClientIds.add(s.client_id);
      if (boundaryRef.current) {
        const isNew =
          detail.id === newSessionIdRef.current ||
          [...postBoundaryIdsRef.current].some((cid) => serverClientIds.has(cid));
        if (!isNew) return;
        boundaryRef.current = false;
        setBoundary(false);
      }
      setServerSession(detail);
      setSavedSets((prev) =>
        prev.filter(
          (s) =>
            s.session_id === detail.id &&
            !(s.client_id != null && serverClientIds.has(s.client_id)) &&
            !detail.exercises.some((g) => g.sets.some((x) => x.id === s.id)),
        ),
      );
    } catch {
      // 오프라인 등 — 로컬 표시 유지 (§5.4)
    }
  }, []);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  useEffect(
    () =>
      subscribeOutbox((items) => {
        setOutbox(items);
        // 항목이 줄어들 때마다 재조회 — flush 부분 성공분도 즉시 화면 반영 (§5.4)
        if (items.length < prevOutboxLen.current) void refreshSession();
        prevOutboxLen.current = items.length;
      }),
    [refreshSession],
  );

  // §10.2 carry-over 금지 — 앱을 켜 둔 채 03:00 경계를 지나면 날짜가 바뀌어
  // 다음 저장이 새 lazy 세션을 만든다. 이전 날짜에 설정된 카드 타겟은 폐기한다.
  useEffect(() => {
    const st = useAppStore.getState();
    if (st.targetsDate != null && st.targetsDate !== todayStr()) st.clearTargets();
  }, []);

  const exercisesQuery = useQuery({ queryKey: ["exercises"], queryFn: () => fetchExercises() });
  const exercises = useMemo(() => exercisesQuery.data ?? [], [exercisesQuery.data]);
  const exMap = useMemo(() => new Map(exercises.map((e) => [e.id, e])), [exercises]);

  const bwQuery = useQuery({ queryKey: ["bodyweight"], queryFn: () => fetchBodyweight(1) });
  const latestBw = bwQuery.data?.[0]?.weight_kg ?? 0;

  const lastRecordQuery = useQuery({
    queryKey: ["last-record", activeExerciseId],
    queryFn: () => fetchLastRecord(activeExerciseId as number),
    enabled: activeExerciseId != null,
  });

  useEffect(() => {
    if (activeExerciseId == null || awaitLastRecordRef.current !== activeExerciseId) return;
    if (!lastRecordQuery.isSuccess) return;
    awaitLastRecordRef.current = null;
    const lr = lastRecordQuery.data;
    if (lr && lr.sets.length > 0) {
      const last = lr.sets[lr.sets.length - 1];
      setStepper({ weight_kg: last.weight_kg, reps: last.reps });
    }
  }, [activeExerciseId, lastRecordQuery.isSuccess, lastRecordQuery.data, setStepper]);

  const estVolume = useCallback(
    (exId: number, w: number, reps: number) => {
      const ex = exMap.get(exId);
      return (w + (ex?.bodyweight_factor ?? 0) * latestBw) * (ex?.load_multiplier ?? 1) * reps;
    },
    [exMap, latestBw],
  );

  const activeExercise = activeExerciseId != null ? (exMap.get(activeExerciseId) ?? null) : null;
  // §10.2 활성 카드의 sticky 타겟 — 미지정이면 종목 기본 타겟
  const activeDefaultTarget = activeExercise?.default_target ?? "";
  const activeTarget: TargetCode =
    (activeExerciseId != null ? targets[activeExerciseId] : undefined) ?? activeDefaultTarget;

  const groups = useMemo<LGroup[]>(() => {
    const list: LGroup[] = [];
    const byEx = new Map<number, LGroup>();
    const seen = new Set<string>();
    const groupFor = (exId: number, name?: string, defaultTarget?: TargetCode) => {
      let g = byEx.get(exId);
      if (!g) {
        const ex = exMap.get(exId);
        g = {
          exercise_id: exId,
          name_ko: name ?? ex?.name_ko ?? `종목 ${exId}`,
          default_target: defaultTarget ?? ex?.default_target ?? "",
          sets: [],
        };
        byEx.set(exId, g);
        list.push(g);
      }
      return g;
    };

    if (!boundary && serverSession) {
      for (const g of serverSession.exercises) {
        const lg = groupFor(g.exercise_id, g.name_ko, g.default_target);
        for (const s of g.sets) {
          if (s.client_id) seen.add(s.client_id);
          const pr = s.client_id ? prFlagsRef.current.get(s.client_id) : undefined;
          lg.sets.push({
            key: `srv-${s.id}`,
            id: s.id,
            client_id: s.client_id,
            weight_kg: s.weight_kg,
            reps: s.reps,
            is_warmup: s.is_warmup,
            volume_kg: s.volume_kg,
            target: s.target,
            technique: s.technique ?? null,
            created_ms: parseTs(s.created_at),
            pending: false,
            prW: pr?.w ?? false,
            prE: pr?.e ?? false,
          });
        }
      }
    }

    for (const s of savedSets) {
      if (s.client_id && seen.has(s.client_id)) continue;
      if (boundary && !(s.client_id != null && postBoundaryIdsRef.current.has(s.client_id))) continue;
      if (!boundary && serverSession && s.session_id !== serverSession.id) continue;
      if (s.client_id) seen.add(s.client_id);
      groupFor(s.exercise_id).sets.push({
        key: s.client_id ?? `srv-${s.id}`,
        id: s.id,
        client_id: s.client_id,
        weight_kg: s.weight_kg,
        reps: s.reps,
        is_warmup: s.is_warmup,
        volume_kg: s.volume_kg,
        target: s.target,
        technique: s.technique ?? null,
        created_ms: parseTs(s.created_at),
        pending: false,
        prW: s.is_weight_pr,
        prE: s.is_e1rm_pr,
      });
    }

    // 날짜와 무관하게 전부 표기 (§5.4-3) — 03:00 경계를 넘긴 대기 세트도 보여야 한다
    for (const o of outbox) {
      if (seen.has(o.client_id)) continue;
      if (boundary && !postBoundaryIdsRef.current.has(o.client_id)) continue;
      seen.add(o.client_id);
      const g = groupFor(o.exercise_id);
      g.sets.push({
        key: o.client_id,
        id: null,
        client_id: o.client_id,
        weight_kg: o.weight_kg,
        reps: o.reps,
        is_warmup: o.is_warmup,
        volume_kg: null,
        target: o.target ?? g.default_target,
        technique: o.technique ?? null,
        created_ms: parseTs(o.queued_at),
        pending: true,
        prW: false,
        prE: false,
      });
    }
    return list;
  }, [boundary, serverSession, savedSets, outbox, exMap]);

  const allSets = useMemo(() => groups.flatMap((g) => g.sets), [groups]);
  const hasSets = allSets.length > 0;

  const totalVolume = useMemo(
    () =>
      groups.reduce(
        (sum, g) =>
          sum +
          g.sets.reduce(
            (s2, s) =>
              s.is_warmup ? s2 : s2 + (s.volume_kg ?? estVolume(g.exercise_id, s.weight_kg, s.reps)),
            0,
          ),
        0,
      ),
    [groups, estVolume],
  );

  const elapsedMin = useMemo(() => {
    if (allSets.length < 2) return 0;
    const times = allSets.map((s) => s.created_ms);
    return Math.floor((Math.max(...times) - Math.min(...times)) / 60_000);
  }, [allSets]);

  const activeGroup = groups.find((g) => g.exercise_id === activeExerciseId) ?? null;

  const selectExercise = (ex: Exercise) => {
    // 최근 사용 push는 ExercisePicker가 내부에서 수행
    setPickerOpen(false);
    setEditingKey(null);
    setInputError(null);
    setActiveExercise(ex.id);
    const g = groups.find((x) => x.exercise_id === ex.id);
    const last = g?.sets[g.sets.length - 1];
    if (last) {
      setStepper({ weight_kg: last.weight_kg, reps: last.reps, is_warmup: false, technique: null });
      awaitLastRecordRef.current = null;
    } else {
      // 프리필 ③ 빈 값 (§5.3) — 임의 기본 중량을 넣지 않는다
      setStepper({ weight_kg: 0, reps: 8, is_warmup: false, technique: null });
      awaitLastRecordRef.current = ex.id;
    }
    if (ex.bodyweight_factor > 0 && !bwPromptedRef.current) {
      if (bwQuery.isError) void bwQuery.refetch();
      setBwCheckPending(true); // 조회 완료 후 effect에서 판정 — 로딩 레이스 방지 (§5.6)
    }
  };

  useEffect(() => {
    if (!bwCheckPending || !bwQuery.isSuccess) return;
    setBwCheckPending(false);
    if (bwQuery.data.length === 0 && !bwPromptedRef.current) {
      bwPromptedRef.current = true;
      setBwModalOpen(true);
    }
  }, [bwCheckPending, bwQuery.isSuccess, bwQuery.data]);

  const openGroup = (g: LGroup) => {
    setEditingKey(null);
    setInputError(null);
    setActiveExercise(g.exercise_id);
    pushRecent(g.exercise_id);
    awaitLastRecordRef.current = null;
    const last = g.sets[g.sets.length - 1];
    if (last) setStepper({ weight_kg: last.weight_kg, reps: last.reps, is_warmup: false, technique: null });
  };

  const completeSet = async () => {
    if (activeExerciseId == null) return;
    const { weight_kg, reps, is_warmup, technique } = stepper;
    const err = validateSetInput(weight_kg, reps);
    if (err) {
      setInputError(err);
      return;
    }
    setInputError(null);
    awaitLastRecordRef.current = null;
    const isNewSession = needNewSessionRef.current;
    needNewSessionRef.current = false;
    // §10.2 carry-over 금지 — 03:00 경계를 넘겨 날짜가 바뀌었으면 새 세션이므로
    // 이전 날짜의 카드 타겟을 폐기하고 종목 기본으로 저장한다
    const st = useAppStore.getState();
    if (st.targetsDate != null && st.targetsDate !== todayStr()) st.clearTargets();
    const before = new Set(getOutbox().map((i) => i.client_id));
    const promise = saveSet({
      date: todayStr(),
      exercise_id: activeExerciseId,
      weight_kg,
      reps,
      is_warmup,
      technique,
      new_session: isNewSession || undefined,
      // §10.2 카드 sticky 타겟 — 미지정이면 필드 자체를 생략 (종목 기본 타겟)
      target: useAppStore.getState().targets[activeExerciseId],
    });
    const mine = getOutbox().find((i) => !before.has(i.client_id));
    if (mine && boundaryRef.current) postBoundaryIdsRef.current.add(mine.client_id);
    startRest();
    try {
      const saved = await promise;
      if (saved) {
        if (saved.client_id) {
          prFlagsRef.current.set(saved.client_id, { w: saved.is_weight_pr, e: saved.is_e1rm_pr });
        }
        if (isNewSession) newSessionIdRef.current = saved.session_id;
        setSavedSets((prev) => [...prev, saved]);
        if (isNewSession) void refreshSession();
      }
    } catch (e) {
      if (isNewSession) needNewSessionRef.current = true;
      setInputError(apiErrorMessage(e));
    }
  };

  const finishSession = () => {
    endSession();
    setEditingKey(null);
    setInputError(null);
  };

  const startNewSession = () => {
    endSession();
    setEditingKey(null);
    setInputError(null);
    needNewSessionRef.current = true;
    postBoundaryIdsRef.current = new Set();
    newSessionIdRef.current = null;
    boundaryRef.current = true;
    setBoundary(true);
  };

  // PATCH 응답을 로컬 두 소스(savedSets·serverSession)에 반영 — 편집 종료와 분리 (타겟 일괄 적용에서도 사용)
  const mergeUpdatedSet = useCallback((updated: WorkoutSet) => {
    setSavedSets((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    setServerSession((prev) =>
      prev
        ? {
            ...prev,
            exercises: prev.exercises.map((g) => ({
              ...g,
              sets: g.sets.map((x) =>
                x.id === updated.id
                  ? {
                      ...x,
                      weight_kg: updated.weight_kg,
                      reps: updated.reps,
                      is_warmup: updated.is_warmup,
                      volume_kg: updated.volume_kg,
                      target: updated.target,
                      target_ko: updated.target_ko,
                      technique: updated.technique,
                    }
                  : x,
              ),
            })),
          }
        : prev,
    );
  }, []);

  const applySetUpdate = (updated: WorkoutSet) => {
    mergeUpdatedSet(updated);
    setEditingKey(null);
  };

  // §10.2 소급 적용 실행 — 저장된 세트는 PATCH, 전송 대기(outbox) 세트는 id가 없어
  // PATCH 불가하므로 localStorage 큐의 target을 직접 갱신 (소급 완전성).
  // 설정(물어보기/항상 적용/적용 안 함) 분기와 확인 다이얼로그는 useTargetBackfill이 담당.
  const backfill = useTargetBackfill(async ({ code, ids, clientIds }: TargetBackfillTarget) => {
    setInputError(null);
    if (clientIds.length > 0) updateOutboxTarget(clientIds, code);
    try {
      for (const id of ids) {
        mergeUpdatedSet(await updateSet(id, { target: code }));
      }
    } catch (e) {
      setInputError(apiErrorMessage(e));
    }
  });

  // §10.2 타겟 선택 (카드 단위 sticky): 이후 저장 세트에 자동 적용.
  // 이미 저장된 이 세션 같은 종목 세트는 설정에 따라 소급 (backfill.request).
  const applyTarget = async (code: TargetCode) => {
    setTargetSheetOpen(false);
    if (activeExerciseId == null) return;
    if (code === activeTarget) return;
    setTarget(activeExerciseId, code === activeDefaultTarget ? null : code);
    const g = groups.find((x) => x.exercise_id === activeExerciseId);
    const changed = (g?.sets ?? []).filter((s) => s.target !== code);
    const ids = changed.filter((s) => s.id != null).map((s) => s.id as number);
    const clientIds = changed
      .filter((s) => s.id == null && s.client_id != null)
      .map((s) => s.client_id as string);
    if (ids.length === 0 && clientIds.length === 0) return;
    await backfill.request({ code, ids, clientIds });
  };

  const applySetDelete = (id: number) => {
    setSavedSets((prev) => prev.filter((s) => s.id !== id));
    setServerSession((prev) =>
      prev
        ? {
            ...prev,
            exercises: prev.exercises
              .map((g) => ({ ...g, sets: g.sets.filter((x) => x.id !== id) }))
              .filter((g) => g.sets.length > 0),
          }
        : prev,
    );
    setEditingKey(null);
  };

  const renderSetRow = (g: LGroup, s: LSet, i: number) => {
    if (editingKey === s.key && s.id != null) {
      return (
        <li key={s.key}>
          <SetEditor
            set={s}
            defaultTarget={g.default_target}
            weightStep={weightStep}
            onSaved={applySetUpdate}
            onDeleted={() => applySetDelete(s.id as number)}
            onCancel={() => setEditingKey(null)}
          />
        </li>
      );
    }
    return (
      <li key={s.key}>
        <button
          type="button"
          disabled={s.pending}
          onClick={() => {
            if (s.id != null) setEditingKey(s.key);
          }}
          className={`flex min-h-11 w-full items-center gap-2.5 rounded-row bg-well px-3 py-2 text-left dark:bg-surface-sunken ${
            s.pending ? "opacity-60" : "active:brightness-[0.97] dark:active:brightness-110"
          }`}
        >
          {/* 세트 번호: 라이트 = 원형 accent 체크뱃지 / 다크 = muted 숫자 */}
          <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-on-accent dark:hidden">
            ✓
          </span>
          <span className="hidden w-4 shrink-0 text-center font-numeric text-xs text-muted dark:inline">
            {i + 1}
          </span>
          <span
            className={`font-numeric text-[15px] font-semibold ${s.is_warmup ? "text-muted" : "text-text"}`}
          >
            {fmtWeight(s.weight_kg)} × {s.reps}
          </span>
          {s.is_warmup ? (
            <span className="shrink-0 rounded-tag bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">
              웜업
            </span>
          ) : null}
          <TechniqueBadge technique={s.technique} />
          {/* §10.2 종목 기본과 다른 타겟만 뱃지 — 기본이면 노이즈 없음 */}
          {s.target !== g.default_target ? (
            <span className="shrink-0 rounded-tag bg-accent-glow px-1.5 py-0.5 text-[10px] font-semibold text-accent">
              {nameOf(s.target)}
            </span>
          ) : null}
          {s.prW || s.prE ? (
            <span className="shrink-0 rounded-tag bg-pr px-1.5 py-0.5 text-[9px] font-extrabold text-on-pr transition-opacity duration-500 starting:opacity-0 dark:text-[10px] dark:font-bold">
              PR
            </span>
          ) : null}
          <span className="ml-auto flex shrink-0 items-center font-numeric text-xs text-muted">
            {s.pending ? (
              <Spinner size="sm" />
            ) : s.volume_kg != null ? (
              <>
                {fmtInt(s.volume_kg)}
                <span className="dark:hidden">&nbsp;kg</span>
              </>
            ) : null}
          </span>
        </button>
      </li>
    );
  };

  const renderCollapsedCard = (g: LGroup) => (
    <Card key={g.exercise_id} variant="sunken" onClick={() => openGroup(g)}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="truncate font-semibold">{g.name_ko}</h2>
        <span className="flex shrink-0 items-center gap-2">
          {g.sets.some((s) => s.pending) ? <Spinner size="sm" /> : null}
          {/* 다크: "4 SETS" / 라이트: "✓ 4" */}
          <span className="hidden font-numeric text-xs font-medium tracking-widest text-muted uppercase dark:inline">
            {g.sets.length} SETS
          </span>
          <span className="text-sm font-bold text-accent dark:hidden">✓ {g.sets.length}</span>
        </span>
      </div>
      <p className="mt-1 truncate font-numeric text-sm text-muted">
        {g.sets.map((s) => setLabel(s.weight_kg, s.reps, s.is_warmup)).join(" · ")}
      </p>
    </Card>
  );

  const nudgeWeight = (delta: number) => {
    awaitLastRecordRef.current = null;
    setStepper({
      weight_kg: Math.min(500, Math.max(0, Math.round((stepper.weight_kg + delta) * 100) / 100)),
    });
  };

  // ±증분 퀵칩 (다크: surface 사각칩 muted / 라이트: accent 8% tint 필칩)
  const quickChipCls =
    "min-h-8 flex-1 rounded-chip bg-accent-glow px-2 font-numeric text-[11px] font-semibold text-accent " +
    "active:brightness-95 dark:bg-surface dark:font-medium dark:text-muted dark:active:brightness-125";

  const renderActiveCard = (g: LGroup | null) => {
    const lr = lastRecordQuery.data ?? null;
    const nextSetNo = (g?.sets.length ?? 0) + 1;
    const restTargetMs = restTargetSeconds * 1000;
    const restElapsedMs = restStartedAt != null ? Math.max(0, now - restStartedAt) : 0;
    const restOver = restStartedAt != null && restElapsedMs >= restTargetMs;
    const restPct = restStartedAt != null ? Math.min(100, (restElapsedMs / restTargetMs) * 100) : 0;
    return (
      <Card key={`active-${activeExerciseId}`} variant="live" className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="truncate text-base font-extrabold dark:text-[17px] dark:font-bold">
            {activeExercise?.name_ko ?? g?.name_ko ?? ""}
          </h2>
          {/* §10.2 타겟 칩 — 종목 기본이 미리 선택, 탭 → 3단계 부위 시트 */}
          {activeTarget ? (
            <TargetChipButton
              value={activeTarget}
              defaultCode={activeDefaultTarget}
              onClick={() => setTargetSheetOpen(true)}
            />
          ) : null}
          {/* 진행중 표시: 라이트 = accent 필 뱃지 / 다크 = 오렌지 글로우 도트 */}
          <span className="shrink-0 rounded-tag bg-accent px-2.5 py-1 text-[10px] font-bold text-on-accent dark:hidden">
            진행중
          </span>
          <span
            className="hidden h-2 w-2 shrink-0 rounded-full bg-accent shadow-[0_0_8px_var(--color-accent)] dark:block"
            aria-hidden="true"
          />
        </div>
        {g && g.sets.length > 0 ? (
          <ul className="flex flex-col gap-2">{g.sets.map((s, i) => renderSetRow(g, s, i))}</ul>
        ) : null}
        {lastRecordQuery.isLoading ? (
          <p className="px-1 text-[10px] text-faint">지난 기록 불러오는 중…</p>
        ) : lr && lr.sets.length > 0 ? (
          <p className="px-1 text-[10px] text-faint">
            지난번 {formatShortDate(lr.session_date)} —{" "}
            {lr.sets.map((s) => setLabel(s.weight_kg, s.reps, s.is_warmup)).join(" · ")}
          </p>
        ) : null}
        <div className="flex items-start gap-3">
          {/* 중량 웰(flex 1.4): 스테퍼 + 퀵칩이 같은 웰 안에 보이도록 동일 bg로 감쌈 */}
          <div className="flex min-w-0 flex-[1.4] flex-col rounded-well bg-well">
            <Stepper
              label={isDark ? "KG" : "중량 kg"}
              value={stepper.weight_kg}
              step={weightStep}
              onChange={(v) => {
                awaitLastRecordRef.current = null;
                setStepper({ weight_kg: v });
              }}
              min={0}
              max={500}
              className="w-full"
            />
            <div className="flex items-center justify-center gap-1.5 px-2.5 pb-2.5">
              <button type="button" className={quickChipCls} onClick={() => nudgeWeight(-weightStep)}>
                −{weightStep}
              </button>
              <button type="button" className={quickChipCls} onClick={() => nudgeWeight(weightStep)}>
                +{weightStep}
              </button>
            </div>
          </div>
          <Stepper
            label={isDark ? "REPS" : "횟수"}
            value={stepper.reps}
            step={1}
            onChange={(v) => {
              awaitLastRecordRef.current = null;
              setStepper({ reps: Math.round(v) });
            }}
            min={1}
            max={100}
            inputMode="numeric"
            className="min-w-0 flex-1"
          />
        </div>
        <div className="flex items-center gap-3">
          <WarmupToggle
            on={stepper.is_warmup}
            onToggle={() => setStepper({ is_warmup: !stepper.is_warmup })}
          />
          <TechniqueChip value={stepper.technique} onChange={(t) => setStepper({ technique: t })} />
          {inputError ? <p className="min-w-0 text-sm text-danger">{inputError}</p> : null}
        </div>
        <Button size="lg" full onClick={() => void completeSet()}>
          <span className="dark:hidden">✓ 세트 완료 ({nextSetNo})</span>
          <span className="hidden dark:inline">세트 완료 · {nextSetNo}</span>
        </Button>
        {restStartedAt != null ? (
          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-xs font-semibold text-muted dark:hidden">휴식</span>
              <span className="hidden font-numeric text-[11px] font-semibold tracking-[2px] text-muted dark:inline">
                REST
              </span>
              <span className="font-numeric text-sm font-semibold">
                <span className={restOver ? "text-accent" : "text-text"}>
                  {fmtClock(restElapsedMs)}
                </span>
                <span className="font-normal text-faint"> / {fmtClock(restTargetMs)}</span>
              </span>
            </div>
            <div className="mt-1.5 h-1 overflow-hidden rounded-[2px] bg-track dark:h-[3px]">
              <div
                className="h-full rounded-[2px] bg-accent transition-[width] duration-1000 ease-linear"
                style={{ width: `${restPct}%` }}
              />
            </div>
          </div>
        ) : null}
      </Card>
    );
  };

  const regionLabel = !boundary ? (serverSession?.region_label ?? null) : null;

  return (
    <main className="mx-auto max-w-[720px] px-[18px] py-4">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="flex items-center gap-2">
            {/* 다크: 요일 태그 + "07.21 · 가슴" / 라이트: "7월 21일 (화) · 가슴" */}
            <span className="hidden shrink-0 rounded-tag bg-accent px-1.5 py-0.5 font-numeric text-[11px] font-semibold tracking-[2px] text-on-accent dark:inline-block">
              {weekdayEn(today)}
            </span>
            <span className="hidden truncate font-numeric text-xs tracking-[2px] text-muted dark:inline">
              {headerDateIron(today)}
              {regionLabel ? ` · ${regionLabel}` : ""}
            </span>
            <span className="truncate text-xs font-semibold text-muted dark:hidden">
              {headerDateFresh(today)}
              {regionLabel ? ` · ${regionLabel}` : ""}
            </span>
          </h1>
          <p className="mt-1 flex items-baseline gap-1">
            <span className="font-numeric text-[40px] leading-none font-bold tracking-[-1px] dark:text-[48px] dark:tracking-normal">
              {fmtInt(totalVolume)}
            </span>
            <span className="text-sm font-semibold text-muted dark:text-[15px] dark:uppercase">
              kg
            </span>
          </p>
          <p className="mt-1.5 text-xs tracking-wide text-muted">
            총 볼륨{elapsedMin > 0 ? ` · ${elapsedMin}분` : ""} · 세트 {allSets.length}
          </p>
        </div>
        {hasSets ? (
          <button
            type="button"
            onClick={finishSession}
            className="touch-target shrink-0 rounded-field bg-hero px-4 text-xs font-bold text-hero-text active:brightness-110 dark:font-semibold"
          >
            완료
          </button>
        ) : null}
      </header>

      <div className="flex flex-col gap-3">
        <FlushFailuresBanner exercises={exercises} />
        {boundary && !hasSets ? (
          <p className="text-center text-xs text-muted">새 세션 — 첫 세트를 저장하면 시작됩니다</p>
        ) : null}
        {groups.length === 0 && activeExerciseId == null ? (
          <Card className="py-10 text-center text-muted">
            <p>오늘 기록이 없습니다.</p>
            <p className="mt-1 text-sm">아래에서 종목을 추가해 첫 세트를 기록하세요.</p>
          </Card>
        ) : null}
        {groups.map((g) =>
          g.exercise_id === activeExerciseId ? renderActiveCard(g) : renderCollapsedCard(g),
        )}
        {activeExerciseId != null && !activeGroup ? renderActiveCard(null) : null}
        <DashedAddButton onClick={() => setPickerOpen(true)}>＋ 종목 추가</DashedAddButton>
        {hasSets ? (
          <Button variant="ghost" full onClick={startNewSession}>
            새 세션 시작
          </Button>
        ) : null}
      </div>

      <ExercisePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        exercises={exercises}
        onSelect={selectExercise}
      />
      {/* §10.2 타겟 부위 선택 시트 — 카드 단위 sticky */}
      <TargetSheet
        open={targetSheetOpen}
        value={activeTarget}
        defaultCode={activeDefaultTarget || undefined}
        description="선택하면 이 종목의 이후 세트에 자동 적용됩니다. 새 세션은 항상 종목 기본 타겟에서 시작합니다."
        onClose={() => setTargetSheetOpen(false)}
        onSelect={(code) => void applyTarget(code)}
      />
      {/* §10.2 소급 적용 확인 — 설정 "물어보기"일 때만 열린다 */}
      <TargetBackfillModal
        open={backfill.prompt != null}
        count={(backfill.prompt?.ids.length ?? 0) + (backfill.prompt?.clientIds.length ?? 0)}
        code={backfill.prompt?.code ?? null}
        onResolve={(apply, remember) => void backfill.resolve(apply, remember)}
        onClose={backfill.dismiss}
      />
      <BodyweightModal
        open={bwModalOpen}
        onClose={() => setBwModalOpen(false)}
        onSaved={() => {
          void queryClient.invalidateQueries({ queryKey: ["bodyweight"] });
          setBwModalOpen(false);
        }}
      />
    </main>
  );
}
