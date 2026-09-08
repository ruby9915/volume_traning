// 종목 선택 bottom sheet (v2, §10.3) — 즐겨찾기 → 최근 사용 → 검색/부위별 탐색.
// 내장 라이브러리가 수백 종이라 전체 목록은 검색이나 부위 펼치기로만 연다.
// 최근 사용 목록은 내부에서 localStorage로 관리: open 시 read, 선택 시 push.
// 시트는 선택 후 자동으로 닫히지 않는다 — 호출측이 onSelect에서 닫기(open=false) 처리.

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiErrorMessage,
  archivedConflictOf,
  createExercise,
  fetchMachines,
  restoreExercise,
} from "../../api/client";
import type { Exercise, Region } from "../../api/types";
import { REGION_NAMES_KO } from "../../api/types";
import { useFavorites } from "../../hooks/useFavorites";
import { useTargets } from "../../hooks/useTargets";
import BottomSheet from "../BottomSheet";
import Button from "../Button";
import ExerciseForm, { EMPTY_FORM, validateForm, type ExerciseFormValues } from "../exercise-form/ExerciseForm";
import TagChips from "../exercise-form/TagChips";
import { exerciseMatchesQuery } from "../exercise-form/attributeUtils";
import { pushRecent, readRecent } from "./recentExercises";

const REGION_ORDER = Object.keys(REGION_NAMES_KO) as Region[];

function NewExerciseForm({
  initialName,
  exercises,
  onCreated,
  onCancel,
}: {
  initialName: string;
  exercises: Exercise[];
  onCreated: (ex: Exercise) => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const machinesQ = useQuery({ queryKey: ["machines"], queryFn: fetchMachines, staleTime: 5 * 60_000 });
  const [values, setValues] = useState<ExerciseFormValues>({ ...EMPTY_FORM, name_ko: initialName });
  const [advOpen, setAdvOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const create = async () => {
    const body = validateForm(values);
    if (typeof body === "string") {
      setErr(body);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const ex = await createExercise(body);
      await queryClient.invalidateQueries({ queryKey: ["exercises"] });
      onCreated(ex);
    } catch (e) {
      const conflict = archivedConflictOf(e);
      if (conflict) {
        if (window.confirm(`숨김 처리된 '${conflict.name_ko}' 종목이 이미 있습니다. 복원할까요?`)) {
          try {
            const restored = await restoreExercise(conflict.exercise_id);
            await queryClient.invalidateQueries({ queryKey: ["exercises"] });
            onCreated(restored);
            return;
          } catch (e2) {
            setErr(apiErrorMessage(e2));
          }
        }
        setBusy(false);
        return;
      }
      setErr(apiErrorMessage(e));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-semibold">새 종목 만들기</p>
      <p className="text-xs text-muted">
        내장 목록에 없는 종목만 추가하세요. 만든 종목은 내 계정에서만 보입니다.
      </p>
      <ExerciseForm
        values={values}
        onChange={setValues}
        exercises={exercises}
        machines={machinesQ.data ?? []}
        advancedOpen={advOpen}
        onToggleAdvanced={() => setAdvOpen((v) => !v)}
      />
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      <div className="flex gap-2">
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          취소
        </Button>
        <Button full onClick={() => void create()} disabled={busy}>
          추가하고 선택
        </Button>
      </div>
    </div>
  );
}

export interface ExercisePickerProps {
  open: boolean;
  onClose: () => void;
  /** fetchExercises() 결과 (활성 종목 목록) — 호출측 React Query 캐시 공유 */
  exercises: Exercise[];
  /** 기존 종목 선택·새 종목 생성/복원 완료 시 호출. 호출측이 여기서 시트를 닫아야 한다. */
  onSelect: (ex: Exercise) => void;
}

export default function ExercisePicker({ open, onClose, exercises, onSelect }: ExercisePickerProps) {
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [openRegion, setOpenRegion] = useState<Region | null>(null);
  const [recentIds, setRecentIds] = useState<number[]>(() => readRecent());
  const favorites = useFavorites();
  const { regionOf, nameOf } = useTargets();

  useEffect(() => {
    if (open) {
      setRecentIds(readRecent()); // openGroup 등 외부 pushRecent 반영
    } else {
      setQ("");
      setCreating(false);
      setOpenRegion(null);
    }
  }, [open]);

  const select = (ex: Exercise) => {
    setRecentIds(pushRecent(ex.id));
    onSelect(ex);
  };

  const query = q.trim().toLowerCase();
  const byId = useMemo(() => new Map(exercises.map((e) => [e.id, e])), [exercises]);
  const filtered = useMemo(
    () => (query ? exercises.filter((e) => exerciseMatchesQuery(e, query)) : []),
    [exercises, query],
  );
  const favoriteList = favorites.ids.map((id) => byId.get(id)).filter((e): e is Exercise => e != null);
  const recent = recentIds
    .map((id) => byId.get(id))
    .filter((e): e is Exercise => e != null && !favorites.isFavorite(e.id))
    .slice(0, 8);

  const byRegion = useMemo(() => {
    const map = new Map<Region, Exercise[]>();
    for (const e of exercises) {
      const r = regionOf(e.default_target) ?? "core";
      const list = map.get(r) ?? [];
      list.push(e);
      map.set(r, list);
    }
    for (const list of map.values()) list.sort((a, b) => a.name_ko.localeCompare(b.name_ko, "ko"));
    return map;
  }, [exercises, regionOf]);

  const row = (e: Exercise) => (
    <li key={e.id} className="flex items-center gap-1 border-b border-line/50">
      <button
        type="button"
        onClick={() => select(e)}
        className="flex min-h-12 min-w-0 flex-1 flex-col justify-center gap-0.5 px-1 py-1.5 text-left active:bg-surface-2"
      >
        <span className="flex items-center gap-2">
          <span className="truncate">{e.name_ko}</span>
          {e.is_own ? (
            <span className="shrink-0 rounded-tag bg-accent-glow px-1.5 py-0.5 text-[10px] font-bold text-accent">내 종목</span>
          ) : null}
          <span className="ml-auto shrink-0 text-xs text-muted">{nameOf(e.default_target)}</span>
        </span>
        <TagChips ex={e} />
      </button>
      <button
        type="button"
        aria-label={favorites.isFavorite(e.id) ? "즐겨찾기 해제" : "즐겨찾기 추가"}
        aria-pressed={favorites.isFavorite(e.id)}
        onClick={() => favorites.toggle(e.id)}
        className={`touch-target shrink-0 text-lg ${favorites.isFavorite(e.id) ? "text-accent" : "text-faint"}`}
      >
        {favorites.isFavorite(e.id) ? "★" : "☆"}
      </button>
    </li>
  );

  return (
    <BottomSheet open={open} onClose={onClose} title="종목 선택">
      {creating ? (
        <NewExerciseForm
          initialName={q.trim()}
          exercises={exercises}
          onCreated={select}
          onCancel={() => setCreating(false)}
        />
      ) : (
        <div className="flex flex-col gap-4">
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="종목 검색 (이름·별칭·태그·계열)"
            className="min-h-12 rounded-xl border border-line bg-bg px-4"
          />
          {query ? (
            // 검색으로 결과가 급감해도 시트 높이가 주저앉지 않게 최소 높이 유지
            <div className="min-h-[40dvh]">
              {filtered.length === 0 ? (
                <div className="flex flex-col gap-3">
                  <p className="text-sm text-muted">검색 결과가 없습니다.</p>
                  <Button variant="secondary" full onClick={() => setCreating(true)}>
                    ＋ "{q.trim()}" 새 종목 만들기
                  </Button>
                </div>
              ) : (
                <ul>{filtered.slice(0, 60).map(row)}</ul>
              )}
            </div>
          ) : (
            <>
              <div>
                <p className="mb-1 text-xs font-semibold text-muted">★ 즐겨찾기</p>
                {favoriteList.length === 0 ? (
                  <p className="px-1 py-2 text-xs text-faint">
                    목록에서 ☆를 눌러 자주 하는 종목을 여기에 모아 두세요.
                  </p>
                ) : (
                  <ul>{favoriteList.map(row)}</ul>
                )}
              </div>
              {recent.length > 0 ? (
                <div>
                  <p className="mb-2 text-xs font-semibold text-muted">최근 사용</p>
                  <div className="flex flex-wrap gap-2">
                    {recent.map((e) => (
                      <button
                        key={e.id}
                        type="button"
                        onClick={() => select(e)}
                        className="touch-target rounded-full border border-line bg-surface-2 px-4 text-sm active:bg-line"
                      >
                        {e.name_ko}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              <div>
                <p className="mb-1 text-xs font-semibold text-muted">전체 종목 · 부위별</p>
                <ul className="flex flex-col gap-1">
                  {REGION_ORDER.map((r) => {
                    const list = byRegion.get(r) ?? [];
                    const opened = openRegion === r;
                    return (
                      <li key={r}>
                        <button
                          type="button"
                          onClick={() => setOpenRegion(opened ? null : r)}
                          className="flex min-h-11 w-full items-center justify-between rounded-row bg-well px-3 text-sm font-semibold active:bg-surface-2"
                        >
                          <span>{REGION_NAMES_KO[r]}</span>
                          <span className="font-numeric text-xs font-normal text-muted">
                            {list.length} {opened ? "▾" : "▸"}
                          </span>
                        </button>
                        {opened ? <ul className="mt-1 pl-1">{list.map(row)}</ul> : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
              <Button variant="ghost" full onClick={() => setCreating(true)}>
                ＋ 새 종목 만들기
              </Button>
            </>
          )}
        </div>
      )}
    </BottomSheet>
  );
}
