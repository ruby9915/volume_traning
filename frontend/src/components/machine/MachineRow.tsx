// §10.4·§15 머신 한 줄 — 한글 이름 / 브랜드 · 모델 / 참고 타겟. 검색 시트·머신 시트·종목 선택 시트 공용.
import type { ReactNode } from "react";
import type { Machine } from "../../api/types";
import { useTargets } from "../../hooks/useTargets";

export default function MachineRow({
  machine,
  onClick,
  selected = false,
  trailing,
}: {
  machine: Machine;
  onClick: () => void;
  selected?: boolean;
  /** 참고 타겟 대신 오른쪽에 둘 내용 */
  trailing?: ReactNode;
}) {
  const { nameOf } = useTargets();
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`flex min-h-12 w-full items-center justify-between gap-3 rounded-row px-2 py-2 text-left active:bg-surface-2 ${
        selected ? "bg-accent-glow" : ""
      }`}
    >
      <span className="min-w-0">
        <span className={`block truncate text-sm font-semibold ${selected ? "text-accent" : ""}`}>
          {machine.name_ko}
        </span>
        <span className="block truncate text-xs text-muted">
          {machine.brand} · {machine.model}
        </span>
      </span>
      {trailing ??
        (machine.target ? (
          <span className="shrink-0 rounded-chip border border-line px-2 py-0.5 text-[11px] text-muted">
            {nameOf(machine.target)}
          </span>
        ) : null)}
    </button>
  );
}
