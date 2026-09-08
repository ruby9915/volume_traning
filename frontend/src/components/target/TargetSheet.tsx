// §10.2 타겟 선택 시트 — 부위 → 근육 → 세부 3단계를 한 화면에. 어느 단계에서 골라도 된다.
// 기록·세션 상세(세트 타겟)와 종목 폼(기본 타겟)이 공용으로 쓴다.
import type { Region, TargetCode } from "../../api/types";
import { REGION_NAMES_KO } from "../../api/types";
import { useTargets } from "../../hooks/useTargets";
import BottomSheet from "../BottomSheet";

const REGION_ORDER = Object.keys(REGION_NAMES_KO) as Region[];

export default function TargetSheet({
  open,
  value,
  defaultCode,
  description,
  onClose,
  onSelect,
}: {
  open: boolean;
  /** 현재 선택 (체크 표시) */
  value: TargetCode | null;
  /** 있으면 맨 위에 "기본 (종목 기본 타겟: OOO)" 항목을 둔다 — 세트 타겟용 */
  defaultCode?: TargetCode;
  description?: string;
  onClose: () => void;
  onSelect: (code: TargetCode) => void;
}) {
  const { muscles, childrenOf, nameOf } = useTargets();
  const rowCls = (on: boolean) =>
    `flex min-h-11 w-full items-center justify-between gap-2 rounded-row px-2 text-left active:bg-surface-2 ${
      on ? "bg-accent-glow font-semibold text-accent" : ""
    }`;
  const chipCls = (on: boolean) =>
    `rounded-full border px-3 py-1.5 text-xs ${
      on ? "border-accent bg-accent/10 font-semibold text-accent" : "border-line text-secondary"
    }`;

  return (
    <BottomSheet open={open} onClose={onClose} title="타겟 부위">
      {description ? <p className="mb-2 text-xs text-muted">{description}</p> : null}
      {defaultCode !== undefined ? (
        <button type="button" onClick={() => onSelect(defaultCode)} className={rowCls(value === defaultCode)}>
          <span>
            기본 <span className="text-xs font-normal text-muted">종목 기본 타겟 · {nameOf(defaultCode)}</span>
          </span>
          {value === defaultCode ? <span aria-hidden="true">✓</span> : null}
        </button>
      ) : null}
      <div className="mt-2 flex flex-col gap-4 pb-2">
        {REGION_ORDER.map((region) => {
          const list = muscles.filter((m) => m.region === region);
          if (list.length === 0) return null;
          return (
            <section key={region}>
              <h3 className="mb-1 px-2 text-[11px] font-semibold tracking-wide text-faint uppercase">
                {REGION_NAMES_KO[region]}
              </h3>
              <ul className="flex flex-col gap-1">
                {list.map((m) => {
                  const details = childrenOf(m.code);
                  return (
                    <li key={m.code}>
                      <button type="button" onClick={() => onSelect(m.code)} className={rowCls(value === m.code)}>
                        <span>{m.name_ko}</span>
                        {value === m.code ? <span aria-hidden="true">✓</span> : null}
                      </button>
                      {details.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5 px-2 pt-1 pb-1.5">
                          {details.map((d) => (
                            <button
                              key={d.code}
                              type="button"
                              onClick={() => onSelect(d.code)}
                              className={chipCls(value === d.code)}
                            >
                              {d.name_ko}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
    </BottomSheet>
  );
}
