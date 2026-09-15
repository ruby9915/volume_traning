// §10.3 종목 관리 (v2) — 즐겨찾기 편집, 검색 + 부위 필터, 부위별 그룹(내장 라이브러리 + 내 종목),
// 폼(이름·계열·태그·기본 타겟·머신·고급), 복제, 숨김/복원.
// 내장 종목 수정은 관리자만 (공용 데이터), 일반 사용자는 복제해서 내 종목으로 만든다.

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
import type { ArchivedConflictDetail, Exercise, Region } from "../api/types";
import { REGION_NAMES_KO } from "../api/types";
import BottomSheet from "../components/BottomSheet";
import Button from "../components/Button";
import Modal from "../components/Modal";
import Spinner from "../components/Spinner";
import ExerciseForm, {
  EMPTY_FORM,
  formFromExercise,
  validateForm,
  type ExerciseFormValues,
} from "../components/exercise-form/ExerciseForm";
import TagChips from "../components/exercise-form/TagChips";
import { exerciseMatchesQuery } from "../components/exercise-form/attributeUtils";
import { collapseLabel, useCollapsed } from "../hooks/useCollapsed";
import { useFavorites } from "../hooks/useFavorites";
import { useMe } from "../hooks/useMe";
import { useTargets } from "../hooks/useTargets";

type RegionFilter = Region | "all";
const REGION_ORDER = Object.keys(REGION_NAMES_KO) as Region[];
const REGION_FILTERS: { key: RegionFilter; label: string }[] = [
  { key: "all", label: "전체" },
  ...REGION_ORDER.map((r) => ({ key: r as RegionFilter, label: REGION_NAMES_KO[r] })),
];

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

function StarButton({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      aria-label={on ? "즐겨찾기 해제" : "즐겨찾기 추가"}
      aria-pressed={on}
      onClick={onToggle}
      className={`touch-target shrink-0 text-lg ${on ? "text-accent" : "text-faint"}`}
    >
      {on ? "★" : "☆"}
    </button>
  );
}

export default function Exercises() {
  const qc = useQueryClient();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["exercises", { includeArchived: true }],
    queryFn: () => fetchExercises(true),
  });
  const me = useMe();
  const isAdmin = me.data?.is_admin ?? false;
  const favorites = useFavorites();
  const [favCollapsed, toggleFav] = useCollapsed("favorites"); // 2026-09-15 사용자 요청: 즐겨찾기 접기
  const { nameOf, regionOf } = useTargets();

  const [query, setQuery] = useState("");
  const [regionFilter, setRegionFilter] = useState<RegionFilter>("all");
  const [showArchived, setShowArchived] = useState(false);
  const [favEditing, setFavEditing] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Exercise | null>(null);
  const [cloneOf, setCloneOf] = useState<Exercise | null>(null);
  const [form, setForm] = useState<ExerciseFormValues>(EMPTY_FORM);
  const [advOpen, setAdvOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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

  const all = data ?? [];
  const byId = useMemo(() => new Map(all.map((e) => [e.id, e])), [all]);
  const canEdit = (ex: Exercise) => ex.is_own || (ex.is_builtin && isAdmin);

  const q = query.trim().toLowerCase();
  const matches = (ex: Exercise) =>
    exerciseMatchesQuery(ex, q) && (regionFilter === "all" || regionOf(ex.default_target) === regionFilter);

  const filteredActive = all.filter((ex) => !ex.is_archived && matches(ex));
  const archivedAll = all.filter((ex) => ex.is_archived);
  const filteredArchived = archivedAll.filter(matches);

  const groups = useMemo(() => {
    const byRegion = new Map<Region, Exercise[]>();
    for (const ex of filteredActive) {
      const r = regionOf(ex.default_target) ?? "core";
      const arr = byRegion.get(r) ?? [];
      arr.push(ex);
      byRegion.set(r, arr);
    }
    return REGION_ORDER.filter((r) => byRegion.has(r)).map((r) => ({
      key: r,
      label: REGION_NAMES_KO[r],
      items: (byRegion.get(r) ?? []).sort((a, b) => a.name_ko.localeCompare(b.name_ko, "ko")),
    }));
  }, [filteredActive, regionOf]);

  const favoriteList = favorites.ids.map((id) => byId.get(id)).filter((e): e is Exercise => e != null);

  // 유사 이름 경고 (§6.3 — 중복 생성으로 인한 히스토리 단절 예방)
  const similar = useMemo(() => {
    if (editing) return null;
    const n = form.name_ko.trim();
    if (n.length < 2) return null;
    return all.find((ex) => !ex.is_archived && (ex.name_ko.includes(n) || n.includes(ex.name_ko))) ?? null;
  }, [editing, form.name_ko, all]);

  function openCreate(prefillName = "") {
    setEditing(null);
    setCloneOf(null);
    setForm({ ...EMPTY_FORM, name_ko: prefillName });
    setAdvOpen(false);
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(ex: Exercise) {
    setEditing(ex);
    setCloneOf(null);
    setForm(formFromExercise(ex));
    setAdvOpen(ex.bodyweight_factor > 0 || ex.load_multiplier !== 1);
    setFormError(null);
    setFormOpen(true);
  }

  // 복제 — 내장 종목의 변형을 내 종목으로 만드는 기본 경로 (타겟·태그·계수 프리필, 이름은 바꿔야 저장됨)
  function openClone(ex: Exercise) {
    setEditing(null);
    setCloneOf(ex);
    setForm(formFromExercise(ex));
    setAdvOpen(ex.bodyweight_factor > 0 || ex.load_multiplier !== 1);
    setFormError(null);
    setFormOpen(true);
  }

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
    setCloneOf(null);
  }

  async function refresh() {
    await qc.invalidateQueries({ queryKey: ["exercises"] });
  }

  async function handleSubmit() {
    const body = validateForm(form);
    if (typeof body === "string") {
      setFormError(body);
      return;
    }
    if (cloneOf && body.name_ko === cloneOf.name_ko) {
      setFormError("복제한 종목은 이름을 바꿔서 저장하세요");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      if (editing) {
        await updateExercise(editing.id, body);
        showNotice("종목을 수정했습니다");
      } else {
        await createExercise(body);
        showNotice("내 종목으로 추가했습니다");
      }
      closeForm();
      await refresh();
    } catch (e) {
      const conflict = archivedConflictOf(e);
      if (conflict && !editing) {
        setRestoreTarget(conflict);
      } else if (e instanceof ApiError && e.status === 409) {
        setFormError("같은 이름의 종목이 이미 있습니다");
      } else if (e instanceof ApiError && e.status === 403) {
        setFormError("내장 종목은 관리자만 수정할 수 있습니다. 복제해서 내 종목으로 만드세요.");
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
      showNotice(res.archived ? "세트 기록이 있어 숨김 처리했습니다" : "종목을 삭제했습니다");
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

  function moveFavorite(index: number, delta: number) {
    const next = [...favorites.ids];
    const j = index + delta;
    if (j < 0 || j >= next.length) return;
    [next[index], next[j]] = [next[j], next[index]];
    favorites.reorder(next);
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

  const exerciseRow = (ex: Exercise, i: number) => (
    <div
      key={ex.id}
      className={`flex w-full items-center gap-1 pr-2 transition-colors hover:bg-surface-2 ${
        i > 0 ? "border-t border-hairline" : ""
      }`}
    >
      <button
        type="button"
        onClick={() => (canEdit(ex) ? openEdit(ex) : openClone(ex))}
        className="flex min-w-0 flex-1 items-center gap-3 py-3 pl-4 text-left active:bg-surface-2"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-semibold">{ex.name_ko}</span>
            {ex.is_own ? (
              <span className="shrink-0 rounded-tag bg-accent-glow px-2 py-0.5 text-[10px] font-bold text-accent">
                내 종목
              </span>
            ) : null}
          </div>
          <div className="mt-0.5 truncate text-xs text-muted">
            {nameOf(ex.default_target)}
            {ex.name_en ? ` · ${ex.name_en}` : ""}
          </div>
          <TagChips ex={ex} className="mt-1" />
        </div>
        <span className="text-faint">{canEdit(ex) ? "›" : "복제 ›"}</span>
      </button>
      <StarButton on={favorites.isFavorite(ex.id)} onToggle={() => favorites.toggle(ex.id)} />
    </div>
  );

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

      {/* 즐겨찾기 — 운동 중 빠르게 고를 종목. 순서 편집 가능 */}
      <section className="mt-3 rounded-card bg-surface p-4 shadow-card">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">★ 즐겨찾기 <span className="font-numeric text-xs font-normal text-faint">{favoriteList.length}</span></h2>
          <div className="flex items-center gap-1">
            {favoriteList.length > 1 && !favCollapsed ? (
              <button
                type="button"
                className="touch-target text-xs font-semibold text-accent"
                onClick={() => setFavEditing((v) => !v)}
              >
                {favEditing ? "완료" : "순서 편집"}
              </button>
            ) : null}
            <button
              type="button"
              aria-expanded={!favCollapsed}
              className="touch-target -mr-2 px-2 text-xs font-semibold text-muted active:text-text"
              onClick={toggleFav}
            >
              {collapseLabel(favCollapsed)}
            </button>
          </div>
        </div>
        {favCollapsed ? null : favoriteList.length === 0 ? (
          <p className="mt-2 text-xs text-muted">
            아래 목록에서 ☆를 눌러 자주 하는 종목을 모아 두면 기록 화면 종목 선택이 빨라집니다.
          </p>
        ) : (
          <ul className="mt-2 divide-y divide-hairline">
            {favoriteList.map((ex, i) => (
              <li key={ex.id} className="flex items-center gap-2 py-1.5">
                <span className="min-w-0 flex-1 truncate text-sm">{ex.name_ko}</span>
                {favEditing ? (
                  <>
                    <button type="button" aria-label="위로" className="touch-target text-muted" disabled={i === 0 || favorites.isMutating} onClick={() => moveFavorite(i, -1)}>▲</button>
                    <button type="button" aria-label="아래로" className="touch-target text-muted" disabled={i === favoriteList.length - 1 || favorites.isMutating} onClick={() => moveFavorite(i, 1)}>▼</button>
                    <button type="button" aria-label="즐겨찾기 해제" className="touch-target text-danger" onClick={() => favorites.toggle(ex.id)}>✕</button>
                  </>
                ) : (
                  <span className="text-xs text-muted">{nameOf(ex.default_target)}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="종목 검색 (이름·별칭·태그·계열·머신)"
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
                <span className="font-numeric text-xs font-normal text-faint">{g.items.length}</span>
              </h2>
              <div className="overflow-hidden rounded-card bg-surface shadow-card">
                {g.items.map(exerciseRow)}
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
                    className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? "border-t border-hairline" : ""}`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-muted">{ex.name_ko}</div>
                      <div className="truncate text-xs text-faint">{nameOf(ex.default_target)}</div>
                      <TagChips ex={ex} className="mt-1" />
                    </div>
                    {canEdit(ex) ? (
                      <Button
                        variant="secondary"
                        disabled={restoringId === ex.id}
                        onClick={() => void handleRestoreRow(ex)}
                      >
                        {restoringId === ex.id ? <Spinner size="sm" /> : "복원"}
                      </Button>
                    ) : null}
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
        title={editing ? (editing.is_builtin ? "내장 종목 수정 (관리자)" : "내 종목 수정") : cloneOf ? "복제해서 내 종목 만들기" : "새 종목"}
      >
        <div className="space-y-4 pb-2">
          {cloneOf ? (
            <p className="text-xs text-muted">
              '{cloneOf.name_ko}'의 타겟·태그·계수를 가져왔습니다. 이름을 바꿔 저장하면 내 종목이 됩니다.
            </p>
          ) : null}
          <ExerciseForm
            values={form}
            onChange={setForm}
            exercises={all}
            advancedOpen={advOpen}
            onToggleAdvanced={() => setAdvOpen((v) => !v)}
          />
          {similar && similar.id !== cloneOf?.id ? (
            <p className="text-sm text-muted">
              유사한 종목이 이미 있습니다: <span className="font-semibold text-text">{similar.name_ko}</span>
            </p>
          ) : null}

          {formError ? <p className="text-sm text-danger">{formError}</p> : null}

          <Button size="lg" full disabled={saving} onClick={() => void handleSubmit()}>
            {saving ? "저장 중…" : editing ? "저장" : "추가"}
          </Button>
          {editing ? (
            <Button variant="danger" full disabled={saving} onClick={() => setConfirmDelete(true)}>
              {editing.is_builtin ? "숨기기 (모든 사용자에게서)" : "삭제"}
            </Button>
          ) : null}
        </div>
      </BottomSheet>

      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="종목 삭제">
        <p className="text-sm text-secondary">
          이 종목을 삭제할까요? 세트 기록이 있으면 삭제 대신 숨김 처리되어 과거 기록이 보존됩니다.
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

      <Modal open={restoreTarget !== null} onClose={() => setRestoreTarget(null)} title="숨긴 종목 복원">
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
    </main>
  );
}
