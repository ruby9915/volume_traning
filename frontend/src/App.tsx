import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { getToken } from "./api/client";
import TabBar from "./components/TabBar";
import ErrorBoundary from "./components/ErrorBoundary";
import UpdateBanner from "./components/UpdateBanner";
import { useMe } from "./hooks/useMe";
import Admin from "./pages/Admin";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Log from "./pages/Log";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import SessionDetail from "./pages/SessionDetail";
import Exercises from "./pages/Exercises";
import Settings from "./pages/Settings";
import Profile from "./pages/Profile";
import FriendProfile from "./pages/FriendProfile";

function RequireAuth() {
  if (!getToken()) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** §10.5 관리자 전용 — 일반 사용자는 기록 화면으로 (API도 403으로 막는다) */
function RequireAdmin() {
  const me = useMe();
  if (me.isLoading) return null;
  if (!me.data?.is_admin) return <Navigate to="/log" replace />;
  return <Outlet />;
}

function Shell() {
  const location = useLocation();
  return (
    <div className="min-h-dvh pb-20">
      <UpdateBanner />
      {/* 페이지 콘텐츠만 감싼다 — 한 화면이 죽어도 TabBar는 살아남아 다른 화면으로 이동 가능. */}
      <ErrorBoundary resetKey={location.pathname}>
        <Outlet />
      </ErrorBoundary>
      <TabBar />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route element={<RequireAuth />}>
        <Route element={<Shell />}>
          <Route path="/" element={<Navigate to="/log" replace />} />
          <Route path="/log" element={<Log />} />
          {/* 분석 탭 = 분석(대시보드) | 이력 세그먼트 — 주소는 예전 그대로 */}
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/history" element={<History />} />
          {/* §3.7B 빈 날짜 기록 추가 — 세션 미생성 편집 화면 (정적 세그먼트가 :sessionId보다 우선 매칭) */}
          <Route path="/history/new" element={<SessionDetail />} />
          <Route path="/history/:sessionId" element={<SessionDetail />} />
          <Route path="/exercises" element={<Exercises />} />
          <Route path="/settings" element={<Settings />} />
          {/* §13 프로필·친구 열람(읽기 전용) */}
          <Route path="/profile" element={<Profile />} />
          <Route path="/u/:username" element={<FriendProfile view="dashboard" />} />
          <Route path="/u/:username/dashboard" element={<FriendProfile view="dashboard" />} />
          <Route path="/u/:username/history" element={<FriendProfile view="history" />} />
          <Route path="/u/:username/history/:sessionId" element={<FriendProfile view="session" />} />
          <Route element={<RequireAdmin />}>
            <Route path="/admin" element={<Admin />} />
            <Route path="/admin/:userId" element={<Admin />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/log" replace />} />
    </Routes>
  );
}
