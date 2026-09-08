// §3.6 생성/수정 UI 1~4 — Log NewExerciseForm · Exercises 폼 공용 속성 빌더
// ① 동작+속성 4종 자동완성(기존 값 distinct + 새 값 자유 입력) ② 이름 자동 조합
// ③ support 넛지 1회 ④ 동일 조합 경고(차단 아님). 속성→부위/계수 자동 유도는 하지 않는다(§3.6).

import { useMemo, useState } from "react";
import type { Exercise } from "../../api/types";
import {
  ATTR_KEYS,
  ATTR_LABELS,
  ATTR_PLACEHOLDERS,
  composeName,
  distinctAttrValues,
  findDuplicateCombo,
  type AttrDraft,
  type AttrKey,
} from "./attributeUtils";

const INPUT_CLS =
  "mt-1 w-full rounded-field border border-transparent bg-well px-4 py-3 outline-none placeholder:text-faint focus:border-accent";

function AttrInput({
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
    const list = t
      ? options.filter((o) => o.toLowerCase().includes(t) && o !== value.trim())
      : options;
    return list.slice(0, 6);
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
              // mousedown preventDefault: input blur 전에 값 선택이 동작하도록
              onMouseDown={(e) => e.preventDefault()}
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

export default function AttributeBuilder({
  exercises,
  excludeId,
  name,
  attrs,
  onNameChange,
  onAttrsChange,
  initialNameTouched = false,
}: {
  exercises: Exercise[];
  /** 수정 모드: 자기 자신은 중복 비교에서 제외 */
  excludeId?: number;
  name: string;
  attrs: AttrDraft;
  onNameChange: (name: string) => void;
  onAttrsChange: (attrs: AttrDraft) => void;
  /** true면 이름 자동 조합을 처음부터 중단 (수정 모드, 검색어 프리필 등) */
  initialNameTouched?: boolean;
}) {
  // 사용자가 이름 필드를 직접 건드리면 자동 갱신 중단 (§3.6-2)
  const [nameTouched, setNameTouched] = useState(initialNameTouched);
  // support 넛지는 1회만 (§3.6-3) — 닫거나 한 번 채우면 다시 표시하지 않음
  const [nudgeDismissed, setNudgeDismissed] = useState(false);

  const optionsByKey = useMemo(() => {
    const m = {} as Record<AttrKey, string[]>;
    for (const k of ATTR_KEYS) m[k] = distinctAttrValues(exercises, k);
    return m;
  }, [exercises]);

  const setAttr = (key: AttrKey, value: string) => {
    const next = { ...attrs, [key]: value };
    onAttrsChange(next);
    if (key === "support" && value.trim()) setNudgeDismissed(true);
    if (!nameTouched) {
      const composed = composeName(next);
      if (composed) onNameChange(composed);
    }
  };

  const duplicate = useMemo(
    () => findDuplicateCombo(exercises, attrs, excludeId),
    [exercises, attrs, excludeId],
  );
  const composed = composeName(attrs);
  const showNudge =
    !nudgeDismissed && attrs.base_movement.trim() !== "" && attrs.support.trim() === "";

  return (
    <div className="space-y-4">
      <AttrInput
        label={`${ATTR_LABELS.base_movement} (선택 — 같은 동작끼리 계열로 묶입니다)`}
        value={attrs.base_movement}
        options={optionsByKey.base_movement}
        placeholder={ATTR_PLACEHOLDERS.base_movement}
        onChange={(v) => setAttr("base_movement", v)}
      />

      <div className="grid grid-cols-2 gap-3">
        {(["equipment", "support", "grip", "angle"] as const).map((k) => (
          <AttrInput
            key={k}
            label={ATTR_LABELS[k]}
            value={attrs[k]}
            options={optionsByKey[k]}
            placeholder={ATTR_PLACEHOLDERS[k]}
            onChange={(v) => setAttr(k, v)}
          />
        ))}
      </div>

      {showNudge ? (
        <div className="flex items-start justify-between gap-2 rounded-well bg-accent-glow px-3 py-2.5">
          <p className="text-xs text-accent">
            자세(시티드/스탠딩 등)를 지정할까요? 나중에 같은 동작을 나눠 볼 때 도움이
            됩니다.
          </p>
          <button
            type="button"
            aria-label="넛지 닫기"
            className="shrink-0 px-1 text-xs font-bold text-accent"
            onClick={() => setNudgeDismissed(true)}
          >
            ✕
          </button>
        </div>
      ) : null}

      {duplicate ? (
        <div className="rounded-well border border-danger/40 px-3 py-2.5">
          <p className="text-xs text-secondary">
            같은 조합의 종목이 이미 있습니다:{" "}
            <span className="font-semibold text-text">{duplicate.name_ko}</span>
            <span className="text-muted"> — 의도한 것이면 그대로 진행해도 됩니다.</span>
          </p>
        </div>
      ) : null}

      <label className="block">
        <span className="text-sm text-muted">이름</span>
        <input
          value={name}
          onChange={(e) => {
            setNameTouched(true);
            onNameChange(e.target.value);
          }}
          placeholder="예: 케이블 로우"
          maxLength={50}
          className={INPUT_CLS}
        />
        {!nameTouched && composed ? (
          <span className="mt-1 block text-xs text-faint">
            속성에서 자동 조합된 이름 — 직접 수정할 수 있습니다
          </span>
        ) : null}
        {nameTouched && composed && composed !== name.trim() ? (
          <button
            type="button"
            className="mt-1 block text-left text-xs text-accent"
            onClick={() => {
              onNameChange(composed);
              setNameTouched(false);
            }}
          >
            제안 이름 적용: {composed}
          </button>
        ) : null}
      </label>

      <label className="block">
        <span className="text-sm text-muted">검색 별칭 (쉼표로 구분, 선택)</span>
        <input
          value={attrs.aliases}
          onChange={(e) => onAttrsChange({ ...attrs, aliases: e.target.value })}
          placeholder="예: 숄더프레스,밀리터리 프레스"
          maxLength={200}
          className={INPUT_CLS}
        />
      </label>
    </div>
  );
}
