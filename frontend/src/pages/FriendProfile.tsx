// §13 다른 사용자의 프로필 (/u/:username) — 카드 + 관계 버튼, 친구(공개)면 그 사람의 분석 | 이력을 읽기 전용으로.
// 분석·이력·세션은 내 화면과 같은 컴포넌트를 SubjectProvider 아래에서 그린다(쿼리 키에 userId 포함).
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acceptFriendRequest,
  apiErrorMessage,
  declineFriendRequest,
  fetchProfile,
  removeFriend,
  requestFriend,
} from "../api/client";
import type { Profile } from "../api/types";
import Avatar from "../components/Avatar";
import Button from "../components/Button";
import Card from "../components/Card";
import ErrorRetry from "../components/ErrorRetry";
import Spinner from "../components/Spinner";
import ReadOnlySession from "../components/session/ReadOnlySession";
import { useMe } from "../hooks/useMe";
import { SubjectProvider } from "../subject";
import { fmtInt } from "../utils/format";
import Dashboard from "./Dashboard";
import History from "./History";

type View = "dashboard" | "history" | "session";

function RelationActions({ p }: { p: Profile }) {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["profile", p.username] });
    void qc.invalidateQueries({ queryKey: ["friends"] });
  };
  const request = useMutation({ mutationFn: () => requestFriend(p.username), onSuccess: refresh });
  const accept = useMutation({ mutationFn: () => acceptFriendRequest(p.request_id!), onSuccess: refresh });
  const decline = useMutation({ mutationFn: () => declineFriendRequest(p.request_id!), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => removeFriend(p.id), onSuccess: refresh });
  const busy = request.isPending || accept.isPending || decline.isPending || remove.isPending;
  const err = request.error ?? accept.error ?? decline.error ?? remove.error;

  let body: React.ReactNode;
  switch (p.relation) {
    case "friend":
      body = (
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            if (window.confirm(`${p.display_name}님과 친구를 끊을까요?`)) remove.mutate();
          }}
        >
          친구 끊기
        </Button>
      );
      break;
    case "pending_in":
      body = (
        <div className="flex gap-2">
          <Button full disabled={busy} onClick={() => accept.mutate()}>친구 요청 수락</Button>
          <Button variant="ghost" disabled={busy} onClick={() => decline.mutate()}>거절</Button>
        </div>
      );
      break;
    case "pending_out":
      body = (
        <Button variant="secondary" full disabled={busy} onClick={() => decline.mutate()}>
          요청 보냄 · 취소
        </Button>
      );
      break;
    default:
      body = (
        <Button full disabled={busy} onClick={() => request.mutate()}>
          친구 요청
        </Button>
      );
  }
  return (
    <div className="mt-4">
      {body}
      {err ? <p className="mt-2 text-sm text-danger">{apiErrorMessage(err, "처리하지 못했습니다")}</p> : null}
    </div>
  );
}

export default function FriendProfile({ view }: { view: View }) {
  const { username = "", sessionId } = useParams();
  const navigate = useNavigate();
  const me = useMe();
  const q = useQuery({ queryKey: ["profile", username], queryFn: () => fetchProfile(username), enabled: username !== "" });

  if (me.data && me.data.username === username) return <Navigate to="/profile" replace />;
  if (q.isPending)
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  if (q.isError)
    return (
      <main className="mx-auto max-w-[720px] p-4">
        <ErrorRetry className="py-10" onRetry={() => q.refetch()} />
      </main>
    );
  const p = q.data;
  const shared = p.relation === "friend" && p.stats !== null;
  const subject = { userId: p.id, username: p.username, displayName: p.display_name };

  return (
    <div className="mx-auto max-w-[720px]">
      <main className="p-4 pb-0">
        <header className="mb-3 flex items-center gap-2">
          <button
            type="button"
            aria-label="뒤로"
            onClick={() => navigate(-1)}
            className="touch-target -ml-3 rounded-xl text-2xl text-muted active:bg-surface-2"
          >
            ‹
          </button>
          <h1 className="min-w-0 flex-1 truncate text-[19px] font-extrabold">{p.display_name}</h1>
        </header>
        <Card>
          <div className="flex items-center gap-3">
            <Avatar avatar={p.avatar} name={p.display_name} size="lg" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-lg font-bold">{p.display_name}</p>
              <p className="truncate text-sm text-muted">@{p.username} · 가입 {p.created_at.slice(0, 10)}</p>
              {p.bio ? <p className="mt-1 text-sm">{p.bio}</p> : null}
            </div>
          </div>
          {p.stats ? (
            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              {[
                ["훈련", `${p.stats.training_weeks}주`],
                ["세션", fmtInt(p.stats.session_count)],
                ["세트", fmtInt(p.stats.set_count)],
                ["4주 볼륨", `${fmtInt(Math.round(p.stats.volume_4w / 1000))}k`],
              ].map(([k, v]) => (
                <div key={k} className="rounded-sub bg-well py-2">
                  <p className="font-numeric text-base font-bold">{v}</p>
                  <p className="text-[11px] text-muted">{k}</p>
                </div>
              ))}
            </div>
          ) : null}
          <RelationActions p={p} />
          {p.relation !== "friend" ? (
            <p className="mt-3 text-xs text-muted">친구가 되면 이 사용자의 분석·이력·체중을 읽기 전용으로 볼 수 있습니다.</p>
          ) : !shared ? (
            <p className="mt-3 text-xs text-muted">이 사용자는 기록을 친구에게 비공개로 두었습니다.</p>
          ) : null}
        </Card>
      </main>

      {shared ? (
        <SubjectProvider subject={subject}>
          {view === "session" && sessionId ? (
            <main className="p-4">
              <ReadOnlySession sessionId={Number(sessionId)} userId={p.id} />
            </main>
          ) : view === "history" ? (
            <History />
          ) : (
            <Dashboard />
          )}
        </SubjectProvider>
      ) : null}
    </div>
  );
}
