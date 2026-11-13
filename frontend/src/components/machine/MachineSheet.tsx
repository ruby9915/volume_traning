// §15.3 머신 선택 시트 — 종목 카드·세트의 머신을 고른다. 내 머신만 나열하고 아카이브는 검색 시트로 연다.
// 기록·세션 상세 공용. 시트는 선택 후 자동으로 닫히지 않는다 — 호출측이 onSelect에서 닫는다.
import { useMemo, useState } from "react";
import type { Machine, MachineRef, Region } from "../../api/types";
import { useMyMachines } from "../../hooks/useMyMachines";
import { useTargets } from "../../hooks/useTargets";
import BottomSheet from "../BottomSheet";
import Button from "../Button";
import Spinner from "../Spinner";
import MachinePicker from "./MachinePicker";
import MachineRow from "./MachineRow";

export default function MachineSheet({
  open,
  value,
  region,
  description,
  onClose,
  onSelect,
}: {
  open: boolean;
  /** 현재 선택 (null = 머신 없음) */
  value: MachineRef | null;
  /** 종목 기본 타겟의 부위 — 같은 부위의 머신을 앞에 둔다 */
  region?: Region | null;
  description?: string;
  onClose: () => void;
  onSelect: (machine: MachineRef | null) => void;
}) {
  const mine = useMyMachines();
  const { regionOf } = useTargets();
  const [searchOpen, setSearchOpen] = useState(false);

  // 같은 부위 머신 → 참고 타겟이 없는 장비(케이블·랙·벤치) → 나머지. 그룹 안은 담은 순서 그대로
  const sorted = useMemo(() => {
    const rank = (m: Machine) => {
      if (m.target == null) return 1;
      return region != null && regionOf(m.target) === region ? 0 : 2;
    };
    return [...mine.machines].sort((a, b) => rank(a) - rank(b));
  }, [mine.machines, region, regionOf]);

  const pickFromArchive = (m: Machine) => {
    setSearchOpen(false);
    if (!mine.has(m.id)) void mine.add(m.id).catch(() => undefined);
    onSelect({ id: m.id, name_ko: m.name_ko });
  };

  const rowCls = (on: boolean) =>
    `flex min-h-12 w-full items-center justify-between gap-2 rounded-row px-2 text-left active:bg-surface-2 ${
      on ? "bg-accent-glow font-semibold text-accent" : ""
    }`;
  const outsideList = value != null && !mine.has(value.id);

  return (
    <BottomSheet open={open} onClose={onClose} title="머신">
      {description ? <p className="mb-2 text-xs text-muted">{description}</p> : null}
      <ul className="flex flex-col gap-1">
        <li>
          <button type="button" onClick={() => onSelect(null)} className={rowCls(value == null)}>
            <span>
              머신 없음 <span className="text-xs font-normal text-muted">프리웨이트·기록 안 함</span>
            </span>
            {value == null ? <span aria-hidden="true">✓</span> : null}
          </button>
        </li>
        {outsideList ? (
          <li>
            <button type="button" onClick={() => onSelect(value)} className={rowCls(true)}>
              <span className="truncate">{value.name_ko}</span>
              <span aria-hidden="true">✓</span>
            </button>
          </li>
        ) : null}
        {sorted.map((m) => (
          <li key={m.id}>
            <MachineRow
              machine={m}
              selected={value?.id === m.id}
              onClick={() => onSelect({ id: m.id, name_ko: m.name_ko })}
            />
          </li>
        ))}
      </ul>
      {mine.isLoading ? (
        <div className="flex justify-center py-3">
          <Spinner size="sm" />
        </div>
      ) : mine.machines.length === 0 ? (
        <p className="px-2 py-2 text-xs text-faint">
          헬스장에 있는 머신을 검색해 고르면 내 머신에 담겨 다음부터 여기서 바로 고릅니다.
        </p>
      ) : null}
      <Button variant="secondary" full className="mt-3" onClick={() => setSearchOpen(true)}>
        ＋ 머신 검색해서 고르기
      </Button>
      <MachinePicker open={searchOpen} onClose={() => setSearchOpen(false)} onPick={pickFromArchive} />
    </BottomSheet>
  );
}
