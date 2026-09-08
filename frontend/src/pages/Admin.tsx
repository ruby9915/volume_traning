// §10.5 관리자 페이지 — 사용자 목록과 각 사용자의 기록을 읽기만 한다.
// 시스템 수정 기능 없음 (사용자 결정: 시스템 수정은 작업 PC에서 직접).
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  fetchAdminUserBodyweight,
  fetchAdminUserSession,
  fetchAdminUserSessions,
  fetchAdminUsers,
} from "../api/client";
import type { AdminUser, SessionSummary } from "../api/types";
import Card from "../components/Card";
import ErrorRetry from "../components/ErrorRetry";
import Spinner from "../components/Spinner";
import { useTargets } from "../hooks/useTargets";
import { formatFullDate, formatKoreanDate } from "../utils/date";
import { fmtInt } from "../utils/format";
import { SessionCard } from "./History";

function Loading() {
  return (
    <div className="flex justify-center py-10">
      <Spinner />
    </div>
  );
}

function PageTitle({ children }: { children: string }) {
  return (
    <h1>
      <span className="text-[19px] font-extrabold dark:hidden">{children}</span>
      <span className="hidden font-numeric text-[13px] font-semibold uppercase tracking-[3px] text-muted dark:inline">
        ADMIN
      </span>
    </h1>
  );
}

function UserRow({ u }: { u: AdminUser }) {
  return (
    <Link
      to={`/admin/${u.id}`}
      className="flex items-center gap-3 border-t border-hairline px-4 py-3 first:border-t-0 active:bg-surface-2"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-semibold">{u.display_name}</span>
          <span className="truncate text-xs text-muted">@{u.username}</span>
          {u.is_admin ? (
            <span className="shrink-0 rounded-tag bg-accent-glow px-1.5 py-0.5 text-[10px] font-bold text-accent">
              관리자
            </span>
          ) : null}
        </div>
        <div className="mt-0.5 font-numeric text-xs text-muted">
          세션 {fmtInt(u.session_count)} · 세트 {fmtInt(u.set_count)}
          {u.last_date ? ` · 마지막 ${formatKoreanDate(u.last_date)}` : " · 기록 없음"}
        </div>
      </div>
      <span className="text-faint">›</span>
    </Link>
  );
}

function UsersList() {
  const q = useQuery({ queryKey: ["admin", "users"], queryFn: fetchAdminUsers });
  return (
    <main className="mx-auto max-w-[720px] p-4">
      <header className="flex min-h-9 items-center">
        <PageTitle>관리</PageTitle>
      </header>
      <p className="mt-1 text-xs text-muted">사용자 데이터를 열람만 합니다. 수정은 작업 PC에서 직접.</p>
      <div className="mt-4 overflow-hidden rounded-card bg-surface shadow-card">
        {q.isPending ? (
          <Loading />
        ) : q.isError ? (
          <ErrorRetry className="py-10" onRetry={() => q.refetch()} />
        ) : (
          q.data.map((u) => <UserRow key={u.id} u={u} />)
        )}
      </div>
    </main>
  );
}

function SessionDetailView({ userId, session }: { userId: number; session: SessionSummary }) {
  const { nameOf } = useTargets();
  const q = useQuery({
    queryKey: ["admin", "session", userId, session.id],
    queryFn: () => fetchAdminUserSession(userId, session.id),
  });
  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorRetry onRetry={() => q.refetch()} />;
  return (
    <div className="mb-3 flex flex-col gap-2 rounded-sub bg-well p-3">
      {q.data.exercises.map((g) => (
        <div key={g.exercise_id}>
          <div className="flex items-baseline justify-between">
            <span className="font-semibold">{g.name_ko}</span>
            <span className="font-numeric text-xs text-muted">{g.sets.length}세트</span>
          </div>
          <p className="mt-0.5 font-numeric text-sm text-muted">
            {g.sets
              .map((s) => `${s.is_warmup ? "W " : ""}${s.weight_kg}×${s.reps}${s.target !== g.default_target ? `(${nameOf(s.target)})` : ""}`)
              .join(" · ")}
          </p>
        </div>
      ))}
      {q.data.exercises.length === 0 ? <p className="text-sm text-muted">세트 없음</p> : null}
    </div>
  );
}

function UserDetail({ userId }: { userId: number }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState<number | null>(null);
  const users = useQuery({ queryKey: ["admin", "users"], queryFn: fetchAdminUsers });
  const sessions = useQuery({
    queryKey: ["admin", "sessions", userId],
    queryFn: () => fetchAdminUserSessions(userId, { limit: 100 }),
  });
  const bodyweight = useQuery({
    queryKey: ["admin", "bodyweight", userId],
    queryFn: () => fetchAdminUserBodyweight(userId),
  });
  const user = users.data?.find((u) => u.id === userId);

  return (
    <main className="mx-auto max-w-[720px] p-4">
      <header className="mb-4 flex items-center gap-2">
        <button
          type="button"
          aria-label="사용자 목록으로"
          onClick={() => navigate("/admin")}
          className="touch-target flex items-center justify-center rounded-row text-xl text-muted active:bg-surface-2"
        >
          ←
        </button>
        <h1 className="min-w-0 flex-1 truncate text-[19px] font-extrabold">
          {user ? user.display_name : `사용자 ${userId}`}
          {user ? <span className="ml-2 text-sm font-normal text-muted">@{user.username}</span> : null}
        </h1>
      </header>

      <Card className="mb-4">
        <p className="text-xs font-semibold text-muted">요약</p>
        <p className="mt-1 font-numeric text-sm">
          세션 {fmtInt(user?.session_count ?? 0)} · 세트 {fmtInt(user?.set_count ?? 0)}
          {bodyweight.data?.[0] ? ` · 체중 ${bodyweight.data[0].weight_kg}kg (${formatKoreanDate(bodyweight.data[0].date)})` : ""}
        </p>
        {user?.created_at ? (
          <p className="mt-1 text-xs text-muted">가입 {user.created_at.slice(0, 10)}</p>
        ) : null}
      </Card>

      {sessions.isPending ? (
        <Loading />
      ) : sessions.isError ? (
        <ErrorRetry className="py-10" onRetry={() => sessions.refetch()} />
      ) : sessions.data.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted">기록된 세션이 없습니다.</p>
      ) : (
        sessions.data.map((s) => (
          <div key={s.id}>
            <p className="mb-1 font-numeric text-xs font-semibold text-muted">{formatFullDate(s.date)}</p>
            <SessionCard session={s} onClick={() => setOpen(open === s.id ? null : s.id)} />
            {open === s.id ? <SessionDetailView userId={userId} session={s} /> : null}
          </div>
        ))
      )}
    </main>
  );
}

export default function Admin() {
  const { userId } = useParams();
  const id = userId === undefined ? null : Number(userId);
  if (id === null || !Number.isFinite(id)) return <UsersList />;
  return <UserDetail userId={id} />;
}
