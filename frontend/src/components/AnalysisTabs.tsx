// 분석 탭 안의 세그먼트 — 분석(대시보드) | 이력. 2026-09-15 "이력과 분석 병합" 결정.
// 주소는 그대로(/dashboard, /history)라 기존 링크가 깨지지 않고, 친구 열람(/u/:username/…)에서도 같은 부품을 쓴다.
import { NavLink } from "react-router-dom";
import { useSubject } from "../subject";

export default function AnalysisTabs() {
  const { basePath } = useSubject();
  const items = [
    { to: `${basePath}/dashboard`, label: "분석" },
    { to: `${basePath}/history`, label: "이력" },
  ];
  return (
    <div className="mb-3 grid grid-cols-2 gap-1 rounded-field bg-surface p-1 shadow-card" role="tablist" aria-label="분석 · 이력">
      {items.map((it) => (
        <NavLink
          key={it.to}
          to={it.to}
          role="tab"
          className={({ isActive }) =>
            `touch-target flex items-center justify-center rounded-field text-sm transition-colors ${
              isActive ? "bg-text font-bold text-surface dark:bg-bg dark:text-text" : "font-medium text-muted"
            }`
          }
        >
          {it.label}
        </NavLink>
      ))}
    </div>
  );
}
