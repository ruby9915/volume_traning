// §3.7A 기록 의도 주동근 — 기록(Log)·세션 상세(SessionDetail) 공용 UI 조각.
import type { MuscleCode } from "../../api/types";
import { MUSCLE_GROUPS, MUSCLE_NAME_KO } from "../../api/types";

/** 세트 인라인 수정 폼의 의도 칩 행 — "기본"(null = 종목 매핑 사용) + 12분류 */
export function IntentChips({
  value,
  onChange,
}: {
  value: MuscleCode | null;
  onChange: (code: MuscleCode | null) => void;
}) {
  const chipCls = (on: boolean) =>
    `shrink-0 rounded-full border px-3 py-1.5 text-xs ${
      on ? "border-accent bg-accent/10 text-accent" : "border-line text-muted"
    }`;
  return (
    <div className="mt-3">
      <p className="mb-1.5 text-xs text-muted">의도 주동근</p>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        <button type="button" onClick={() => onChange(null)} className={chipCls(value == null)}>
          기본
        </button>
        {MUSCLE_GROUPS.map((m) => (
          <button
            key={m.code}
            type="button"
            onClick={() => onChange(m.code)}
            className={chipCls(value === m.code)}
          >
            {m.name_ko}
          </button>
        ))}
      </div>
    </div>
  );
}

/** 종목 카드 헤더의 의도 칩 — 기본 표시 "기본", 탭 → IntentSheet. 지정 시 accent 강조 */
export function IntentChipButton({
  value,
  onClick,
}: {
  value: MuscleCode | null;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="기록 의도 주동근"
      className={`shrink-0 rounded-chip border px-2.5 py-1 text-[11px] font-semibold ${
        value != null ? "border-accent/40 bg-accent-glow text-accent" : "border-line text-muted"
      }`}
    >
      의도 · {value != null ? MUSCLE_NAME_KO[value] : "기본"}
    </button>
  );
}
