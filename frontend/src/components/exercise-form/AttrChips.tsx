// §3.6-7 속성 칩 표시 — Exercises 목록·상세용. 색은 시맨틱 토큰만 사용 (두 테마 공용).
import type { Exercise } from "../../api/types";
import { ATTR_KEYS } from "./attributeUtils";

export default function AttrChips({
  ex,
  className = "",
}: {
  ex: Exercise;
  className?: string;
}) {
  const chips = ATTR_KEYS.filter((k) => ex[k]).map((k) => ({
    key: k,
    value: ex[k] as string,
    isBase: k === "base_movement",
  }));
  if (chips.length === 0) return null;
  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {chips.map((c) => (
        <span
          key={c.key}
          className={`rounded-tag px-1.5 py-0.5 text-[10px] font-medium ${
            c.isBase ? "bg-accent-glow text-accent" : "bg-well text-muted"
          }`}
        >
          {c.value}
        </span>
      ))}
    </div>
  );
}
