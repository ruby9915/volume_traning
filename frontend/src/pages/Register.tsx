// §10.1 회원가입 — 지인 대상 최소 폼. 가입 즉시 로그인된다.
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ApiError, getToken, register } from "../api/client";
import Button from "../components/Button";
import Spinner from "../components/Spinner";
import { AUTH_INPUT_CLS } from "./Login";

const USERNAME_RE = /^[A-Za-z0-9_.-]{2,32}$/;

function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 409) return "이미 사용 중인 아이디입니다.";
    if (typeof e.detail === "string") return e.detail;
    return `오류가 발생했습니다. (HTTP ${e.status})`;
  }
  return "서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.";
}

export default function Register() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (getToken()) return <Navigate to="/log" replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    const u = username.trim();
    if (!USERNAME_RE.test(u)) {
      setError("아이디는 영문·숫자·._- 2~32자로 입력해 주세요.");
      return;
    }
    if (password.length < 4) {
      setError("비밀번호는 4자 이상이어야 합니다.");
      return;
    }
    if (password !== confirm) {
      setError("비밀번호 확인이 일치하지 않습니다.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await register({ username: u, password, display_name: displayName.trim() || undefined });
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
      <h1 className="mt-1 text-center text-2xl font-extrabold">회원가입</h1>
      <p className="mt-2 text-center text-sm text-muted">아이디는 로그인에만 쓰이고 다른 사용자에게 보이지 않습니다</p>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-3">
        <input
          type="text"
          value={username}
          onChange={(e) => {
            setUsername(e.target.value);
            setError(null);
          }}
          placeholder="아이디 (영문·숫자, 2~32자)"
          autoComplete="username"
          autoCapitalize="none"
          autoFocus
          disabled={loading}
          aria-label="아이디"
          className={AUTH_INPUT_CLS}
        />
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="표시 이름 (선택)"
          autoComplete="nickname"
          disabled={loading}
          aria-label="표시 이름"
          className={AUTH_INPUT_CLS}
        />
        <input
          type="password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setError(null);
          }}
          placeholder="비밀번호 (4자 이상)"
          autoComplete="new-password"
          disabled={loading}
          aria-label="비밀번호"
          className={AUTH_INPUT_CLS}
        />
        <input
          type="password"
          value={confirm}
          onChange={(e) => {
            setConfirm(e.target.value);
            setError(null);
          }}
          placeholder="비밀번호 확인"
          autoComplete="new-password"
          disabled={loading}
          aria-label="비밀번호 확인"
          className={AUTH_INPUT_CLS}
        />

        {error != null && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}

        <Button type="submit" size="lg" full disabled={loading || !username || !password} className="mt-1">
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <Spinner size="sm" />
              가입 중…
            </span>
          ) : (
            "가입하고 시작"
          )}
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        이미 계정이 있나요?{" "}
        <Link to="/login" className="font-semibold text-accent">
          로그인
        </Link>
      </p>
    </main>
  );
}
