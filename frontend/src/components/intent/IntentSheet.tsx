// §3.7A 의도 주동근 선택 시트 — 12분류(MUSCLE_GROUPS) + "기본". 기록·세션 상세 공용.
import type { MuscleCode } from "../../api/types";
import { MUSCLE_GROUPS, MUSCLE_NAME_KO } from "../../api/types";
import BottomSheet from "../BottomSheet";

const OPTIONS: (MuscleCode | null)[] = [null, ...MUSCLE_GROUPS.map((m) => m.code)];

export default function IntentSheet({
  open,
  value,
  description,
  onClose,
  onSelect,
}: {
  open: boolean;
  /** 현재 카드의 의도 (null = 기본) — 체크 표시용 */
  value: MuscleCode | null;
  /** 화면별 안내 문구 (기록: 새 세션은 항상 기본 / 세션 상세: 이후 추가 세트에 적용) */
  description: string;
  onClose: () => void;
  onSelect: (code: MuscleCode | null) => void;
}) {
  return (
    <BottomSheet open={open} onClose={onClose} title="의도 주동근">
      <p className="mb-2 text-xs text-muted">{description}</p>
      <ul>
        {OPTIONS.map((code) => {
          const on = value === code;
          return (
            <li key={code ?? "default"}>
              <button
                type="button"
                onClick={() => onSelect(code)}
                className={`flex min-h-12 w-full items-center justify-between gap-2 border-b border-line/50 px-1 text-left active:bg-surface-2 ${
                  on ? "font-semibold text-accent" : ""
                }`}
              >
                <span>{code == null ? "기본 (종목 부위 매핑)" : MUSCLE_NAME_KO[code]}</span>
                {on ? <span aria-hidden="true">✓</span> : null}
              </button>
            </li>
          );
        })}
      </ul>
    </BottomSheet>
  );
}
