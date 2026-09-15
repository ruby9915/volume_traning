// §13 프로필 탭 — 내 카드(편집), 친구(아이디 검색·요청·수락·목록), 계정(비밀번호·로그아웃).
// 친구는 요청 → 수락의 양방향. 수락된 친구는 /u/:username 에서 내 분석·이력·체중을 읽기 전용으로 본다.
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  acceptFriendRequest,
  apiErrorMessage,
  changePassword,
  declineFriendRequest,
  fetchFriends,
  fetchProfile,
  logout,
  removeFriend,
  requestFriend,
  searchUsers,
  updateProfile,
} from "../api/client";
import type { FriendUser, FriendsOut, ProfileUpdateRequest, User } from "../api/types";
import Avatar from "../components/Avatar";
import Button from "../components/Button";
import Card from "../components/Card";
import ErrorRetry from "../components/ErrorRetry";
import Spinner from "../components/Spinner";
import { useMe } from "../hooks/useMe";
import { fmtInt } from "../utils/format";

const FIELD_CLS =
  "touch-target w-full rounded-row border border-line bg-well px-4 text-base placeholder:text-faint focus:border-accent focus:outline-none";
const AVATARS = ["🦍", "🐺", "🦁", "🐻", "🦈", "🔥", "⚡", "🏋️", "💪", "🎯", "🌙", "☀️"];

function SectionTitle({ children }: { children: string }) {
  return <h2 className="mb-2 text-xs font-semibold tracking-wide text-muted">{children}</h2>;
}

function ChoiceButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`touch-target rounded-btn border px-3 text-sm font-semibold transition-colors ${
        active ? "border-accent bg-accent/15 text-accent" : "border-line bg-surface-2 text-muted active:bg-line"
      }`}
    >
      {children}
    </button>
  );
}

// ---------- 내 카드 ----------

function ProfileEditor({ me, onDone }: { me: User; onDone: () => void }) {
  const qc = useQueryClient();
  const [displayName, setDisplayName] = useState(me.display_name);
  const [bio, setBio] = useState(me.bio ?? "");
  const [avatar, setAvatar] = useState<string | null>(me.avatar);
  const [share, setShare] = useState(me.share_with_friends);
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (body: ProfileUpdateRequest) => updateProfile(body),
    onSuccess: (user) => {
      qc.setQueryData(["me"], user);
      void qc.invalidateQueries({ queryKey: ["profile"] });
      onDone();
    },
    onError: (e) => setErr(apiErrorMessage(e, "저장하지 못했습니다")),
  });
  const submit = () => {
    if (!displayName.trim()) {
      setErr("표시 이름을 입력하세요");
      return;
    }
    save.mutate({ display_name: displayName.trim(), bio: bio.trim() || null, avatar, share_with_friends: share });
  };
  return (
    <div className="mt-3 flex flex-col gap-3">
      <label className="block">
        <span className="text-sm text-muted">표시 이름</span>
        <input id="profile-display-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={50} className={`${FIELD_CLS} mt-1`} />
      </label>
      <label className="block">
        <span className="text-sm text-muted">한 줄 소개 (선택)</span>
        <input id="profile-bio" value={bio} onChange={(e) => setBio(e.target.value)} maxLength={120} placeholder="예: 5분할 · 등 이두 위주" className={`${FIELD_CLS} mt-1`} />
      </label>
      <div>
        <span className="text-sm text-muted">아바타</span>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setAvatar(null)}
            className={`touch-target rounded-chip border px-3 text-sm ${avatar === null ? "border-accent/40 bg-accent-glow font-semibold text-accent" : "border-line text-muted"}`}
          >
            이니셜
          </button>
          {AVATARS.map((a) => (
            <button
              key={a}
              type="button"
              onClick={() => setAvatar(a)}
              aria-label={`아바타 ${a}`}
              className={`touch-target rounded-chip border px-2.5 text-lg ${avatar === a ? "border-accent/40 bg-accent-glow" : "border-line"}`}
            >
              {a}
            </button>
          ))}
        </div>
      </div>
      <div>
        <span className="text-sm text-muted">친구에게 내 기록 공개</span>
        <div className="mt-1.5 grid grid-cols-2 gap-2">
          <ChoiceButton active={share} onClick={() => setShare(true)}>공개</ChoiceButton>
          <ChoiceButton active={!share} onClick={() => setShare(false)}>비공개</ChoiceButton>
        </div>
        <p className="mt-1 text-xs text-muted">공개면 수락된 친구가 내 분석·이력·체중을 읽기 전용으로 봅니다. 수정은 못 합니다.</p>
      </div>
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      <div className="flex gap-2">
        <Button variant="ghost" onClick={onDone} disabled={save.isPending}>취소</Button>
        <Button full onClick={submit} disabled={save.isPending}>{save.isPending ? <Spinner size="sm" /> : "저장"}</Button>
      </div>
    </div>
  );
}

function MyCard({ me }: { me: User }) {
  const [editing, setEditing] = useState(false);
  const profile = useQuery({ queryKey: ["profile", me.username], queryFn: () => fetchProfile(me.username), staleTime: 60_000 });
  const stats = profile.data?.stats;
  return (
    <Card>
      <div className="flex items-center gap-3">
        <Avatar avatar={me.avatar} name={me.display_name} size="lg" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg font-bold">
            {me.display_name}
            {me.is_admin ? (
              <span className="ml-2 rounded-tag bg-accent-glow px-1.5 py-0.5 align-middle text-[10px] font-bold text-accent">관리자</span>
            ) : null}
          </p>
          <p className="truncate text-sm text-muted">@{me.username} · 가입 {me.created_at.slice(0, 10)}</p>
          {me.bio ? <p className="mt-1 text-sm">{me.bio}</p> : null}
        </div>
      </div>
      {stats ? (
        <div className="mt-4 grid grid-cols-4 gap-2 text-center">
          {[
            ["훈련", `${stats.training_weeks}주`],
            ["세션", fmtInt(stats.session_count)],
            ["세트", fmtInt(stats.set_count)],
            ["4주 볼륨", `${fmtInt(Math.round(stats.volume_4w / 1000))}k`],
          ].map(([k, v]) => (
            <div key={k} className="rounded-sub bg-well py-2">
              <p className="font-numeric text-base font-bold">{v}</p>
              <p className="text-[11px] text-muted">{k}</p>
            </div>
          ))}
        </div>
      ) : null}
      {editing ? (
        <ProfileEditor me={me} onDone={() => setEditing(false)} />
      ) : (
        <Button variant="secondary" full className="mt-4" onClick={() => setEditing(true)}>
          프로필 편집
        </Button>
      )}
      {!me.share_with_friends ? (
        <p className="mt-2 text-xs text-muted">현재 기록을 친구에게 비공개로 두고 있습니다.</p>
      ) : null}
    </Card>
  );
}

// ---------- 친구 ----------

function UserRow({ user, action }: { user: FriendUser; action?: React.ReactNode }) {
  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <Link to={`/u/${encodeURIComponent(user.username)}`} className="flex min-w-0 flex-1 items-center gap-2.5">
        <Avatar avatar={user.avatar} name={user.display_name} size="sm" />
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold">{user.display_name}</span>
          <span className="block truncate text-xs text-muted">@{user.username}{user.bio ? ` · ${user.bio}` : ""}</span>
        </span>
      </Link>
      {action}
    </li>
  );
}

function SmallButton({ children, onClick, disabled, danger }: { children: string; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`touch-target shrink-0 rounded-btn border px-3 text-sm font-semibold disabled:opacity-40 ${
        danger ? "border-line text-muted" : "border-accent/40 bg-accent-glow text-accent"
      }`}
    >
      {children}
    </button>
  );
}

function FriendsSection() {
  const qc = useQueryClient();
  const friendsQ = useQuery({ queryKey: ["friends"], queryFn: fetchFriends, staleTime: 30_000 });
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDq(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);
  const searchQ = useQuery({ queryKey: ["users", "search", dq], queryFn: () => searchUsers(dq), enabled: dq.length >= 2 });

  const apply = (data: FriendsOut) => {
    qc.setQueryData(["friends"], data);
    void qc.invalidateQueries({ queryKey: ["users", "search"] });
    void qc.invalidateQueries({ queryKey: ["profile"] });
  };
  const onError = (e: unknown) => setMsg(apiErrorMessage(e, "처리하지 못했습니다"));
  const request = useMutation({ mutationFn: requestFriend, onSuccess: apply, onError });
  const accept = useMutation({ mutationFn: acceptFriendRequest, onSuccess: apply, onError });
  const decline = useMutation({ mutationFn: declineFriendRequest, onSuccess: apply, onError });
  const remove = useMutation({ mutationFn: removeFriend, onSuccess: apply, onError });
  const busy = request.isPending || accept.isPending || decline.isPending || remove.isPending;

  const actionFor = (u: FriendUser) => {
    switch (u.relation) {
      case "friend":
        return <span className="text-xs text-muted">친구</span>;
      case "pending_out":
        return <SmallButton danger disabled={busy} onClick={() => u.request_id && decline.mutate(u.request_id)}>요청 취소</SmallButton>;
      case "pending_in":
        return <SmallButton disabled={busy} onClick={() => u.request_id && accept.mutate(u.request_id)}>수락</SmallButton>;
      default:
        return <SmallButton disabled={busy} onClick={() => request.mutate(u.username)}>친구 요청</SmallButton>;
    }
  };

  const data = friendsQ.data;
  return (
    <Card>
      <SectionTitle>친구</SectionTitle>
      <input
        id="friend-search"
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="아이디로 찾기 (2자 이상)"
        autoComplete="off"
        className={FIELD_CLS}
      />
      {dq.length >= 2 ? (
        <div className="mt-2">
          {searchQ.isLoading ? (
            <div className="flex justify-center py-3"><Spinner size="sm" /></div>
          ) : searchQ.isError ? (
            <ErrorRetry onRetry={() => searchQ.refetch()} />
          ) : (searchQ.data ?? []).length === 0 ? (
            <p className="py-2 text-sm text-muted">일치하는 사용자가 없습니다.</p>
          ) : (
            <ul className="divide-y divide-line">{(searchQ.data ?? []).map((u) => <UserRow key={u.id} user={u} action={actionFor(u)} />)}</ul>
          )}
        </div>
      ) : null}
      {msg ? <p className="mt-2 text-sm text-danger">{msg}</p> : null}

      {friendsQ.isLoading ? (
        <div className="flex justify-center py-4"><Spinner size="sm" /></div>
      ) : friendsQ.isError || !data ? (
        <ErrorRetry className="py-4" onRetry={() => friendsQ.refetch()} />
      ) : (
        <>
          {data.incoming.length > 0 ? (
            <div className="mt-4">
              <p className="text-xs font-semibold text-muted">받은 요청 <span className="font-numeric text-accent">{data.incoming.length}</span></p>
              <ul className="divide-y divide-line">
                {data.incoming.map((r) => (
                  <UserRow
                    key={r.request_id}
                    user={r.user}
                    action={
                      <span className="flex gap-1.5">
                        <SmallButton disabled={busy} onClick={() => accept.mutate(r.request_id)}>수락</SmallButton>
                        <SmallButton danger disabled={busy} onClick={() => decline.mutate(r.request_id)}>거절</SmallButton>
                      </span>
                    }
                  />
                ))}
              </ul>
            </div>
          ) : null}
          {data.outgoing.length > 0 ? (
            <div className="mt-4">
              <p className="text-xs font-semibold text-muted">보낸 요청</p>
              <ul className="divide-y divide-line">
                {data.outgoing.map((r) => (
                  <UserRow key={r.request_id} user={r.user} action={<SmallButton danger disabled={busy} onClick={() => decline.mutate(r.request_id)}>취소</SmallButton>} />
                ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-4">
            <p className="text-xs font-semibold text-muted">내 친구 <span className="font-numeric">{data.friends.length}</span></p>
            {data.friends.length === 0 ? (
              <p className="py-2 text-sm text-muted">아직 친구가 없습니다. 위에서 아이디로 찾아 요청을 보내세요.</p>
            ) : (
              <ul className="divide-y divide-line">
                {data.friends.map((u) => (
                  <UserRow
                    key={u.id}
                    user={u}
                    action={
                      <SmallButton
                        danger
                        disabled={busy}
                        onClick={() => {
                          if (window.confirm(`${u.display_name}님과 친구를 끊을까요? 서로의 기록이 더는 보이지 않습니다.`)) remove.mutate(u.id);
                        }}
                      >
                        끊기
                      </SmallButton>
                    }
                  />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

// ---------- 계정 ----------

function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < 4) {
      setMsg({ ok: false, text: "새 비밀번호는 4자 이상이어야 합니다." });
      return;
    }
    if (next !== confirm) {
      setMsg({ ok: false, text: "새 비밀번호가 서로 다릅니다." });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await changePassword({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setConfirm("");
      setMsg({ ok: true, text: "비밀번호를 변경했습니다." });
    } catch (err) {
      setMsg({
        ok: false,
        text: err instanceof ApiError && err.status === 401 ? "현재 비밀번호가 올바르지 않습니다." : apiErrorMessage(err, "네트워크 오류 — 연결을 확인하세요"),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} className="mt-3 flex flex-col gap-2">
      <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="현재 비밀번호" autoComplete="current-password" className={FIELD_CLS} />
      <input type="password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="새 비밀번호 (4자 이상)" autoComplete="new-password" className={FIELD_CLS} />
      <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="새 비밀번호 확인" autoComplete="new-password" className={FIELD_CLS} />
      {msg ? <p className={`text-sm ${msg.ok ? "text-accent" : "text-danger"}`}>{msg.text}</p> : null}
      <Button type="submit" variant="secondary" full disabled={busy || !current || !next || !confirm}>
        {busy ? <Spinner size="sm" /> : "비밀번호 변경"}
      </Button>
    </form>
  );
}

export default function Profile() {
  const me = useMe();
  const navigate = useNavigate();
  return (
    <main className="mx-auto max-w-[720px] p-4">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-[19px] font-extrabold">프로필</h1>
        <Link to="/settings" aria-label="설정" className="touch-target flex items-center justify-center rounded-row text-xl text-muted active:bg-surface-2">
          ⚙
        </Link>
      </header>
      {me.isLoading ? (
        <div className="flex justify-center py-10"><Spinner /></div>
      ) : me.isError || !me.data ? (
        <ErrorRetry className="py-10" onRetry={() => me.refetch()} />
      ) : (
        <div className="flex flex-col gap-3">
          <MyCard me={me.data} />
          <FriendsSection />
          <Card>
            <SectionTitle>계정</SectionTitle>
            <p className="text-sm text-muted">비밀번호 변경</p>
            <PasswordSection />
            <Button
              variant="danger"
              full
              className="mt-4"
              onClick={() => {
                logout();
                navigate("/login", { replace: true });
              }}
            >
              로그아웃
            </Button>
          </Card>
        </div>
      )}
    </main>
  );
}
