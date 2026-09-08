import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ApiError,
  apiErrorMessage,
  deleteSession,
  deleteSet,
  fetchExercises,
  fetchSession,
  fetchSessions,
  getOutbox,
  saveSet,
  subscribeOutbox,
  updateSession,
  updateSet,
} from "../api/client";
import type {
  Exercise,
  OutboxItem,
  SessionDetail as SessionDetailData,
  SessionExerciseGroup,
  TargetCode,
} from "../api/types";
import Button from "../components/Button";
import Card from "../components/Card";
import DashedAddButton from "../components/DashedAddButton";
import FlushFailuresBanner from "../components/FlushFailuresBanner";
import Modal from "../components/Modal";
import Spinner from "../components/Spinner";
import Stepper from "../components/Stepper";
import ExercisePicker from "../components/exercise-picker/ExercisePicker";
import TargetBackfillModal from "../components/target/TargetBackfillModal";
import TargetChipButton from "../components/target/TargetChipButton";
import TargetSheet from "../components/target/TargetSheet";
import { useTargetBackfill } from "../components/target/useTargetBackfill";
import { useTargets } from "../hooks/useTargets";
import { useAppStore } from "../store";
import { formatFullDate, todayStr } from "../utils/date";
import { fmtInt } from "../utils/format";
import { validateSetInput } from "../utils/setInput";

interface SetFormValues {
  weight_kg: number;
  reps: number;
  is_warmup: boolean;
  target: TargetCode; // §10.2 세트 타겟 (항상 값 있음)
}

function groupVolume(g: SessionExerciseGroup): number {
  return g.sets.reduce((sum, s) => sum + s.volume_kg, 0);
}

// §5.3: 새 종목 첫 세트에 임의 기본 중량을 넣지 않는다
function emptySet(target: TargetCode): SetFormValues {
  return { weight_kg: 0, reps: 8, is_warmup: false, target };
}

// cardTarget: 카드 타겟 칩에서 명시 선택된 값(§10.2 sticky). undefined = 칩 미조작 →
// 마지막 세트의 타겟 상속(없으면 종목 기본)
function prefillFrom(g: SessionExerciseGroup, cardTarget?: TargetCode): SetFormValues {
  const last = g.sets[g.sets.length - 1];
  const target = cardTarget ?? last?.target ?? g.default_target;
  return last
    ? { weight_kg: last.weight_kg, reps: last.reps, is_warmup: false, target }
    : emptySet(target);
}

// §10.2 소급 적용 대상 — 세션 상세의 세트는 전부 저장된 세트라 id만 있다
interface TargetBackfillTarget {
  code: TargetCode;
  ids: number[];
}

function SetEditor({
  initial,
  defaultTarget,
  saveLabel,
  busy,
  onSave,
  onCancel,
  onDelete,
}: {
  initial: SetFormValues;
  defaultTarget: TargetCode;
  saveLabel: string;
  busy: boolean;
  onSave: (v: SetFormValues) => void;
  onCancel: () => void;
  onDelete?: () => void;
}) {
  const weightStep = useAppStore((s) => s.weightStep);
  const [values, setValues] = useState(initial);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    const err = validateSetInput(values.weight_kg, values.reps);
    if (err) {
      setError(err);
      return;
    }
    onSave(values);
  };

  return (
    <div className="mt-2 rounded-well bg-well p-2.5">
      {/* 모바일 가로 넘침 방지 — ± 버튼(44px 고정)×4가 한 행에 안 들어가므로
          수정 폼에서는 스테퍼를 세로 스택으로 배치 (Log SetEditor와 동일 패턴) */}
      <div className="flex flex-col gap-2">
        <Stepper
          label="중량(kg)"
          value={values.weight_kg}
          step={weightStep}
          max={500}
          onChange={(w) => setValues((v) => ({ ...v, weight_kg: w }))}
        />
        <Stepper
          label="횟수"
          value={values.reps}
          step={1}
          min={1}
          max={100}
          inputMode="numeric"
          onChange={(r) => setValues((v) => ({ ...v, reps: r }))}
        />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            className="h-5 w-5 accent-accent"
            checked={values.is_warmup}
            onChange={(e) => setValues((v) => ({ ...v, is_warmup: e.target.checked }))}
          />
          웜업 세트
        </label>
        <TargetChipButton value={values.target} defaultCode={defaultTarget} onClick={() => setSheetOpen(true)} />
      </div>
      {error && <p className="mt-2 text-center text-sm text-danger">{error}</p>}
      <div className="mt-3 flex gap-2">
        {onDelete && (
          <Button variant="danger" disabled={busy} onClick={onDelete}>
            삭제
          </Button>
        )}
        <Button variant="secondary" className="flex-1" disabled={busy} onClick={onCancel}>
          취소
        </Button>
        <Button className="flex-1" disabled={busy} onClick={submit}>
          {busy ? "저장 중…" : saveLabel}
        </Button>
      </div>
      <TargetSheet
        open={sheetOpen}
        value={values.target}
        defaultCode={defaultTarget}
        onClose={() => setSheetOpen(false)}
        onSelect={(code) => {
          setValues((v) => ({ ...v, target: code }));
          setSheetOpen(false);
        }}
      />
    </div>
  );
}

// §3.7B 세션 날짜·메모 수정 — PATCH /api/sessions/{id} (기존 API)
function SessionEditModal({
  open,
  sessionId,
  initialDate,
  initialNote,
  onClose,
  onSaved,
}: {
  open: boolean;
  sessionId: number;
  initialDate: string;
  initialNote: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [date, setDate] = useState(initialDate);
  const [note, setNote] = useState(initialNote ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setDate(initialDate);
      setNote(initialNote ?? "");
      setBusy(false);
      setErr(null);
    }
  }, [open, initialDate, initialNote]);

  const save = async () => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      setErr("날짜를 올바르게 선택해 주세요.");
      return;
    }
    // §3.7B: 날짜 변경 시 주간 분석 소속 변경 확인
    if (
      date !== initialDate &&
      !window.confirm("날짜를 변경하면 이 세션의 주간 분석 소속이 바뀝니다. 계속할까요?")
    ) {
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const trimmed = note.trim();
      await updateSession(sessionId, { date, note: trimmed === "" ? null : trimmed });
      onSaved();
    } catch (e) {
      setErr(apiErrorMessage(e, "세션 수정에 실패했습니다."));
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => {
        if (!busy) onClose();
      }}
      title="날짜·메모 수정"
    >
      <label className="block text-xs font-semibold text-muted" htmlFor="session-date">
        날짜
      </label>
      <input
        id="session-date"
        type="date"
        value={date}
        onChange={(e) => setDate(e.target.value)}
        className="mt-1 min-h-12 w-full rounded-xl border border-line bg-bg px-4 font-numeric"
      />
      <label className="mt-3 block text-xs font-semibold text-muted" htmlFor="session-note">
        메모
      </label>
      <input
        id="session-note"
        type="text"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="예: 어깨 컨디션 안 좋음"
        className="mt-1 min-h-12 w-full rounded-xl border border-line bg-bg px-4"
      />
      {err && <p className="mt-2 text-sm text-danger">{err}</p>}
      <div className="mt-4 flex gap-2">
        <Button variant="secondary" className="flex-1" disabled={busy} onClick={onClose}>
          취소
        </Button>
        <Button className="flex-1" disabled={busy} onClick={() => void save()}>
          {busy ? "저장 중…" : "저장"}
        </Button>
      </div>
    </Modal>
  );
}

// §3.7B 빈 날짜에 과거 기록 생성 — /history/new?date=YYYY-MM-DD (세션 미생성 상태).
// 첫 세트 저장 시 new_session=true로 생성하고 반환된 session_id로 URL 교체 (§4.2 빈 세션 금지 유지).
function NewSessionEditor() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const rawDate = searchParams.get("date") ?? "";
  const date = /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : todayStr();

  const exercisesQuery = useQuery({ queryKey: ["exercises"], queryFn: () => fetchExercises() });
  const exercises = exercisesQuery.data ?? [];

  const [pickerOpen, setPickerOpen] = useState(false);
  const [picked, setPicked] = useState<Exercise | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [queuedItems, setQueuedItems] = useState<OutboxItem[]>([]);

  // 오프라인으로 큐에 대기 중인 내 세트들 — flush 완료 시 그 날짜 세션을 찾아 URL 교체
  const myClientIdsRef = useRef<Set<string>>(new Set());
  const sessionRequestedRef = useRef(false); // 첫 세트가 큐에 들어갔으면 이후 new_session 생략

  useEffect(
    () =>
      subscribeOutbox((items) => {
        const mine = items.filter((i) => myClientIdsRef.current.has(i.client_id));
        setQueuedItems(mine);
        if (myClientIdsRef.current.size > 0 && mine.length === 0) {
          void fetchSessions({ from: date, to: date, limit: 10 })
            .then((rows) => {
              if (rows.length > 0) {
                const latest = rows.reduce((a, b) => (b.id > a.id ? b : a));
                navigate(`/history/${latest.id}`, { replace: true });
              }
            })
            .catch(() => {
              // 재조회 실패 — 대기 화면 유지 (다음 flush에서 재시도)
            });
        }
      }),
    [date, navigate],
  );

  const handleSave = async (v: SetFormValues) => {
    if (!picked) return;
    setBusy(true);
    setActionError(null);
    const before = new Set(getOutbox().map((i) => i.client_id));
    try {
      const saved = await saveSet({
        date,
        exercise_id: picked.id,
        weight_kg: v.weight_kg,
        reps: v.reps,
        is_warmup: v.is_warmup,
        target: v.target,
        // 첫 세트만 새 세션 생성 — 큐 대기 중 추가 세트는 같은 날짜 lazy 귀속 (flush 순서 보존)
        new_session: sessionRequestedRef.current ? undefined : true,
      });
      if (saved !== null) {
        navigate(`/history/${saved.session_id}`, { replace: true });
        return;
      }
      // 오프라인 큐 대기 — 내 항목 추적
      sessionRequestedRef.current = true;
      const mine = getOutbox().find((i) => !before.has(i.client_id));
      if (mine) {
        myClientIdsRef.current.add(mine.client_id);
        setQueuedItems(getOutbox().filter((i) => myClientIdsRef.current.has(i.client_id)));
      }
      setPicked(null);
    } catch (e) {
      setActionError(apiErrorMessage(e, "세트 저장에 실패했습니다."));
    } finally {
      setBusy(false);
    }
  };

  const exName = (id: number) => exercises.find((e) => e.id === id)?.name_ko ?? `종목 ${id}`;

  return (
    <main className="mx-auto max-w-[720px] p-4">
      <header className="mb-4 flex items-center gap-2">
        <Link
          to="/history"
          aria-label="이력으로"
          className="touch-target flex items-center justify-center rounded-row text-xl text-muted active:bg-surface-2"
        >
          ←
        </Link>
        <h1 className="flex-1 font-numeric text-[19px] font-extrabold dark:font-bold">
          {formatFullDate(date)}
        </h1>
      </header>

      <Card className="mb-4">
        <p className="text-sm text-muted">
          이 날짜에 새 기록을 추가합니다. 첫 세트를 저장하면 세션이 생성됩니다.
        </p>
      </Card>

      {/* §5.4 silent 유실 방지 — 이 화면에서 큐잉한 세트가 flush에서 거부돼도 안내가 보이도록 */}
      <div className="mb-3 empty:hidden">
        <FlushFailuresBanner exercises={exercises} />
      </div>

      {actionError && <p className="mb-3 text-sm text-danger">{actionError}</p>}

      {queuedItems.length > 0 && (
        <Card variant="sunken" className="mb-3">
          <p className="text-sm text-muted">오프라인 — 연결 복구 후 세션이 생성됩니다.</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {queuedItems.map((o) => (
              <li
                key={o.client_id}
                className="flex min-h-11 items-center gap-2.5 rounded-row bg-well px-3 py-2 opacity-60"
              >
                <span className="flex-1 font-numeric font-semibold">
                  {exName(o.exercise_id)} · {o.weight_kg} × {o.reps}
                </span>
                <Spinner size="sm" />
              </li>
            ))}
          </ul>
        </Card>
      )}

      {picked ? (
        <Card variant="sunken" className="mb-3">
          <h2 className="font-bold">{picked.name_ko}</h2>
          <SetEditor
            initial={emptySet(picked.default_target)}
            defaultTarget={picked.default_target}
            saveLabel="세트 저장"
            busy={busy}
            onSave={(v) => void handleSave(v)}
            onCancel={() => setPicked(null)}
          />
        </Card>
      ) : (
        <DashedAddButton onClick={() => setPickerOpen(true)}>＋ 종목 추가</DashedAddButton>
      )}

      <ExercisePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        exercises={exercises}
        onSelect={(ex) => {
          setPickerOpen(false);
          setPicked(ex);
          setActionError(null);
        }}
      />
    </main>
  );
}

function ExistingSessionDetail({ sessionIdParam }: { sessionIdParam: string }) {
  const id = Number(sessionIdParam);
  const navigate = useNavigate();
  const { nameOf } = useTargets();

  const [data, setData] = useState<SessionDetailData | null>(null);
  const [notFound, setNotFound] = useState(!Number.isFinite(id));
  const [loadError, setLoadError] = useState(false);
  const [editingSetId, setEditingSetId] = useState<number | null>(null);
  const [addingExerciseId, setAddingExerciseId] = useState<number | null>(null);
  const [newExercise, setNewExercise] = useState<Exercise | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [editSessionOpen, setEditSessionOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [queuedNotice, setQueuedNotice] = useState(false);

  // §10.2 카드 단위 sticky 타겟 (기록·세션상세 공통 UX) — 이 화면 방문 동안만 유지.
  // 값 존재 = 칩에서 명시 선택, 부재 = 미조작(마지막 세트 타겟 상속)
  const [cardTargets, setCardTargets] = useState<Partial<Record<number, TargetCode>>>({});
  const [targetSheetFor, setTargetSheetFor] = useState<number | null>(null);

  // §3.7B 종목 추가용 — Log와 React Query 캐시 공유
  const exercisesQuery = useQuery({ queryKey: ["exercises"], queryFn: () => fetchExercises() });
  const exercises = exercisesQuery.data ?? [];

  const reload = useCallback(async () => {
    try {
      const d = await fetchSession(id);
      setData(d);
      setLoadError(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setNotFound(true);
      else setLoadError(true);
    }
  }, [id]);

  useEffect(() => {
    if (Number.isFinite(id)) void reload();
  }, [id, reload]);

  // 오프라인 큐로 대기하던 세트 추가가 flush되면 재조회 (§5.4)
  const pendingRef = useRef(0);
  useEffect(() => {
    return subscribeOutbox((items) => {
      if (pendingRef.current > 0 && items.length === 0) {
        setQueuedNotice(false);
        void reload();
      }
      pendingRef.current = items.length;
    });
  }, [reload]);

  const handleUpdate = async (setId: number, v: SetFormValues) => {
    setBusy(true);
    setActionError(null);
    try {
      await updateSet(setId, {
        weight_kg: v.weight_kg,
        reps: v.reps,
        is_warmup: v.is_warmup,
        target: v.target,
      });
      setEditingSetId(null);
      await reload();
    } catch (e) {
      setActionError(apiErrorMessage(e, "세트 수정에 실패했습니다."));
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteSet = async (setId: number) => {
    setBusy(true);
    setActionError(null);
    try {
      await deleteSet(setId);
      setEditingSetId(null);
      await reload();
    } catch (e) {
      setActionError(apiErrorMessage(e, "세트 삭제에 실패했습니다."));
    } finally {
      setBusy(false);
    }
  };

  // §3.7B: 세션 상세의 세트 추가는 반드시 session_id 직접 귀속 —
  // date만 보내면 같은 날 두 번째 세션에 잘못 붙을 수 있다 (기존 결함 수정)
  const handleAdd = async (exerciseId: number, v: SetFormValues) => {
    setBusy(true);
    setActionError(null);
    try {
      const saved = await saveSet({
        date: data!.date,
        exercise_id: exerciseId,
        weight_kg: v.weight_kg,
        reps: v.reps,
        is_warmup: v.is_warmup,
        target: v.target,
        session_id: data!.id,
      });
      setAddingExerciseId(null);
      setNewExercise(null);
      if (saved === null) setQueuedNotice(true);
      else await reload();
    } catch (e) {
      setActionError(apiErrorMessage(e, "세트 추가에 실패했습니다."));
    } finally {
      setBusy(false);
    }
  };

  // 카드 칩 표시값 = 다음 "세트 추가"에 적용될 타겟 (명시 선택 우선, 없으면 마지막 세트 상속, 없으면 기본)
  const effectiveTarget = (g: SessionExerciseGroup): TargetCode =>
    cardTargets[g.exercise_id] ?? g.sets[g.sets.length - 1]?.target ?? g.default_target;

  // §10.2 소급 적용 실행 — 설정 분기·확인 다이얼로그는 useTargetBackfill이 담당 (Log와 공용)
  const backfill = useTargetBackfill(async ({ code, ids }: TargetBackfillTarget) => {
    setBusy(true);
    setActionError(null);
    try {
      for (const setId of ids) {
        await updateSet(setId, { target: code });
      }
      await reload();
    } catch (e) {
      setActionError(apiErrorMessage(e, "타겟 적용에 실패했습니다."));
    } finally {
      setBusy(false);
    }
  });

  // §10.2 타겟 선택 (카드 단위 sticky): 이후 추가 세트에 자동 적용,
  // 이미 저장된 이 카드 세트는 설정(물어보기/항상 적용/적용 안 함)에 따라 소급
  const applyCardTarget = async (g: SessionExerciseGroup, code: TargetCode) => {
    setTargetSheetFor(null);
    setCardTargets((m) => ({ ...m, [g.exercise_id]: code }));
    const ids = g.sets.filter((s) => s.target !== code).map((s) => s.id);
    if (ids.length === 0) return;
    await backfill.request({ code, ids });
  };

  const handleDeleteSession = async () => {
    setBusy(true);
    try {
      await deleteSession(id);
      navigate("/history", { replace: true });
    } catch (e) {
      setBusy(false);
      setConfirmDelete(false);
      setActionError(apiErrorMessage(e, "세션 삭제에 실패했습니다."));
    }
  };

  // 피커에서 종목 선택 — 이미 세션에 있으면 그 카드의 세트 추가 열기, 없으면 새 종목 카드
  const handlePickExercise = (ex: Exercise) => {
    setPickerOpen(false);
    setEditingSetId(null);
    setActionError(null);
    if (data?.exercises.some((g) => g.exercise_id === ex.id)) {
      setNewExercise(null);
      setAddingExerciseId(ex.id);
    } else {
      setAddingExerciseId(null);
      setNewExercise(ex);
    }
  };

  if (notFound) {
    return (
      <main className="mx-auto max-w-[720px] p-4">
        <p className="py-10 text-center text-muted">세션을 찾을 수 없습니다.</p>
        <div className="flex justify-center">
          <Link to="/history">
            <Button variant="secondary">이력으로 돌아가기</Button>
          </Link>
        </div>
      </main>
    );
  }

  if (loadError && !data) {
    return (
      <main className="mx-auto max-w-[720px] p-4">
        <p className="py-10 text-center text-muted">세션을 불러오지 못했습니다.</p>
        <div className="flex justify-center">
          <Button variant="secondary" onClick={() => void reload()}>
            다시 시도
          </Button>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="flex justify-center py-16">
        <Spinner />
      </main>
    );
  }

  const totalSets = data.exercises.reduce((n, g) => n + g.sets.length, 0);
  const sheetGroup = data.exercises.find((x) => x.exercise_id === targetSheetFor) ?? null;

  return (
    <main className="mx-auto max-w-[720px] p-4">
      <header className="mb-4 flex items-center gap-2">
        <Link
          to="/history"
          aria-label="이력으로"
          className="touch-target flex items-center justify-center rounded-row text-xl text-muted active:bg-surface-2"
        >
          ←
        </Link>
        {/* §3.7B 날짜·메모 수정 진입 — 헤더 날짜 탭 */}
        <button
          type="button"
          aria-label="날짜·메모 수정"
          className="flex min-w-0 flex-1 items-center gap-1.5 rounded-row text-left active:bg-surface-2"
          onClick={() => setEditSessionOpen(true)}
        >
          <span className="truncate font-numeric text-[19px] font-extrabold dark:font-bold">
            {formatFullDate(data.date)}
          </span>
          <span aria-hidden="true" className="shrink-0 text-sm text-muted">
            ✎
          </span>
        </button>
        <Button variant="danger" onClick={() => setConfirmDelete(true)}>
          세션 삭제
        </Button>
      </header>

      <Card className="mb-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-muted">총 볼륨</span>
          {data.region_label && (
            <span className="rounded-tag bg-accent-glow px-2 py-0.5 text-[11px] font-bold text-accent">
              {data.region_label}
            </span>
          )}
        </div>
        <p className="mt-1 font-numeric text-[36px] font-bold leading-none tracking-[-1px] dark:text-[42px] dark:font-semibold dark:tracking-normal">
          {fmtInt(data.total_volume)}
          <span className="ml-1.5 text-[15px] font-normal tracking-normal text-muted dark:uppercase">
            kg
          </span>
        </p>
        <p className="mt-2 font-numeric text-sm text-muted">
          {data.exercises.length}종목 · {totalSets}세트
        </p>
        {data.note && <p className="mt-2 text-sm text-secondary">{data.note}</p>}
      </Card>

      {/* §5.4 silent 유실 방지 — flush 중 영구 거부된 세트 알림 (Log와 공용 배너) */}
      <div className="mb-3 empty:hidden">
        <FlushFailuresBanner exercises={exercises} />
      </div>

      {actionError && <p className="mb-3 text-sm text-danger">{actionError}</p>}
      {queuedNotice && (
        <p className="mb-3 text-sm text-muted">오프라인 — 추가한 세트는 연결 복구 후 반영됩니다.</p>
      )}

      {data.exercises.length === 0 && !newExercise && (
        <p className="py-8 text-center text-sm text-muted">기록된 세트가 없습니다.</p>
      )}

      {data.exercises.map((g) => (
        <Card key={g.exercise_id} variant="sunken" className="mb-3">
          {/* 기록 화면 완료 카드 패턴: 종목명 + 우측 세트수 뱃지(라이트 ✓ N accent / 다크 N SETS) */}
          <div className="flex items-center justify-between gap-2">
            <h2 className="min-w-0 truncate font-bold">{g.name_ko}</h2>
            {/* §10.2 타겟 칩 (기록·세션상세 공통) — 탭 → 3단계 시트, 이후 추가 세트에 sticky */}
            <TargetChipButton
              value={effectiveTarget(g)}
              defaultCode={g.default_target}
              onClick={() => setTargetSheetFor(g.exercise_id)}
            />
            <span className="flex shrink-0 items-baseline gap-2 font-numeric text-sm text-muted">
              {fmtInt(groupVolume(g))} kg
              <span className="text-xs font-bold text-accent dark:hidden">✓ {g.sets.length}</span>
              <span className="hidden text-xs tracking-wider uppercase dark:inline">
                {g.sets.length} SETS
              </span>
            </span>
          </div>
          <ul className="mt-2.5 flex flex-col gap-1.5">
            {g.sets.map((s, i) =>
              editingSetId === s.id ? (
                <li key={s.id}>
                  <SetEditor
                    initial={{ weight_kg: s.weight_kg, reps: s.reps, is_warmup: s.is_warmup, target: s.target }}
                    defaultTarget={g.default_target}
                    saveLabel="저장"
                    busy={busy}
                    onSave={(v) => void handleUpdate(s.id, v)}
                    onCancel={() => setEditingSetId(null)}
                    onDelete={() => void handleDeleteSet(s.id)}
                  />
                </li>
              ) : (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setEditingSetId(s.id);
                      setAddingExerciseId(null);
                      setNewExercise(null);
                      setActionError(null);
                    }}
                    className="flex min-h-11 w-full items-center gap-2.5 rounded-row bg-well px-3 py-2 text-left active:brightness-[0.97] dark:active:brightness-125"
                  >
                    <span className="grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full bg-accent font-numeric text-[10px] font-bold text-on-accent dark:h-auto dark:w-4 dark:bg-transparent dark:text-xs dark:font-medium dark:text-muted">
                      {i + 1}
                    </span>
                    <span className="flex-1 font-numeric font-semibold">
                      {s.weight_kg} × {s.reps}
                    </span>
                    {s.is_warmup && (
                      <span className="rounded-tag bg-line px-1.5 py-0.5 text-[10px] font-semibold text-secondary">
                        웜업
                      </span>
                    )}
                    {/* §10.2 종목 기본과 다른 타겟만 뱃지 */}
                    {s.target !== g.default_target && (
                      <span className="rounded-tag bg-accent-glow px-1.5 py-0.5 text-[10px] font-semibold text-accent">
                        {nameOf(s.target)}
                      </span>
                    )}
                    <span className="shrink-0 font-numeric text-sm text-muted">
                      {fmtInt(s.volume_kg)} kg
                    </span>
                  </button>
                </li>
              ),
            )}
          </ul>
          {addingExerciseId === g.exercise_id ? (
            <SetEditor
              initial={prefillFrom(g, cardTargets[g.exercise_id])}
              defaultTarget={g.default_target}
              saveLabel="세트 추가"
              busy={busy}
              onSave={(v) => void handleAdd(g.exercise_id, v)}
              onCancel={() => setAddingExerciseId(null)}
            />
          ) : (
            <DashedAddButton
              className="mt-2"
              onClick={() => {
                setAddingExerciseId(g.exercise_id);
                setEditingSetId(null);
                setNewExercise(null);
                setActionError(null);
              }}
            >
              ＋ 세트 추가
            </DashedAddButton>
          )}
        </Card>
      ))}

      {/* §3.7B 피커에서 고른 새 종목 — 첫 세트 저장 시 session_id 직접 귀속으로 세션에 추가 */}
      {newExercise && (
        <Card variant="sunken" className="mb-3">
          <h2 className="font-bold">{newExercise.name_ko}</h2>
          <SetEditor
            initial={emptySet(newExercise.default_target)}
            defaultTarget={newExercise.default_target}
            saveLabel="세트 추가"
            busy={busy}
            onSave={(v) => void handleAdd(newExercise.id, v)}
            onCancel={() => setNewExercise(null)}
          />
        </Card>
      )}

      <DashedAddButton onClick={() => setPickerOpen(true)}>＋ 종목 추가</DashedAddButton>

      <ExercisePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        exercises={exercises}
        onSelect={handlePickExercise}
      />

      {/* §10.2 타겟 부위 선택 시트 — Log와 동일, 카드 단위 sticky */}
      <TargetSheet
        open={targetSheetFor != null}
        value={sheetGroup ? effectiveTarget(sheetGroup) : null}
        defaultCode={sheetGroup?.default_target}
        description="선택하면 이 종목의 이후 추가 세트에 자동 적용됩니다."
        onClose={() => setTargetSheetFor(null)}
        onSelect={(code) => {
          if (sheetGroup) void applyCardTarget(sheetGroup, code);
        }}
      />

      {/* §10.2 소급 적용 확인 — 설정 "물어보기"일 때만 열린다 */}
      <TargetBackfillModal
        open={backfill.prompt != null}
        count={backfill.prompt?.ids.length ?? 0}
        code={backfill.prompt?.code ?? null}
        busy={busy}
        onResolve={(apply, remember) => void backfill.resolve(apply, remember)}
        onClose={backfill.dismiss}
      />

      <SessionEditModal
        open={editSessionOpen}
        sessionId={data.id}
        initialDate={data.date}
        initialNote={data.note}
        onClose={() => setEditSessionOpen(false)}
        onSaved={() => {
          setEditSessionOpen(false);
          void reload();
        }}
      />

      <Modal
        open={confirmDelete}
        onClose={() => {
          if (!busy) setConfirmDelete(false);
        }}
        title="세션 삭제"
      >
        <p className="text-sm text-muted">
          {formatFullDate(data.date)} 세션과 세트 {totalSets}개가 모두 삭제됩니다. 되돌릴 수 없습니다.
        </p>
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" className="flex-1" disabled={busy} onClick={() => setConfirmDelete(false)}>
            취소
          </Button>
          <Button variant="danger" className="flex-1" disabled={busy} onClick={() => void handleDeleteSession()}>
            {busy ? "삭제 중…" : "삭제"}
          </Button>
        </div>
      </Modal>
    </main>
  );
}

export default function SessionDetail() {
  const { sessionId } = useParams();
  // /history/new 라우트는 :sessionId 파라미터가 없다 — 세션 미생성 편집 화면 (§3.7B)
  if (sessionId === undefined) return <NewSessionEditor />;
  return <ExistingSessionDetail sessionIdParam={sessionId} />;
}
