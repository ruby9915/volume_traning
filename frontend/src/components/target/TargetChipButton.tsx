// §10.2 종목 카드·세트 편집 폼의 타겟 칩 — 탭하면 TargetSheet. 기록·세션 상세 공용.
import type { TargetCode } from "../../api/types";
import { useTargets } from "../../hooks/useTargets";

export default function TargetChipButton({
  value,
  defaultCode,
  onClick,
  label = "타겟",
}: {
  /** 현재 타겟 코드 */
  value: TargetCode;
  /** 종목 기본 타겟 — 같으면 muted, 다르면 accent 강조 (사용자가 바꿨다는 표시) */
  defaultCode?: TargetCode;
  onClick: () => void;
  label?: string;
}) {
  const { nameOf } = useTargets();
  const changed = defaultCode !== undefined && value !== defaultCode;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="세트 타겟 부위"
      className={`shrink-0 rounded-chip border px-2.5 py-1 text-[11px] font-semibold ${
        changed ? "border-accent/40 bg-accent-glow text-accent" : "border-line text-muted"
      }`}
    >
      {label} · {nameOf(value)}
    </button>
  );
}
