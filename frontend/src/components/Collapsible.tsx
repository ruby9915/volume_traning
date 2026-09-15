// 카드 접기/펼치기 래퍼 (2026-09-15 사용자 요청: 분석 탭 카드 전부).
// 접히면 제목 줄만 있는 얇은 카드를 그리고, 펼치면 자식 카드를 그대로 그린다.
// 자식 카드의 CardTitle은 useCollapseControl()로 "접기" 버튼을 받아 제목 옆에 놓는다 —
// 카드 본문을 건드리지 않고도 어느 카드든 감싸기만 하면 된다. 상태는 기기별로 기억(useCollapsed).
import { createContext, useContext, type ReactNode } from "react";
import { collapseLabel, useCollapsed } from "../hooks/useCollapsed";
import Card from "./Card";

interface CollapseControl {
  collapsed: boolean;
  toggle: () => void;
}

const CollapseContext = createContext<CollapseControl | null>(null);

/** 감싸인 카드 안에서 접기 버튼을 그릴 때 — 래퍼 밖이면 null */
export function useCollapseControl(): CollapseControl | null {
  return useContext(CollapseContext);
}

export function CollapseToggle({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={!collapsed}
      className="touch-target -my-2 -mr-2 shrink-0 px-2 text-xs font-semibold text-muted active:text-text"
    >
      {collapseLabel(collapsed)}
    </button>
  );
}

/** 래퍼 컨텍스트의 접기 버튼 — 제목 줄에 조절 버튼이 따로 있는 카드에서 맨 오른쪽에 둘 때 */
export function ContextToggle() {
  const ctl = useCollapseControl();
  if (!ctl) return null;
  return <CollapseToggle collapsed={ctl.collapsed} onToggle={ctl.toggle} />;
}

export default function Collapsible({
  id,
  title,
  note,
  children,
}: {
  /** localStorage 키 (vt_collapsed_<id>) */
  id: string;
  title: string;
  note?: string;
  children: ReactNode;
}) {
  const [collapsed, toggle] = useCollapsed(id);
  if (collapsed) {
    return (
      <Card>
        <div className="flex items-baseline justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-baseline gap-1.5">
            <h2 className="text-[15px] font-bold">{title}</h2>
            {note ? <span className="text-[11px] text-muted">· {note}</span> : null}
          </div>
          <CollapseToggle collapsed onToggle={toggle} />
        </div>
      </Card>
    );
  }
  return <CollapseContext.Provider value={{ collapsed: false, toggle }}>{children}</CollapseContext.Provider>;
}
