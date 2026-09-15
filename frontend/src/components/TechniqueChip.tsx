// §14 운동 방식 칩 + 선택 시트 — 기록 화면 스테퍼, 세트 편집 폼 공용.
// 값 없음 = 일반 세트(칩은 muted "방식"), 값 있으면 accent 강조. 볼륨·PR 계산과 무관한 표시용 태그.
import { useState } from "react";
import { TECHNIQUE_HINTS_KO, TECHNIQUE_NAMES_KO, TECHNIQUES, type Technique } from "../api/types";
import BottomSheet from "./BottomSheet";

export function TechniqueBadge({ technique }: { technique: Technique | null | undefined }) {
  if (!technique) return null;
  return (
    <span className="shrink-0 rounded-tag border border-accent/30 px-1.5 py-0.5 text-[10px] font-semibold text-accent">
      {TECHNIQUE_NAMES_KO[technique]}
    </span>
  );
}

export default function TechniqueChip({
  value,
  onChange,
}: {
  value: Technique | null;
  onChange: (t: Technique | null) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="운동 방식"
        className={`touch-target shrink-0 rounded-chip border px-3 text-xs font-semibold ${
          value ? "border-accent/40 bg-accent-glow text-accent" : "border-line text-muted"
        }`}
      >
        {value ? TECHNIQUE_NAMES_KO[value] : "방식"}
      </button>
      <BottomSheet open={open} onClose={() => setOpen(false)} title="운동 방식">
        <ul className="flex flex-col gap-1.5">
          <li>
            <button
              type="button"
              onClick={() => {
                onChange(null);
                setOpen(false);
              }}
              className={`flex w-full items-center justify-between rounded-row px-3 py-3 text-left ${
                value === null ? "bg-accent-glow font-semibold text-accent" : "bg-well"
              }`}
            >
              <span>일반 세트</span>
              <span className="text-xs text-muted">방식 없음</span>
            </button>
          </li>
          {TECHNIQUES.map((t) => (
            <li key={t}>
              <button
                type="button"
                onClick={() => {
                  onChange(t);
                  setOpen(false);
                }}
                className={`flex w-full flex-col rounded-row px-3 py-3 text-left ${
                  value === t ? "bg-accent-glow" : "bg-well"
                }`}
              >
                <span className={`text-sm ${value === t ? "font-semibold text-accent" : "font-semibold"}`}>
                  {TECHNIQUE_NAMES_KO[t]}
                </span>
                <span className="text-xs text-muted">{TECHNIQUE_HINTS_KO[t]}</span>
              </button>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-faint">
          방식은 세트에 붙는 표시일 뿐 볼륨·PR 계산은 그대로입니다. 같은 종목에서는 다음 세트에도 유지되고, 종목을
          바꾸면 초기화됩니다.
        </p>
      </BottomSheet>
    </>
  );
}
