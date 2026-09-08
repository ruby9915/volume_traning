// §10.3 종목 메타 칩 표시 — 계열(accent) + 태그(muted) + 머신. 종목 목록·선택 시트 공용.
import type { Exercise } from "../../api/types";

export default function TagChips({ ex, className = "" }: { ex: Exercise; className?: string }) {
  const chips = [
    ...(ex.base_movement ? [{ key: "base", value: ex.base_movement, accent: true }] : []),
    ...ex.tags.map((t) => ({ key: `t-${t}`, value: t, accent: false })),
    ...(ex.machine_name ? [{ key: "machine", value: ex.machine_name, accent: false }] : []),
  ];
  if (chips.length === 0) return null;
  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {chips.map((c) => (
        <span
          key={c.key}
          className={`rounded-tag px-1.5 py-0.5 text-[10px] font-medium ${
            c.accent ? "bg-accent-glow text-accent" : "bg-well text-muted"
          }`}
        >
          {c.value}
        </span>
      ))}
    </div>
  );
}
