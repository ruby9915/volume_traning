import { NavLink } from "react-router-dom";
import { useMe } from "../hooks/useMe";

const TABS = [
  { to: "/log", label: "기록" },
  { to: "/dashboard", label: "분석" },
  { to: "/history", label: "이력" },
  { to: "/exercises", label: "종목" },
];

/** 시안: 상단 헤어라인 + 활성 탭 accent 700 / 비활성 muted. 라이트 bg 흰색, 다크 bg색.
 *  관리자에게만 "관리" 탭 추가 (§10.5). */
export default function TabBar() {
  const me = useMe();
  const tabs = me.data?.is_admin ? [...TABS, { to: "/admin", label: "관리" }] : TABS;
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-hairline bg-tabbar safe-bottom">
      <div className="mx-auto flex max-w-[720px]">
        {tabs.map((tab) => (
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
