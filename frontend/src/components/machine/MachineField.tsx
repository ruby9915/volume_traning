// §10.4 종목 폼의 머신 칸 — 내 머신 칩만 나열하고, 아카이브는 검색 시트로만 연다.
// 편집 중인 종목의 머신이 내 목록에 없어도(옛 종목·관리자 내장 종목) label로 칩을 보여 준다.
import { useState } from "react";
import type { Machine } from "../../api/types";
import { useMyMachines } from "../../hooks/useMyMachines";
import MachinePicker from "./MachinePicker";

const CHIP = "touch-target rounded-chip border px-3 text-sm";
const CHIP_ON = "border-accent/40 bg-accent-glow font-semibold text-accent";
const CHIP_OFF = "border-line text-muted active:bg-surface-2";

export default function MachineField({
  value,
  label,
  onChange,
}: {
  value: number | null;
  /** value에 해당하는 머신의 표시 이름 (내 목록에 없을 때 대비) */
  label: string | null;
  onChange: (m: Machine | null) => void;
}) {
  const mine = useMyMachines();
  const [open, setOpen] = useState(false);
  const inList = value !== null && mine.has(value);

  const pick = (m: Machine) => {
    setOpen(false);
    onChange(m);
    if (!mine.has(m.id)) void mine.add(m.id).catch(() => undefined);
  };

  return (
    <div>
      <span className="text-sm text-muted">머신 (선택 — 내 머신에서 고르기)</span>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        <button type="button" onClick={() => onChange(null)} className={`${CHIP} ${value === null ? CHIP_ON : CHIP_OFF}`}>
          없음
        </button>
        {value !== null && !inList && label ? (
          <button type="button" className={`${CHIP} ${CHIP_ON}`} onClick={() => undefined}>
            {label}
          </button>
        ) : null}
        {mine.machines.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => onChange(value === m.id ? null : m)}
            className={`${CHIP} ${value === m.id ? CHIP_ON : CHIP_OFF}`}
          >
            {m.name_ko}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={`${CHIP} border-dashed border-line-dashed text-muted`}
        >
          ＋ 검색해서 추가
        </button>
      </div>
      {mine.machines.length === 0 && value === null ? (
        <span className="mt-1 block text-xs text-faint">
          헬스장에 있는 머신을 검색해 담아 두면 다음부터 여기서 바로 고릅니다.
        </span>
      ) : null}
      <MachinePicker open={open} onClose={() => setOpen(false)} onPick={pick} />
    </div>
  );
}
