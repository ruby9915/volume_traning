// §15 종목 카드·세트 편집 폼의 머신 칩 — 탭하면 MachineSheet. 기록·세션 상세 공용.
// 머신이 있으면 accent, 없으면 점선 "＋ 머신" (타겟과 달리 머신은 없는 것이 흔한 기본 상태).
import type { MachineRef } from "../../api/types";

export default function MachineChipButton({
  value,
  onClick,
  className = "",
}: {
  value: MachineRef | null;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="세트 머신"
      className={`max-w-full min-w-0 truncate rounded-chip border px-2.5 py-1 text-[11px] font-semibold ${
        value
          ? "border-accent/40 bg-accent-glow text-accent"
          : "border-dashed border-line-dashed text-muted"
      } ${className}`}
    >
      {value ? `머신 · ${value.name_ko}` : "＋ 머신"}
    </button>
  );
}
