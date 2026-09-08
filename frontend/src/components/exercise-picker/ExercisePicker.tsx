// 종목 선택 bottom sheet — Log에서 추출한 공용 컴포넌트 (§3.7B: 세션 상세에서도 재사용)
// 최근 칩 · 부위 그룹 · 검색(name_ko/name_en/aliases/속성값 haystack, §3.6) · 새 종목 승격 포함.
// 최근 사용 목록은 내부에서 localStorage로 관리: open 시 read, 선택 시 push.
// 시트는 선택 후 자동으로 닫히지 않는다 — 호출측이 onSelect에서 닫기(open=false) 처리.

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  apiErrorMessage,
  archivedConflictOf,
  createExercise,
  restoreExercise,
} from "../../api/client";
import type { Exercise, MuscleCode } from "../../api/types";
import { MUSCLE_GROUPS, MUSCLE_NAME_KO } from "../../api/types";
import BottomSheet from "../BottomSheet";
import Button from "../Button";
import AttributeBuilder from "../exercise-form/AttributeBuilder";
import {
  EMPTY_ATTRS,
  attrsToPayload,
  exerciseMatchesQuery,
  type AttrDraft,
} from "../exercise-form/attributeUtils";
import { pushRecent, readRecent } from "./recentExercises";

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
  const [name, setName] = useState(initialName);
  const [attrs, setAttrs] = useState<AttrDraft>(EMPTY_ATTRS);
  const [primary, setPrimary] = useState<MuscleCode[]>([]);
  const [secondary, setSecondary] = useState<MuscleCode[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const togglePrimary = (code: MuscleCode) => {
    setPrimary((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));
    setSecondary((prev) => prev.filter((c) => c !== code));
  };
  const toggleSecondary = (code: MuscleCode) => {
    setSecondary((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));
    setPrimary((prev) => prev.filter((c) => c !== code));
  };

  const create = async () => {
    const n = name.trim();
    if (!n) {
      setErr("종목 이름을 입력하세요");
      return;
    }
    if (primary.length === 0) {
      setErr("주동근을 1개 이상 선택하세요");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const ex = await createExercise({
        name_ko: n,
        muscles: [
          ...primary.map((code) => ({ code, role: "primary" as const })),
          ...secondary.map((code) => ({ code, role: "secondary" as const })),
        ],
        ...attrsToPayload(attrs),
      });
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

  const chip = (code: MuscleCode, on: boolean, onToggle: () => void) => (
    <button
      key={code}
      type="button"
      onClick={onToggle}
      className={`rounded-full border px-3 py-2 text-sm ${on ? "border-accent bg-accent/10 text-accent" : "border-line text-muted"}`}
    >
      {MUSCLE_NAME_KO[code]}
    </button>
  );

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-semibold">새 종목 만들기</p>
      <AttributeBuilder
        exercises={exercises}
        name={name}
        attrs={attrs}
        onNameChange={setName}
        onAttrsChange={setAttrs}
        initialNameTouched={initialName.trim() !== ""}
      />
      <div>
        <p className="mb-2 text-xs text-muted">주동근 (1개 이상)</p>
        <div className="flex flex-wrap gap-2">
          {MUSCLE_GROUPS.map((m) => chip(m.code, primary.includes(m.code), () => togglePrimary(m.code)))}
        </div>
      </div>
      <div>
        <p className="mb-2 text-xs text-muted">보조근 (선택)</p>
        <div className="flex flex-wrap gap-2">
          {MUSCLE_GROUPS.map((m) => chip(m.code, secondary.includes(m.code), () => toggleSecondary(m.code)))}
        </div>
      </div>
      <p className="text-xs text-muted">체중 계수 등 세부 설정은 종목 탭에서 수정할 수 있습니다.</p>
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
  const [recentIds, setRecentIds] = useState<number[]>(() => readRecent());

  useEffect(() => {
    if (open) {
      setRecentIds(readRecent()); // openGroup 등 외부 pushRecent 반영
    } else {
      setQ("");
      setCreating(false);
    }
  }, [open]);

  const select = (ex: Exercise) => {
    setRecentIds(pushRecent(ex.id));
    onSelect(ex);
  };

  const query = q.trim().toLowerCase();
  // §3.6 검색: name_ko / name_en / aliases / 속성값 전부 매칭
  const filtered = query ? exercises.filter((e) => exerciseMatchesQuery(e, query)) : exercises;

  const byId = new Map(exercises.map((e) => [e.id, e]));
  const recent = recentIds
    .map((id) => byId.get(id))
    .filter((e): e is Exercise => e != null)
    .slice(0, 8);

  const musclesLabel = (e: Exercise) => {
    const prim = e.muscles.filter((m) => m.role === "primary").map((m) => MUSCLE_NAME_KO[m.code]);
    const sec = e.muscles.filter((m) => m.role === "secondary").map((m) => MUSCLE_NAME_KO[m.code]);
    return prim.join("·") + (sec.length ? `/${sec.join("·")}` : "");
  };

  const grouped: { label: string; items: Exercise[] }[] = [];
  if (!query) {
    const map = new Map<string, Exercise[]>();
    for (const e of exercises) {
      const fp = MUSCLE_GROUPS.find((m) =>
        e.muscles.some((x) => x.role === "primary" && x.code === m.code),
      );
      const label = fp?.name_ko ?? "기타";
      const list = map.get(label);
      if (list) list.push(e);
      else map.set(label, [e]);
    }
    for (const m of MUSCLE_GROUPS) {
      const items = map.get(m.name_ko);
      if (items) grouped.push({ label: m.name_ko, items });
    }
    const etc = map.get("기타");
    if (etc) grouped.push({ label: "기타", items: etc });
  }

  const row = (e: Exercise) => (
    <li key={e.id}>
      <button
        type="button"
        onClick={() => select(e)}
        className="flex min-h-12 w-full items-center justify-between gap-2 border-b border-line/50 px-1 text-left active:bg-surface-2"
      >
        <span>{e.name_ko}</span>
        <span className="shrink-0 text-xs text-muted">{musclesLabel(e)}</span>
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
            placeholder="종목 검색"
            className="min-h-12 rounded-xl border border-line bg-bg px-4"
          />
          {query && filtered.length === 0 ? (
            <Button variant="secondary" full onClick={() => setCreating(true)}>
              ＋ "{q.trim()}" 새 종목 만들기
            </Button>
          ) : null}
          {!query && recent.length > 0 ? (
            <div>
              <p className="mb-2 text-xs text-muted">최근 사용</p>
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
          {query ? (
            // 검색으로 결과가 급감해도 시트 높이가 주저앉지 않게 최소 높이 유지
            // (키보드 위에서 input·결과 위치가 안정적으로 보이도록)
            <ul className="min-h-[40dvh]">{filtered.map(row)}</ul>
          ) : (
            grouped.map((g) => (
              <div key={g.label}>
                <p className="mb-1 text-xs font-semibold text-muted">{g.label}</p>
                <ul>{g.items.map(row)}</ul>
              </div>
            ))
          )}
          {!(query && filtered.length === 0) ? (
            <Button variant="ghost" full onClick={() => setCreating(true)}>
              ＋ 새 종목 만들기
            </Button>
          ) : null}
        </div>
      )}
    </BottomSheet>
  );
}
