// 종목 선택 bottom sheet (v2, §10.3 · §15.4) — 즐겨찾기 → 최근 사용 → 검색/부위별 탐색.
// 내장 라이브러리가 수백 종이라 전체 목록은 검색이나 부위 펼치기로만 연다.
// 최근 사용 목록은 내부에서 localStorage로 관리: open 시 read, 선택 시 push.
// 시트는 선택 후 자동으로 닫히지 않는다 — 호출측이 onSelect에서 닫기(open=false) 처리.
//
// §15.4 머신으로 찾기: 머신을 먼저 고르면(내 머신 칩·머신 검색·종목 검색 결과의 머신) 그 머신으로
// 할 종목 후보를 보여 주고, 고른 종목과 머신을 함께 onSelect로 넘긴다. 한 가지 동작용 머신
// (참고 타겟 있음)이고 내가 그 머신으로 기록한 종목이 하나뿐이면 후보 없이 바로 그 종목으로 시작한다.

import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiErrorMessage,
  archivedConflictOf,
  createExercise,
  fetchMachineExercises,
  fetchMachines,
  restoreExercise,
} from "../../api/client";
import type { Exercise, Machine, Region, TargetCode } from "../../api/types";
import { REGION_NAMES_KO } from "../../api/types";
import { useFavorites } from "../../hooks/useFavorites";
import { useMyMachines } from "../../hooks/useMyMachines";
import { useTargets } from "../../hooks/useTargets";
import { formatShortDate } from "../../utils/date";
import BottomSheet from "../BottomSheet";
import Button from "../Button";
import Spinner from "../Spinner";
import ExerciseForm, { EMPTY_FORM, validateForm, type ExerciseFormValues } from "../exercise-form/ExerciseForm";
import TagChips from "../exercise-form/TagChips";
import { exerciseMatchesQuery } from "../exercise-form/attributeUtils";
import MachinePicker from "../machine/MachinePicker";
import MachineRow from "../machine/MachineRow";
import { pushRecent, readRecent } from "./recentExercises";

const REGION_ORDER = Object.keys(REGION_NAMES_KO) as Region[];
/** 종목 검색 결과 아래에 함께 보여 줄 머신 수 — 더 찾으려면 머신 검색 시트로 */
const MACHINE_HITS = 4;
const SECTION_LABEL = "mb-1 text-xs font-semibold text-muted";

function NewExerciseForm({
  initialName,
  initialTarget,
  hint,
  exercises,
  onCreated,
  onCancel,
}: {
  initialName: string;
  /** 머신의 참고 타겟 — 있으면 기본 타겟을 채워 둔다 (고칠 수 있다) */
  initialTarget?: TargetCode | null;
  hint: string;
  exercises: Exercise[];
  onCreated: (ex: Exercise) => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<ExerciseFormValues>({
    ...EMPTY_FORM,
    name_ko: initialName,
    default_target: initialTarget ?? null,
  });
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
      <p className="text-xs text-muted">{hint}</p>
      <ExerciseForm
        values={values}
        onChange={setValues}
        exercises={exercises}
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
  /**
   * 기존 종목 선택·새 종목 생성/복원 완료 시 호출. 호출측이 여기서 시트를 닫아야 한다.
   * machine: 머신으로 찾아서 고른 경우 그 머신 — 호출측이 그 종목의 세트에 붙인다 (§15.4)
   */
  onSelect: (ex: Exercise, machine?: Machine) => void;
}

export default function ExercisePicker({ open, onClose, exercises, onSelect }: ExercisePickerProps) {
  const [q, setQ] = useState("");
  const [dq, setDq] = useState(""); // 머신 검색용 디바운스
  const [creating, setCreating] = useState(false);
  const [openRegion, setOpenRegion] = useState<Region | null>(null);
  const [recentIds, setRecentIds] = useState<number[]>(() => readRecent());
  const [machine, setMachine] = useState<Machine | null>(null);
  const [machineSearchOpen, setMachineSearchOpen] = useState(false);
  // 방금 고른 머신 id — 후보가 도착하면 "바로 시작"을 한 번만 판정한다 (판정 전에는 스피너)
  const [autoStartId, setAutoStartId] = useState<number | null>(null);
  const favorites = useFavorites();
  const mine = useMyMachines();
  const { regionOf, nameOf } = useTargets();

  useEffect(() => {
    if (open) {
      setRecentIds(readRecent()); // openGroup 등 외부 pushRecent 반영
    } else {
      setQ("");
      setCreating(false);
      setOpenRegion(null);
      setMachine(null);
      setMachineSearchOpen(false);
      setAutoStartId(null);
    }
  }, [open]);

  useEffect(() => {
    const t = setTimeout(() => setDq(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  const select = (ex: Exercise) => {
    setRecentIds(pushRecent(ex.id));
    onSelect(ex, machine ?? undefined);
  };

  const pickMachine = (m: Machine) => {
    setMachineSearchOpen(false);
    if (!mine.has(m.id)) void mine.add(m.id).catch(() => undefined);
    setAutoStartId(m.id);
    setMachine(m);
    setQ("");
    setCreating(false);
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

  // 종목 검색어로 머신도 함께 찾는다 — 머신 이름을 종목 검색창에 쳐도 길이 막히지 않게
  const machineHitsQ = useQuery({
    queryKey: ["machines", "quick", dq],
    queryFn: () => fetchMachines({ q: dq, limit: MACHINE_HITS }),
    enabled: open && machine == null && dq.length >= 2,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });
  const machineHits = query.length >= 2 && dq.length >= 2 ? (machineHitsQ.data ?? []) : [];

  const machineId = machine?.id ?? null;
  const candidatesQ = useQuery({
    queryKey: ["machine-exercises", machineId],
    queryFn: () => fetchMachineExercises(machineId as number),
    enabled: open && machineId != null,
    retry: 1, // 오프라인이면 오래 기다리게 하지 않고 검색으로 고르게 한다
  });
  const candidates = candidatesQ.data?.machine.id === machineId ? candidatesQ.data : undefined;

  // 바로 시작: 한 가지 동작용 머신 + 내가 그 머신으로 기록한 종목이 하나뿐. 캐시된 옛 후보로 판정하지
  // 않도록 재조회가 끝난 뒤에만 본다. 조회 실패면 후보 화면에 남는다(검색으로 고를 수 있다).
  // (select·byId는 판정하는 렌더의 값이면 충분해 의존성에 넣지 않는다)
  useEffect(() => {
    if (!machine || autoStartId !== machine.id) return;
    if (candidatesQ.isFetching) return;
    if (!candidates) {
      if (candidatesQ.isError) setAutoStartId(null);
      return;
    }
    setAutoStartId(null);
    if (machine.target == null || candidates.used.length !== 1) return;
    const ex = byId.get(candidates.used[0].exercise_id);
    if (ex) select(ex);
  }, [machine, autoStartId, candidates, candidatesQ.isFetching, candidatesQ.isError]);
  const awaitingAutoStart = machine != null && autoStartId === machine.id;

  const row = (e: Exercise, meta?: string) => (
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
          <span className="ml-auto shrink-0 text-xs text-muted">{meta ?? nameOf(e.default_target)}</span>
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

  const machineHitsSection =
    machineHits.length > 0 ? (
      <div className="mt-4">
        <p className={SECTION_LABEL}>머신으로 찾기</p>
        <ul className="divide-y divide-line/50">
          {machineHits.map((m) => (
            <li key={m.id}>
              <MachineRow machine={m} onClick={() => pickMachine(m)} />
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => setMachineSearchOpen(true)}
          className="touch-target w-full text-left text-xs font-semibold text-accent"
        >
          머신 검색에서 더 찾기 ›
        </button>
      </div>
    ) : null;

  const usedRows = (candidates?.used ?? [])
    .map((u) => ({ use: u, ex: byId.get(u.exercise_id) }))
    .filter((r): r is { use: typeof r.use; ex: Exercise } => r.ex != null);
  const suggestedRows = (candidates?.suggested ?? [])
    .map((id) => byId.get(id))
    .filter((e): e is Exercise => e != null);

  const machineBody = machine ? (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 rounded-row bg-well px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">
            <span className="mr-1.5 text-xs font-normal text-muted">머신</span>
            {machine.name_ko}
          </p>
          <p className="truncate text-xs text-muted">
            {machine.brand} · {machine.model}
            {machine.target ? ` · ${nameOf(machine.target)}` : ""}
          </p>
        </div>
        <button
          type="button"
          aria-label="머신 선택 취소"
          onClick={() => {
            setAutoStartId(null);
            setMachine(null);
            setQ("");
          }}
          className="touch-target shrink-0 text-muted"
        >
          ✕
        </button>
      </div>
      {awaitingAutoStart ? (
        <div className="flex min-h-[40dvh] items-start justify-center pt-6">
          <Spinner />
        </div>
      ) : (
        <>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="이 머신으로 할 종목 검색"
            className="min-h-12 rounded-xl border border-line bg-bg px-4"
          />
          {query ? (
            <div className="min-h-[40dvh]">
              {filtered.length === 0 ? (
                <p className="text-sm text-muted">검색 결과가 없습니다.</p>
              ) : (
                <ul>{filtered.slice(0, 60).map((e) => row(e))}</ul>
              )}
            </div>
          ) : (
            <div className="flex min-h-[30dvh] flex-col gap-4">
              {candidatesQ.isError && !candidates ? (
                <p className="text-sm text-muted">
                  추천을 불러오지 못했습니다. 위에서 종목을 검색해 고르면 이 머신으로 기록됩니다.
                </p>
              ) : null}
              {usedRows.length > 0 ? (
                <div>
                  <p className={SECTION_LABEL}>이 머신으로 기록한 종목</p>
                  <ul>
                    {usedRows.map(({ use, ex }) =>
                      row(ex, `${use.set_count}세트 · ${formatShortDate(use.last_date)}`),
                    )}
                  </ul>
                </div>
              ) : null}
              {suggestedRows.length > 0 ? (
                <div>
                  <p className={SECTION_LABEL}>{usedRows.length > 0 ? "다른 추천 종목" : "추천 종목"}</p>
                  <ul>{suggestedRows.map((e) => row(e))}</ul>
                </div>
              ) : null}
              {candidates && usedRows.length === 0 && suggestedRows.length === 0 ? (
                <p className="text-sm text-muted">
                  추천할 종목을 찾지 못했습니다. 위에서 검색해 고르거나 새 종목을 만드세요.
                </p>
              ) : null}
            </div>
          )}
          <Button variant="ghost" full onClick={() => setCreating(true)}>
            ＋ 맞는 종목이 없으면 새 종목 만들기
          </Button>
        </>
      )}
    </div>
  ) : null;

  return (
    <BottomSheet open={open} onClose={onClose} title="종목 선택">
      {creating ? (
        <NewExerciseForm
          // 머신으로 찾던 중이면 머신 이름·참고 타겟을 미리 채운다 (직접 친 검색어가 있으면 그쪽이 이름)
          initialName={q.trim() || (machine ? machine.name_ko.slice(0, 50) : "")}
          initialTarget={machine?.target}
          hint={
            machine
              ? "머신 이름과 참고 타겟을 채워 두었습니다. 고칠 곳이 있으면 고친 뒤 추가하세요. 만든 종목은 내 계정에서만 보입니다."
              : "내장 목록에 없는 종목만 추가하세요. 만든 종목은 내 계정에서만 보입니다."
          }
          exercises={exercises}
          onCreated={select}
          onCancel={() => setCreating(false)}
        />
      ) : machine ? (
        machineBody
      ) : (
        <div className="flex flex-col gap-4">
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="종목·머신 검색 (이름·별칭·태그·계열)"
            className="min-h-12 rounded-xl border border-line bg-bg px-4"
          />
          {query ? (
            // 검색으로 결과가 급감해도 시트 높이가 주저앉지 않게 최소 높이 유지
            <div className="min-h-[40dvh]">
              {filtered.length === 0 ? (
                <p className="text-sm text-muted">일치하는 종목이 없습니다.</p>
              ) : (
                <ul>{filtered.slice(0, 60).map((e) => row(e))}</ul>
              )}
              {machineHitsSection}
              {filtered.length === 0 ? (
                <Button variant="secondary" full className="mt-4" onClick={() => setCreating(true)}>
                  ＋ "{q.trim()}" 새 종목 만들기
                </Button>
              ) : null}
            </div>
          ) : (
            <>
              <div>
                <p className={SECTION_LABEL}>머신으로 찾기</p>
                <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
                  <button
                    type="button"
                    onClick={() => setMachineSearchOpen(true)}
                    className="touch-target shrink-0 rounded-full border border-dashed border-line-dashed px-4 text-sm text-muted active:bg-surface-2"
                  >
                    ＋ 머신 검색
                  </button>
                  {mine.machines.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => pickMachine(m)}
                      // 이름이 긴 머신 하나가 줄을 다 차지하지 않게 폭을 제한 (옆 칩이 보여야 넘겨 볼 줄 안다)
                      className="touch-target max-w-44 shrink-0 truncate rounded-full border border-line bg-surface-2 px-4 text-sm active:bg-line"
                    >
                      {m.name_ko}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className={SECTION_LABEL}>★ 즐겨찾기</p>
                {favoriteList.length === 0 ? (
                  <p className="px-1 py-2 text-xs text-faint">
                    목록에서 ☆를 눌러 자주 하는 종목을 여기에 모아 두세요.
                  </p>
                ) : (
                  <ul>{favoriteList.map((e) => row(e))}</ul>
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
                <p className={SECTION_LABEL}>전체 종목 · 부위별</p>
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
                        {opened ? <ul className="mt-1 pl-1">{list.map((e) => row(e))}</ul> : null}
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
      <MachinePicker
        open={machineSearchOpen}
        onClose={() => setMachineSearchOpen(false)}
        onPick={pickMachine}
        initialQuery={q.trim()}
      />
    </BottomSheet>
  );
}
