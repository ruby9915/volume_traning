import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError, getToken, login, tokenRemainingDays } from "../api/client";
import Button from "../components/Button";
import Spinner from "../components/Spinner";

// §4.1: 토큰 잔여 수명이 7일 미만이면 재로그인 유도. null = 배너 불필요.
export function useReloginBanner(): { days: number; expired: boolean } | null {
  const [days] = useState(() => tokenRemainingDays());
  if (days == null || days >= 7) return null;
  return { days: Math.max(0, Math.floor(days)), expired: days <= 0 };
}

function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return "비밀번호가 올바르지 않습니다.";
    return `오류가 발생했습니다. (HTTP ${e.status})`;
  }
  return "서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.";
}

export default function Login() {
  const navigate = useNavigate();
  const banner = useReloginBanner();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // 유효 토큰 보유(잔여 7일 이상 또는 만료 정보 없음) → 자동 로그인
  if (getToken() && banner == null) {
    return <Navigate to="/log" replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    if (!password) {
      setError("비밀번호를 입력해 주세요.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await login(password);
      navigate("/log", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-[720px] flex-col justify-center px-[18px] py-6 safe-bottom">
      <p className="text-center font-numeric text-[13px] font-semibold tracking-[3px] text-accent uppercase">
        Volume
      </p>
      <h1 className="mt-1 text-center text-2xl font-extrabold">볼륨 트래킹</h1>
      <p className="mt-2 text-center text-sm text-muted">비밀번호를 입력해 로그인하세요</p>

      {banner != null && (
        <div className="mt-6 rounded-card border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-accent">
          {banner.expired
            ? "로그인이 만료되었습니다. 다시 로그인해 주세요."
            : `로그인 유효기간이 ${banner.days}일 남았습니다. 지금 재로그인하면 90일 연장됩니다.`}
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        <input
          type="password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setError(null);
          }}
          placeholder="비밀번호"
          autoComplete="current-password"
          autoFocus
          disabled={loading}
          aria-label="비밀번호"
          className="touch-target w-full rounded-btn border border-line bg-surface px-4 text-base shadow-card placeholder:text-faint focus:border-accent focus:outline-none disabled:opacity-40"
        />

        {error != null && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}

        <Button type="submit" size="lg" full disabled={loading || password.length === 0}>
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <Spinner size="sm" />
              로그인 중…
            </span>
          ) : (
            "로그인"
          )}
        </Button>
      </form>
    </main>
  );
}
