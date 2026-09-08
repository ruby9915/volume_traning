import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { getToken } from "./api/client";
import TabBar from "./components/TabBar";
import ErrorBoundary from "./components/ErrorBoundary";
import Login from "./pages/Login";
import Log from "./pages/Log";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import SessionDetail from "./pages/SessionDetail";
import Exercises from "./pages/Exercises";
import Settings from "./pages/Settings";

function RequireAuth() {
  if (!getToken()) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function Shell() {
  const location = useLocation();
  return (
    <div className="min-h-dvh pb-20">
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
      <Route element={<RequireAuth />}>
        <Route element={<Shell />}>
          <Route path="/" element={<Navigate to="/log" replace />} />
          <Route path="/log" element={<Log />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/history" element={<History />} />
          {/* §3.7B 빈 날짜 기록 추가 — 세션 미생성 편집 화면 (정적 세그먼트가 :sessionId보다 우선 매칭) */}
          <Route path="/history/new" element={<SessionDetail />} />
          <Route path="/history/:sessionId" element={<SessionDetail />} />
          <Route path="/exercises" element={<Exercises />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/log" replace />} />
    </Routes>
  );
}
