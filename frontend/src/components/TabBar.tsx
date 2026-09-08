import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/log", label: "기록" },
  { to: "/dashboard", label: "분석" },
  { to: "/history", label: "이력" },
  { to: "/exercises", label: "종목" },
];

/** 시안: 상단 헤어라인 + 활성 탭 accent 700 / 비활성 muted. 라이트 bg 흰색, 다크 bg색. */
export default function TabBar() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-hairline bg-tabbar safe-bottom">
      <div className="mx-auto flex max-w-[720px]">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `touch-target flex flex-1 flex-col items-center justify-center py-2 text-sm ${
                isActive ? "font-bold text-accent" : "text-muted"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
