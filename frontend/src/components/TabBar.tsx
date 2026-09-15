import { NavLink, useLocation } from "react-router-dom";
import { useMe } from "../hooks/useMe";

// 2026-09-15: 이력 탭은 분석 탭 안의 세그먼트로 합쳤고(§13), 프로필 탭이 생겼다.
// match: 이 접두어로 시작하는 주소면 활성 (분석 = /dashboard·/history, 프로필 = /profile·/u/…)
const TABS = [
  { to: "/log", label: "기록", match: ["/log"] },
  { to: "/dashboard", label: "분석", match: ["/dashboard", "/history"] },
  { to: "/exercises", label: "종목", match: ["/exercises"] },
  { to: "/profile", label: "프로필", match: ["/profile", "/u/"] },
];

/** 시안: 상단 헤어라인 + 활성 탭 accent 700 / 비활성 muted. 라이트 bg 흰색, 다크 bg색.
 *  관리자에게만 "관리" 탭 추가 (§10.5). */
export default function TabBar() {
  const me = useMe();
  const { pathname } = useLocation();
  const tabs = me.data?.is_admin ? [...TABS, { to: "/admin", label: "관리", match: ["/admin"] }] : TABS;
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-hairline bg-tabbar safe-bottom">
      <div className="mx-auto flex max-w-[720px]">
        {tabs.map((tab) => {
          const active = tab.match.some((m) => pathname === m || pathname.startsWith(m.endsWith("/") ? m : `${m}/`));
          return (
            <NavLink
              key={tab.to}
              to={tab.to}
              aria-current={active ? "page" : undefined}
              className={`touch-target flex flex-1 flex-col items-center justify-center py-2 text-sm ${
                active ? "font-bold text-accent" : "text-muted"
              }`}
            >
              {tab.label}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
