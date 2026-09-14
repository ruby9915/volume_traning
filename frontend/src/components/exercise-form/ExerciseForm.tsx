// §10.3 종목 생성·수정 폼 (v2) — 이름·계열·태그·기본 타겟·머신·고급(체중 계수·중량 배수).
// 종목 선택 시트의 "새 종목 만들기"와 종목 관리 화면이 공용으로 쓴다.
// 속성→부위/계수 자동 유도 없음, 이름 자동 조합 없음 (§3.6 반증·사용자 결정).
import { useMemo, useState } from "react";
import type { Exercise, ExerciseCreateRequest, TargetCode } from "../../api/types";
import { useTargets } from "../../hooks/useTargets";
import MachineField from "../machine/MachineField";
import TargetSheet from "../target/TargetSheet";
import { distinctBaseMovements, distinctTags, parseTags } from "./attributeUtils";

export interface ExerciseFormValues {
  name_ko: string;
  base_movement: string;
  tags: string[];
  default_target: TargetCode | null;
  secondary_targets: TargetCode[]; // §11.2 보조 근육 (간접 볼륨 후보)
  machine_id: number | null;
  machine_label: string | null; // 표시용 (편집 시 machine_name) — 요청 본문에는 안 들어간다
  bodyweight_factor: string;
  load_multiplier: string;
}

export const MAX_SECONDARY = 5;

export const EMPTY_FORM: ExerciseFormValues = {
  name_ko: "",
  base_movement: "",
  tags: [],
  default_target: null,
  secondary_targets: [],
  machine_id: null,
  machine_label: null,
  bodyweight_factor: "0",
  load_multiplier: "1",
};

export function formFromExercise(ex: Exercise): ExerciseFormValues {
  return {
    name_ko: ex.name_ko,
    base_movement: ex.base_movement ?? "",
    tags: ex.tags,
    default_target: ex.default_target,
    secondary_targets: ex.secondary_targets,
    machine_id: ex.machine_id,
    machine_label: ex.machine_name ?? null,
    bodyweight_factor: String(ex.bodyweight_factor),
    load_multiplier: String(ex.load_multiplier),
  };
}

/** 검증 후 요청 본문 생성. 오류면 문자열 반환 */
export function validateForm(v: ExerciseFormValues): ExerciseCreateRequest | string {
  const name = v.name_ko.trim();
  if (name.length < 1 || name.length > 50) return "이름은 1~50자로 입력하세요";
  if (!v.default_target) return "기본 타겟 부위를 선택하세요";
  const bw = Number(v.bodyweight_factor);
  if (!Number.isFinite(bw) || bw < 0 || bw > 1) return "체중 계수는 0~1 사이 숫자여야 합니다";
  const lm = Number(v.load_multiplier);
  if (!Number.isFinite(lm) || lm <= 0) return "중량 배수는 0보다 큰 숫자여야 합니다";
  if (v.tags.length > 20) return "태그는 20개 이하로 입력하세요";
  if (v.tags.some((t) => t.length > 30)) return "태그는 30자 이하로 입력하세요";
  const secondary = v.secondary_targets.filter((c) => c !== v.default_target);
  if (secondary.length > MAX_SECONDARY) return `보조 근육은 ${MAX_SECONDARY}개 이하로 선택하세요`;
  return {
    name_ko: name,
    base_movement: v.base_movement.trim() || null,
    tags: v.tags,
    default_target: v.default_target,
    secondary_targets: secondary,
    machine_id: v.machine_id,
    bodyweight_factor: bw,
    load_multiplier: lm,
  };
}

const INPUT_CLS =
  "mt-1 w-full rounded-field border border-transparent bg-well px-4 py-3 outline-none placeholder:text-faint focus:border-accent";

function SuggestInput({
  label,
  value,
  options,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  placeholder: string;
  onChange: (v: string) => void;
}) {
  const [focused, setFocused] = useState(false);
  const suggestions = useMemo(() => {
    const t = value.trim().toLowerCase();
    const list = t ? options.filter((o) => o.toLowerCase().includes(t) && o !== value.trim()) : options;
    return list.slice(0, 8);
  }, [value, options]);
  return (
    <label className="block min-w-0">
      <span className="text-sm text-muted">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder={placeholder}
        maxLength={50}
        className={INPUT_CLS}
      />
      {focused && suggestions.length > 0 ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {suggestions.map((o) => (
            <button
              key={o}
              type="button"
              onMouseDown={(e) => e.preventDefault()} // input blur 전에 값 선택이 동작하도록
              onClick={() => onChange(o)}
              className="rounded-chip bg-well px-3 py-1.5 text-xs text-secondary active:bg-surface-2"
            >
              {o}
            </button>
          ))}
        </div>
      ) : null}
    </label>
  );
}

/** 태그 상자 — 칩 + 입력(쉼표/Enter로 추가) + 자주 쓰는 태그 제안 */
function TagBox({
  tags,
  suggestions,
  onChange,
}: {
  tags: string[];
  suggestions: string[];
  onChange: (tags: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const next = parseTags(draft).filter((t) => !tags.includes(t));
    if (next.length) onChange([...tags, ...next]);
    setDraft("");
  };
  const remaining = suggestions.filter((s) => !tags.includes(s)).slice(0, 10);
  return (
    <div>
      <span className="text-sm text-muted">태그 (장비·자세·그립·각도 등, 선택)</span>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 rounded-field bg-well px-3 py-2">
        {tags.map((t) => (
          <span key={t} className="flex items-center gap-1 rounded-tag bg-surface px-2 py-1 text-xs text-secondary shadow-card">
            {t}
            <button
              type="button"
              aria-label={`${t} 태그 제거`}
              className="text-muted"
              onClick={() => onChange(tags.filter((x) => x !== t))}
            >
              ✕
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              commit();
            }
          }}
          onBlur={commit}
          placeholder={tags.length ? "" : "예: 바벨, 시티드"}
          className="min-w-[8ch] flex-1 bg-transparent py-1 outline-none placeholder:text-faint"
        />
      </div>
      {remaining.length > 0 ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {remaining.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onChange([...tags, s])}
              className="rounded-chip border border-line px-2.5 py-1 text-xs text-muted active:bg-surface-2"
            >
              + {s}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function ExerciseForm({
  values,
  onChange,
  exercises,
  advancedOpen,
  onToggleAdvanced,
}: {
  values: ExerciseFormValues;
  onChange: (next: ExerciseFormValues) => void;
  /** 자동완성 소스 (계열·태그) */
  exercises: Exercise[];
  advancedOpen: boolean;
  onToggleAdvanced: () => void;
}) {
  const { nameOf, muscleOf } = useTargets();
  const [targetOpen, setTargetOpen] = useState(false);
  const [secondaryOpen, setSecondaryOpen] = useState(false);
  const baseOptions = useMemo(() => distinctBaseMovements(exercises), [exercises]);
  const tagOptions = useMemo(() => distinctTags(exercises), [exercises]);
  const set = (patch: Partial<ExerciseFormValues>) => onChange({ ...values, ...patch });

  return (
    <div className="space-y-4">
      <label className="block">
        <span className="text-sm text-muted">이름</span>
        <input
          value={values.name_ko}
          onChange={(e) => set({ name_ko: e.target.value })}
          placeholder="예: 케이블 트라이셉스 푸시다운"
          maxLength={50}
          className={INPUT_CLS}
        />
      </label>

      <div>
        <span className="text-sm text-muted">기본 타겟 부위 (필수 — 기록할 때 세트마다 바꿀 수 있음)</span>
        <div className="mt-1.5">
          <button
            type="button"
            onClick={() => setTargetOpen(true)}
            className={`touch-target w-full rounded-field border px-4 text-left text-sm ${
              values.default_target ? "border-accent/40 bg-accent-glow font-semibold text-accent" : "border-line text-muted"
            }`}
          >
            {values.default_target ? nameOf(values.default_target) : "타겟 선택"}
          </button>
        </div>
      </div>

      <div>
        <span className="text-sm text-muted">보조 근육 (선택 — 고급 분석의 간접 볼륨에만 사용)</span>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {values.secondary_targets.map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => set({ secondary_targets: values.secondary_targets.filter((c) => c !== code) })}
              className="rounded-full border border-line bg-well px-3 py-1.5 text-xs text-secondary"
              aria-label={`${nameOf(code)} 제거`}
            >
              {nameOf(code)} ×
            </button>
          ))}
          {values.secondary_targets.length < MAX_SECONDARY ? (
            <button
              type="button"
              onClick={() => setSecondaryOpen(true)}
              className="rounded-full border border-dashed border-line-dashed px-3 py-1.5 text-xs text-muted"
            >
              + 추가
            </button>
          ) : null}
        </div>
        <span className="mt-1 block text-xs text-muted">
          기본 타겟과 같은 근육은 넣을 수 없습니다. 총볼륨·PR에는 영향이 없습니다.
        </span>
      </div>

      <SuggestInput
        label="계열 (선택 — 같은 동작끼리 분석에서 합산)"
        value={values.base_movement}
        options={baseOptions}
        placeholder="예: 푸시다운"
        onChange={(v) => set({ base_movement: v })}
      />

      <TagBox tags={values.tags} suggestions={tagOptions} onChange={(tags) => set({ tags })} />

      <MachineField
        value={values.machine_id}
        label={values.machine_label}
        onChange={(m) => set({ machine_id: m ? m.id : null, machine_label: m ? m.name_ko : null })}
      />

      <div>
        <button type="button" className="touch-target text-sm text-muted" onClick={onToggleAdvanced}>
          {advancedOpen ? "▾ 고급 설정" : "▸ 고급 설정"}
        </button>
        {advancedOpen ? (
          <div className="mt-2 space-y-3 rounded-well border border-line p-3">
            <label className="block">
              <span className="text-sm text-muted">체중 계수 (0~1)</span>
              <input
                value={values.bodyweight_factor}
                onChange={(e) => set({ bodyweight_factor: e.target.value })}
                inputMode="decimal"
                className={`${INPUT_CLS} font-numeric`}
              />
              <span className="mt-1 block text-xs text-muted">맨몸 운동이 유효 중량에 포함할 체중 비율 (풀업 1, 푸시업 0.65)</span>
            </label>
            <label className="block">
              <span className="text-sm text-muted">중량 배수</span>
              <input
                value={values.load_multiplier}
                onChange={(e) => set({ load_multiplier: e.target.value })}
                inputMode="decimal"
                className={`${INPUT_CLS} font-numeric`}
              />
              <span className="mt-1 block text-xs text-muted">양손 덤벨 동시 운동은 2 (한쪽 덤벨 무게로 입력)</span>
            </label>
          </div>
        ) : null}
      </div>

      <TargetSheet
        open={targetOpen}
        value={values.default_target}
        description="이 종목을 기록할 때 기본으로 선택될 부위입니다. 기록 중에 세트마다 바꿀 수 있습니다."
        onClose={() => setTargetOpen(false)}
        onSelect={(code) => {
          // 기본 타겟이 바뀌어 보조 근육과 같은 근육이 되면 그 보조 근육은 뺀다 (서버 불변식과 동일)
          set({
            default_target: code,
            secondary_targets: values.secondary_targets.filter((c) => muscleOf(c) !== muscleOf(code)),
          });
          setTargetOpen(false);
        }}
      />
      <TargetSheet
        open={secondaryOpen}
        value={null}
        description="이 종목이 간접적으로 쓰는 근육입니다. 고급 분석의 '관여 근육 분배'에서 간접 세트(기본 0.5)로만 집계됩니다."
        onClose={() => setSecondaryOpen(false)}
        onSelect={(code) => {
          setSecondaryOpen(false);
          if (values.default_target && muscleOf(code) === muscleOf(values.default_target)) return;
          if (values.secondary_targets.includes(code)) return;
          set({ secondary_targets: [...values.secondary_targets, code] });
        }}
      />
    </div>
  );
}
