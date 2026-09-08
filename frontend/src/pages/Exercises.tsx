// §5.6 종목 관리 — 검색 + 부위 필터 칩, 부위별 그룹, 커스텀 뱃지, FAB 추가, 폼, 숨김/복원
// 리디자인: README "3. 종목 — 패턴 확장" (시맨틱 토큰만 사용, 다크 IRON / 라이트 FRESH 자동 전환)

import { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  archivedConflictOf,
  createExercise,
  deleteExercise,
  fetchExercises,
  restoreExercise,
  updateExercise,
} from "../api/client";
import type {
  ArchivedConflictDetail,
  Exercise,
  ExerciseCreateRequest,
  ExerciseMuscle,
  MuscleCode,
  Region,
} from "../api/types";
import { MUSCLE_GROUPS, MUSCLE_NAME_KO, REGION_NAMES_KO } from "../api/types";
import BottomSheet from "../components/BottomSheet";
import Button from "../components/Button";
import Modal from "../components/Modal";
import Spinner from "../components/Spinner";
import AttrChips from "../components/exercise-form/AttrChips";
import AttributeBuilder from "../components/exercise-form/AttributeBuilder";
import {
  EMPTY_ATTRS,
  attrsFromExercise,
  attrsToPayload,
  classificationChanged,
  exerciseMatchesQuery,
  type AttrDraft,
} from "../components/exercise-form/attributeUtils";

const MUSCLE_REGION = Object.fromEntries(
  MUSCLE_GROUPS.map((m) => [m.code, m.region]),
) as Record<MuscleCode, Region>;

type RegionFilter = Region | "all";

const REGION_FILTERS: { key: RegionFilter; label: string }[] = [
  { key: "all", label: "전체" },
  ...(Object.keys(REGION_NAMES_KO) as Region[]).map((r) => ({
    key: r as RegionFilter,
    label: REGION_NAMES_KO[r],
  })),
];

interface FormState {
  name_ko: string;
  primary: MuscleCode[];
  secondary: MuscleCode[];
  bodyweight_factor: string;
  load_multiplier: string;
  attrs: AttrDraft; // §3.6 속성 draft (aliases 포함)
}

const EMPTY_FORM: FormState = {
  name_ko: "",
  primary: [],
  secondary: [],
  bodyweight_factor: "0",
  load_multiplier: "1",
  attrs: EMPTY_ATTRS,
};

function muscleSummary(ex: Exercise): string {
  const p = ex.muscles.filter((m) => m.role === "primary").map((m) => MUSCLE_NAME_KO[m.code]);
  const s = ex.muscles.filter((m) => m.role === "secondary").map((m) => MUSCLE_NAME_KO[m.code]);
  return s.length ? `${p.join("·")} / ${s.join("·")}` : p.join("·");
}

/** 수정·복제 폼 프리필 — 종목의 부위·계수·속성을 폼 상태로 */
function formFromExercise(ex: Exercise): FormState {
  return {
    name_ko: ex.name_ko,
    primary: ex.muscles.filter((m) => m.role === "primary").map((m) => m.code),
    secondary: ex.muscles.filter((m) => m.role === "secondary").map((m) => m.code),
    bodyweight_factor: String(ex.bodyweight_factor),
    load_multiplier: String(ex.load_multiplier),
    attrs: attrsFromExercise(ex),
  };
}

/** 고급 설정(체중 계수·중량 배수)이 기본값이 아니면 펼친 채로 연다 */
function hasAdvancedValues(ex: Exercise): boolean {
  return ex.bodyweight_factor > 0 || ex.load_multiplier !== 1;
}

/** 종목이 속한 부위(들): primary 근육의 region 기준 (primary 없으면 전체 근육 기준) */
function exerciseRegions(ex: Exercise): Region[] {
  const primary = ex.muscles.filter((m) => m.role === "primary");
  const src = primary.length > 0 ? primary : ex.muscles;
  return [...new Set(src.map((m) => MUSCLE_REGION[m.code]))];
}

/** 페이지 타이틀 — 라이트 FRESH: 한글 19px 800 / 다크 IRON: Oswald 대문자 레터스페이싱 (분석 헤더 패턴) */
function PageTitle() {
  return (
    <h1>
      <span className="text-[19px] font-extrabold dark:hidden">종목</span>
      <span className="hidden font-numeric text-[13px] font-semibold uppercase tracking-[3px] text-muted dark:inline">
        EXERCISES
      </span>
    </h1>
  );
}

function MuscleChips({
  selected,
  disabledCodes,
  onToggle,
}: {
  selected: MuscleCode[];
  disabledCodes: MuscleCode[];
  onToggle: (code: MuscleCode) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {MUSCLE_GROUPS.map((mg) => {
        const isSelected = selected.includes(mg.code);
        const isDisabled = disabledCodes.includes(mg.code);
        return (
          <button
            key={mg.code}
            type="button"
            disabled={isDisabled}
            onClick={() => onToggle(mg.code)}
            className={`touch-target rounded-chip px-4 text-sm transition-colors ${
              isSelected
                ? "bg-accent font-semibold text-on-accent"
                : "bg-well text-secondary active:bg-surface-2"
            } ${isDisabled ? "opacity-35" : ""}`}
          >
            {mg.name_ko}
          </button>
        );
      })}
    </div>
  );
}

const INPUT_CLS =
  "mt-1 w-full rounded-field border border-transparent bg-well px-4 py-3 outline-none placeholder:text-faint focus:border-accent";

export default function Exercises() {
  const qc = useQueryClient();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["exercises", { includeArchived: true }],
    queryFn: () => fetchExercises(true),
  });

  const [query, setQuery] = useState("");
  const [regionFilter, setRegionFilter] = useState<RegionFilter>("all");
  const [showArchived, setShowArchived] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Exercise | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [advOpen, setAdvOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // 속성 빌더 내부 상태(이름 자동조합·넛지)를 폼 열 때마다 리셋하기 위한 key
  const [builderSeq, setBuilderSeq] = useState(0);
  const [builderNameTouched, setBuilderNameTouched] = useState(true);
  // §3.6 규율 문구 확인 다이얼로그 (분류 5속성 변경 시)
  const [disciplineOpen, setDisciplineOpen] = useState(false);

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<ArchivedConflictDetail | null>(null);
  const [restoringId, setRestoringId] = useState<number | null>(null);

  const [notice, setNotice] = useState<string | null>(null);
  const noticeTimer = useRef<number | undefined>(undefined);

  function showNotice(msg: string) {
    setNotice(msg);
    window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 3000);
  }

  const q = query.trim().toLowerCase();
  // §3.6 검색: name_ko / name_en / aliases / 속성값 전부 매칭
  const matches = (ex: Exercise) =>
    exerciseMatchesQuery(ex, q) &&
    (regionFilter === "all" || exerciseRegions(ex).includes(regionFilter));

  const all = data ?? [];
  const filteredActive = all.filter((ex) => !ex.is_archived && matches(ex));
  const archivedAll = all.filter((ex) => ex.is_archived);
  const filteredArchived = archivedAll.filter(matches);

  const groups = useMemo(() => {
    const byCode = new Map<string, Exercise[]>();
    for (const ex of filteredActive) {
      const code = ex.muscles.find((m) => m.role === "primary")?.code ?? "etc";
      const arr = byCode.get(code) ?? [];
      arr.push(ex);
      byCode.set(code, arr);
    }
    const result: { key: string; label: string; items: Exercise[] }[] = [];
    for (const mg of MUSCLE_GROUPS) {
      const items = byCode.get(mg.code);
      if (items) result.push({ key: mg.code, label: mg.name_ko, items });
    }
    const etc = byCode.get("etc");
    if (etc) result.push({ key: "etc", label: "기타", items: etc });
    return result;
  }, [filteredActive]);

  // 유사 이름 경고 (§6.3 — 중복 생성으로 인한 히스토리 단절 예방)
  const similar = useMemo(() => {
    if (editing) return null;
    const n = form.name_ko.trim();
    if (n.length < 2) return null;
    return (
      all.find(
        (ex) => !ex.is_archived && (ex.name_ko.includes(n) || n.includes(ex.name_ko)),
      ) ?? null
    );
  }, [editing, form.name_ko, all]);

  function openCreate(prefillName = "") {
    setEditing(null);
    setForm({ ...EMPTY_FORM, name_ko: prefillName, attrs: { ...EMPTY_ATTRS } });
    setAdvOpen(false);
    setFormError(null);
    // 검색어 프리필이 있으면 이름을 이미 정한 것 — 자동 조합 중단
    setBuilderNameTouched(prefillName.trim() !== "");
    setBuilderSeq((s) => s + 1);
    setFormOpen(true);
  }

  function openEdit(ex: Exercise) {
    setEditing(ex);
    setForm(formFromExercise(ex));
    setAdvOpen(hasAdvancedValues(ex));
    setFormError(null);
    // 수정 모드: 기존 이름을 자동 조합으로 덮어쓰지 않는다
    setBuilderNameTouched(true);
    setBuilderSeq((s) => s + 1);
    setFormOpen(true);
  }

  // §3.6-5 복제 생성 — 속성·부위·계수 프리필 후 새 종목으로 저장 (변형 생성의 기본 경로)
  function openClone(ex: Exercise) {
    setEditing(null);
    setForm(formFromExercise(ex));
    setAdvOpen(hasAdvancedValues(ex));
    setFormError(null);
    // 복제: 속성을 바꾸면 이름이 자동으로 따라 바뀌도록 자동 조합 활성
    setBuilderNameTouched(false);
    setBuilderSeq((s) => s + 1);
    setFormOpen(true);
  }

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
  }

  function togglePrimary(code: MuscleCode) {
    setForm((f) => ({
      ...f,
      primary: f.primary.includes(code)
        ? f.primary.filter((c) => c !== code)
        : [...f.primary, code],
      secondary: f.secondary.filter((c) => c !== code),
    }));
  }

  function toggleSecondary(code: MuscleCode) {
    setForm((f) => ({
      ...f,
      secondary: f.secondary.includes(code)
        ? f.secondary.filter((c) => c !== code)
        : [...f.secondary, code],
    }));
  }

  async function refresh() {
    await qc.invalidateQueries({ queryKey: ["exercises"] });
  }

  async function handleSubmit(skipDisciplineCheck = false) {
    const name = form.name_ko.trim();
    if (name.length < 1 || name.length > 50) {
      setFormError("이름은 1~50자로 입력하세요");
      return;
    }
    if (form.primary.length === 0) {
      setFormError("주동근을 1개 이상 선택하세요");
      return;
    }
    const bw = Number(form.bodyweight_factor);
    if (!Number.isFinite(bw) || bw < 0 || bw > 1) {
      setFormError("체중 계수는 0~1 사이 숫자여야 합니다");
      return;
    }
    const lm = Number(form.load_multiplier);
    if (!Number.isFinite(lm) || lm <= 0) {
      setFormError("중량 배수는 0보다 큰 숫자여야 합니다");
      return;
    }
    // §3.6 운영 규율: 분류 속성 변경은 확인 다이얼로그를 거친다 (차단 아님)
    if (!skipDisciplineCheck && editing && classificationChanged(editing, form.attrs)) {
      setDisciplineOpen(true);
      return;
    }
    const muscles: ExerciseMuscle[] = [
      ...form.primary.map((code) => ({ code, role: "primary" as const })),
      ...form.secondary.map((code) => ({ code, role: "secondary" as const })),
    ];
    const body: ExerciseCreateRequest = {
      name_ko: name,
      muscles,
      bodyweight_factor: bw,
      load_multiplier: lm,
      ...attrsToPayload(form.attrs),
    };
    setSaving(true);
    setFormError(null);
    try {
      if (editing) {
        await updateExercise(editing.id, body);
        showNotice("종목을 수정했습니다");
      } else {
        await createExercise(body);
        showNotice("종목을 추가했습니다");
      }
      closeForm();
      await refresh();
    } catch (e) {
      const conflict = archivedConflictOf(e);
      if (conflict && !editing) {
        setRestoreTarget(conflict);
      } else if (e instanceof ApiError && e.status === 409) {
        setFormError("같은 이름의 종목이 이미 있습니다");
      } else {
        setFormError(e instanceof Error ? e.message : "저장에 실패했습니다");
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleRestoreConflict() {
    if (!restoreTarget) return;
    const target = restoreTarget;
    setSaving(true);
    try {
      await restoreExercise(target.exercise_id);
      setRestoreTarget(null);
      closeForm();
      showNotice(`'${target.name_ko}' 종목을 복원했습니다`);
      await refresh();
    } catch {
      setRestoreTarget(null);
      setFormError("복원에 실패했습니다");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!editing) return;
    setSaving(true);
    try {
      const res = await deleteExercise(editing.id);
      setConfirmDelete(false);
      closeForm();
      showNotice(
        res.archived ? "세트 기록이 있어 숨김 처리했습니다" : "종목을 삭제했습니다",
      );
      await refresh();
    } catch (e) {
      setConfirmDelete(false);
      setFormError(e instanceof Error ? e.message : "삭제에 실패했습니다");
    } finally {
      setSaving(false);
    }
  }

  async function handleRestoreRow(ex: Exercise) {
    setRestoringId(ex.id);
    try {
      await restoreExercise(ex.id);
      showNotice(`'${ex.name_ko}' 종목을 복원했습니다`);
      await refresh();
    } catch {
      showNotice("복원에 실패했습니다");
    } finally {
      setRestoringId(null);
    }
  }

  if (isLoading) {
    return (
      <main className="mx-auto flex max-w-[720px] justify-center p-4 pt-24">
        <Spinner />
      </main>
    );
  }

  if (isError) {
    return (
      <main className="mx-auto max-w-[720px] p-4">
        <PageTitle />
        <p className="mt-4 text-danger">종목 목록을 불러오지 못했습니다.</p>
        <Button variant="secondary" className="mt-3" onClick={() => void refetch()}>
          다시 시도
        </Button>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[720px] p-4 safe-bottom">
      <header className="flex min-h-9 items-center">
        <PageTitle />
      </header>

      {notice ? (
        <div className="mt-3 rounded-card bg-accent-glow px-4 py-3 text-sm font-semibold text-accent">
          {notice}
        </div>
      ) : null}

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="종목 검색"
        className="mt-3 w-full rounded-field border border-transparent bg-surface px-4 py-3 shadow-card outline-none placeholder:text-faint focus:border-accent"
      />

      {/* 부위 필터 칩 — 활성 = accent 필 (radius: 라이트 999px / 다크 5px 토큰) */}
      <div className="-mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1">
        {REGION_FILTERS.map((rf) => (
          <button
            key={rf.key}
            type="button"
            onClick={() => setRegionFilter(rf.key)}
            className={`touch-target shrink-0 rounded-chip px-4 text-sm transition-colors ${
              regionFilter === rf.key
                ? "bg-accent font-bold text-on-accent"
                : "bg-surface font-semibold text-muted shadow-card active:bg-surface-2"
            }`}
          >
            {rf.label}
          </button>
        ))}
      </div>

      {filteredActive.length === 0 ? (
        <div className="mt-8 text-center">
          <p className="text-muted">검색 결과가 없습니다</p>
          <Button className="mt-4" onClick={() => openCreate(query.trim())}>
            ＋ 새 종목 만들기
          </Button>
        </div>
      ) : (
        <div className="mt-4">
          {groups.map((g) => (
            <section key={g.key} className="mb-4">
              <h2 className="mb-2 flex items-baseline gap-1.5 px-1 text-sm font-semibold text-muted">
                {g.label}
                <span className="font-numeric text-xs font-normal text-faint">
                  {g.items.length}
                </span>
              </h2>
              <div className="overflow-hidden rounded-card bg-surface shadow-card">
                {g.items.map((ex, i) => (
                  <div
                    key={ex.id}
                    className={`flex w-full items-center gap-2 pr-3 transition-colors hover:bg-surface-2 ${
                      i > 0 ? "border-t border-hairline" : ""
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => openEdit(ex)}
                      className="flex min-w-0 flex-1 items-center gap-3 py-3 pl-4 text-left active:bg-surface-2"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-semibold">{ex.name_ko}</span>
                          {!ex.is_builtin ? (
                            <span className="shrink-0 rounded-tag bg-accent-glow px-2 py-0.5 text-[10px] font-bold text-accent">
                              커스텀
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-0.5 truncate text-xs text-muted">
                          {muscleSummary(ex)}
                        </div>
                        <AttrChips ex={ex} className="mt-1" />
                      </div>
                      <span className="text-faint">›</span>
                    </button>
                    {/* §3.6-5 복제 — 변형 생성의 기본 경로 (속성·부위·계수 프리필) */}
                    <button
                      type="button"
                      aria-label={`${ex.name_ko} 복제`}
                      onClick={() => openClone(ex)}
                      className="touch-target shrink-0 rounded-chip bg-well px-3 text-xs font-semibold text-muted active:bg-surface-2"
                    >
                      복제
                    </button>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {archivedAll.length > 0 ? (
        <div className="mt-2">
          <button
            type="button"
            className="touch-target w-full text-sm text-muted"
            onClick={() => setShowArchived((v) => !v)}
          >
            {showArchived ? "숨긴 종목 감추기" : `숨긴 종목 ${archivedAll.length}개 보기`}
          </button>
          {showArchived ? (
            <div className="mt-2 overflow-hidden rounded-card bg-surface shadow-card">
              {filteredArchived.length === 0 ? (
                <p className="px-4 py-3 text-sm text-muted">검색과 일치하는 숨긴 종목 없음</p>
              ) : (
                filteredArchived.map((ex, i) => (
                  <div
                    key={ex.id}
                    className={`flex items-center gap-3 px-4 py-2 ${
                      i > 0 ? "border-t border-hairline" : ""
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-muted">{ex.name_ko}</div>
                      <div className="truncate text-xs text-faint">{muscleSummary(ex)}</div>
                      <AttrChips ex={ex} className="mt-1" />
                    </div>
                    <Button
                      variant="secondary"
                      disabled={restoringId === ex.id}
                      onClick={() => void handleRestoreRow(ex)}
                    >
                      {restoringId === ex.id ? <Spinner size="sm" /> : "복원"}
                    </Button>
                  </div>
                ))
              )}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* FAB — 종목 추가 */}
      <button
        type="button"
        aria-label="종목 추가"
        onClick={() => openCreate()}
        className="fixed bottom-24 right-4 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-accent text-2xl font-bold text-on-accent shadow-btn transition-transform duration-100 hover:brightness-[1.08] active:scale-95"
      >
        ＋
      </button>

      <BottomSheet
        open={formOpen}
        onClose={closeForm}
        title={editing ? "종목 수정" : "새 종목"}
      >
        <div className="space-y-4 pb-2">
          {/* §3.6 속성 빌더 — 동작·속성 4종 자동완성, 이름 자동 조합, 넛지, 중복 경고 */}
          <AttributeBuilder
            key={builderSeq}
            exercises={all}
            excludeId={editing?.id}
            name={form.name_ko}
            attrs={form.attrs}
            onNameChange={(n) => setForm((f) => ({ ...f, name_ko: n }))}
            onAttrsChange={(a) => setForm((f) => ({ ...f, attrs: a }))}
            initialNameTouched={builderNameTouched}
          />
          {similar ? (
            <p className="text-sm text-muted">
              유사한 종목이 이미 있습니다:{" "}
              <span className="font-semibold text-text">{similar.name_ko}</span>
            </p>
          ) : null}

          <div>
            <span className="text-sm text-muted">주동근 (1개 이상)</span>
            <div className="mt-2">
              <MuscleChips
                selected={form.primary}
                disabledCodes={[]}
                onToggle={togglePrimary}
              />
            </div>
          </div>

          <div>
            <span className="text-sm text-muted">보조근</span>
            <div className="mt-2">
              <MuscleChips
                selected={form.secondary}
                disabledCodes={form.primary}
                onToggle={toggleSecondary}
              />
            </div>
          </div>

          <div>
            <button
              type="button"
              className="touch-target text-sm text-muted"
              onClick={() => setAdvOpen((v) => !v)}
            >
              {advOpen ? "▾ 고급 설정" : "▸ 고급 설정"}
            </button>
            {advOpen ? (
              <div className="mt-2 space-y-3 rounded-well border border-line p-3">
                <label className="block">
                  <span className="text-sm text-muted">체중 계수 (0~1)</span>
                  <input
                    value={form.bodyweight_factor}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, bodyweight_factor: e.target.value }))
                    }
                    inputMode="decimal"
                    className={`${INPUT_CLS} font-numeric`}
                  />
                  <span className="mt-1 block text-xs text-muted">
                    맨몸 운동이 유효 중량에 포함할 체중 비율 (풀업 1, 푸시업 0.65)
                  </span>
                </label>
                <label className="block">
                  <span className="text-sm text-muted">중량 배수</span>
                  <input
                    value={form.load_multiplier}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, load_multiplier: e.target.value }))
                    }
                    inputMode="decimal"
                    className={`${INPUT_CLS} font-numeric`}
                  />
                  <span className="mt-1 block text-xs text-muted">
                    양손 덤벨 동시 운동은 2 (한쪽 덤벨 무게로 입력)
                  </span>
                </label>
              </div>
            ) : null}
          </div>

          {formError ? <p className="text-sm text-danger">{formError}</p> : null}

          <Button size="lg" full disabled={saving} onClick={() => void handleSubmit()}>
            {saving ? "저장 중…" : editing ? "저장" : "추가"}
          </Button>
          {editing ? (
            <Button
              variant="danger"
              full
              disabled={saving}
              onClick={() => setConfirmDelete(true)}
            >
              삭제
            </Button>
          ) : null}
        </div>
      </BottomSheet>

      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="종목 삭제"
      >
        <p className="text-sm text-secondary">
          이 종목을 삭제할까요? 세트 기록이 있으면 삭제 대신 숨김 처리되어 과거 기록이
          보존됩니다.
        </p>
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" full onClick={() => setConfirmDelete(false)}>
            취소
          </Button>
          <Button variant="danger" full disabled={saving} onClick={() => void handleDelete()}>
            삭제
          </Button>
        </div>
      </Modal>

      <Modal
        open={restoreTarget !== null}
        onClose={() => setRestoreTarget(null)}
        title="숨긴 종목 복원"
      >
        <p className="text-sm text-secondary">
          {`'${restoreTarget?.name_ko ?? ""}'은(는) 숨김 처리된 종목입니다. 새로 만드는 대신 복원하면 과거 기록이 이어집니다. 복원하시겠습니까?`}
        </p>
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" full onClick={() => setRestoreTarget(null)}>
            취소
          </Button>
          <Button full disabled={saving} onClick={() => void handleRestoreConflict()}>
            복원
          </Button>
        </div>
      </Modal>

      {/* §3.6 운영 규율 — 속성 수정 확인 다이얼로그 */}
      <Modal
        open={disciplineOpen}
        onClose={() => setDisciplineOpen(false)}
        title="속성 수정 확인"
      >
        <p className="text-sm text-secondary">
          과거까지 사실이 바뀌는 '정정'이면 수정, 오늘부터 달라지는 '변경'이면 신규
          등록.
        </p>
        <p className="mt-2 text-xs text-muted">
          속성 수정은 계열 합산·필터 소속만 바꾸며, 이 종목의 PR·세트 기록은 그대로
          유지됩니다. 오늘부터 다르게 수행한다면 취소 후 목록의 '복제'로 새 종목을
          만드세요.
        </p>
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" full onClick={() => setDisciplineOpen(false)}>
            취소
          </Button>
          <Button
            full
            disabled={saving}
            onClick={() => {
              setDisciplineOpen(false);
              void handleSubmit(true);
            }}
          >
            정정으로 수정
          </Button>
        </div>
      </Modal>
    </main>
  );
}
