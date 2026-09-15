"""§13 프로필·친구·공유 — 아이디 검색 → 요청 → 수락. 수락된 친구는 서로의 기록·분석·체중을 읽기 전용으로 본다.

읽기 공유 자체는 여기서 하지 않는다: 세션·통계·분석 라우터의 GET 핸들러가 `subject_user`(auth.py)로
`?user_id=`를 받아 친구 여부·공개 설정을 검사한다. 이 라우터는 관계와 프로필만 다룬다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CurrentUser, _user_out, require_auth
from ..db import get_db
from ..schemas import (
    FriendRequestCreate,
    FriendRequestOut,
    FriendsOut,
    FriendUserOut,
    ProfileOut,
    ProfileStatsOut,
    ProfileUpdate,
    UserOut,
)
from .catalog import _like_escape
from .stats import training_weeks

router = APIRouter(prefix="/api", tags=["friends"])

_CARD_SQL = "SELECT id, username, display_name, avatar, bio, created_at, share_with_friends FROM user"


def _relation(db: sqlite3.Connection, me_id: int, other_id: int) -> tuple[str, int | None]:
    if me_id == other_id:
        return "self", None
    row = db.execute(
        "SELECT id, requester_id, status FROM friendship"
        " WHERE (requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?)",
        (me_id, other_id, other_id, me_id),
    ).fetchone()
    if row is None:
        return "none", None
    if row["status"] == "accepted":
        return "friend", row["id"]
    return ("pending_out" if row["requester_id"] == me_id else "pending_in"), row["id"]


def _card(db: sqlite3.Connection, me_id: int, row: sqlite3.Row) -> FriendUserOut:
    relation, request_id = _relation(db, me_id, row["id"])
    return FriendUserOut(
        id=row["id"], username=row["username"], display_name=row["display_name"],
        avatar=row["avatar"], bio=row["bio"], created_at=row["created_at"],
        relation=relation, request_id=request_id,
    )


def _user_row_or_404(db: sqlite3.Connection, **where: int | str) -> sqlite3.Row:
    (col, val), = where.items()
    row = db.execute(f"{_CARD_SQL} WHERE {col} = ?", (val,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return row


def _friends_out(db: sqlite3.Connection, me_id: int) -> FriendsOut:
    friends = [
        _card(db, me_id, r)
        for r in db.execute(
            f"{_CARD_SQL} WHERE id IN ("
            " SELECT CASE WHEN requester_id = ? THEN addressee_id ELSE requester_id END FROM friendship"
            " WHERE status = 'accepted' AND (requester_id = ? OR addressee_id = ?))"
            " ORDER BY display_name, username",
            (me_id, me_id, me_id),
        ).fetchall()
    ]

    def pending(col_me: str, col_other: str) -> list[FriendRequestOut]:
        rows = db.execute(
            f"SELECT f.id AS request_id, f.created_at AS requested_at, u.* FROM friendship f"
            f" JOIN user u ON u.id = f.{col_other}"
            f" WHERE f.status = 'pending' AND f.{col_me} = ? ORDER BY f.created_at DESC",
            (me_id,),
        ).fetchall()
        return [
            FriendRequestOut(request_id=r["request_id"], user=_card(db, me_id, r), created_at=r["requested_at"])
            for r in rows
        ]

    return FriendsOut(friends=friends, incoming=pending("addressee_id", "requester_id"), outgoing=pending("requester_id", "addressee_id"))


def _profile_stats(db: sqlite3.Connection, user_id: int) -> ProfileStatsOut:
    sessions, last = db.execute(
        "SELECT COUNT(*), MAX(date) FROM workout_session WHERE user_id = ?", (user_id,)
    ).fetchone()
    sets = db.execute(
        "SELECT COUNT(*) FROM workout_set ws JOIN workout_session s ON s.id = ws.session_id WHERE s.user_id = ?",
        (user_id,),
    ).fetchone()[0]
    volume_4w = db.execute(
        "SELECT COALESCE(SUM(volume_kg), 0) FROM set_volume"
        " WHERE user_id = ? AND is_warmup = 0 AND date >= date('now', 'localtime', '-28 days')",
        (user_id,),
    ).fetchone()[0]
    return ProfileStatsOut(
        training_weeks=training_weeks(db, user_id), session_count=sessions, set_count=sets,
        volume_4w=round(float(volume_4w), 1), last_session_date=last,
    )


# ---------- 프로필 ----------


@router.get("/profile/{username}", response_model=ProfileOut)
def get_profile(
    username: str,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> ProfileOut:
    """프로필 카드. 통계는 본인·(공개 설정한) 친구·관리자에게만."""
    row = _user_row_or_404(db, username=username)
    card = _card(db, user.id, row)
    can_see = card.relation == "self" or user.is_admin or (card.relation == "friend" and row["share_with_friends"])
    return ProfileOut(
        **card.model_dump(),
        stats=_profile_stats(db, row["id"]) if can_see else None,
        share_with_friends=bool(row["share_with_friends"]) if card.relation == "self" else None,
    )


@router.patch("/me/profile", response_model=UserOut)
def update_profile(
    body: ProfileUpdate,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> UserOut:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=422, detail="바꿀 값이 없습니다")
    if "display_name" in fields and not fields["display_name"]:
        raise HTTPException(status_code=422, detail="표시 이름은 비울 수 없습니다")
    sets = ", ".join(f"{k} = ?" for k in fields)
    values = [int(v) if isinstance(v, bool) else (v or None) for v in fields.values()]
    if "display_name" in fields:
        values[list(fields).index("display_name")] = fields["display_name"]
    db.execute(f"UPDATE user SET {sets} WHERE id = ?", (*values, user.id))
    return _user_out(db.execute("SELECT * FROM user WHERE id = ?", (user.id,)).fetchone())


# ---------- 친구 ----------


@router.get("/users/search", response_model=list[FriendUserOut])
def search_users(
    q: str = Query(..., min_length=2, max_length=40),
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> list[FriendUserOut]:
    """아이디(앞부분) 또는 표시 이름(포함)으로 찾는다. 본인 제외, 20명까지."""
    pat = _like_escape(q.strip())
    rows = db.execute(
        f"{_CARD_SQL} WHERE id != ? AND (username LIKE ? ESCAPE '\\' OR display_name LIKE ? ESCAPE '\\')"
        " ORDER BY username LIMIT 20",
        (user.id, f"{pat}%", f"%{pat}%"),
    ).fetchall()
    return [_card(db, user.id, r) for r in rows]


@router.get("/friends", response_model=FriendsOut)
def list_friends(
    user: CurrentUser = Depends(require_auth), db: sqlite3.Connection = Depends(get_db)
) -> FriendsOut:
    return _friends_out(db, user.id)


@router.post("/friends/requests", response_model=FriendsOut)
def request_friend(
    body: FriendRequestCreate,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> FriendsOut:
    """요청 보내기. 상대가 이미 나에게 요청해 뒀으면 그 요청을 수락한다."""
    target = _user_row_or_404(db, username=body.username)
    if target["id"] == user.id:
        raise HTTPException(status_code=422, detail="자기 자신에게는 요청할 수 없습니다")
    relation, request_id = _relation(db, user.id, target["id"])
    if relation == "friend":
        raise HTTPException(status_code=409, detail="이미 친구입니다")
    if relation == "pending_out":
        raise HTTPException(status_code=409, detail="이미 요청을 보냈습니다")
    if relation == "pending_in":
        db.execute(
            "UPDATE friendship SET status = 'accepted', responded_at = datetime('now') WHERE id = ?",
            (request_id,),
        )
    else:
        db.execute(
            "INSERT INTO friendship (requester_id, addressee_id) VALUES (?, ?)", (user.id, target["id"])
        )
    return _friends_out(db, user.id)


@router.post("/friends/requests/{request_id}/accept", response_model=FriendsOut)
def accept_request(
    request_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> FriendsOut:
    cur = db.execute(
        "UPDATE friendship SET status = 'accepted', responded_at = datetime('now')"
        " WHERE id = ? AND addressee_id = ? AND status = 'pending'",
        (request_id, user.id),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="받은 요청이 아닙니다")
    return _friends_out(db, user.id)


@router.post("/friends/requests/{request_id}/decline", response_model=FriendsOut)
def decline_request(
    request_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> FriendsOut:
    """받은 요청 거절 또는 보낸 요청 취소 — 행 삭제."""
    cur = db.execute(
        "DELETE FROM friendship WHERE id = ? AND status = 'pending' AND (addressee_id = ? OR requester_id = ?)",
        (request_id, user.id, user.id),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없습니다")
    return _friends_out(db, user.id)


@router.delete("/friends/{user_id}", response_model=FriendsOut)
def remove_friend(
    user_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> FriendsOut:
    """친구 끊기 (양쪽 모두에서 사라진다). 관계가 없어도 무해."""
    db.execute(
        "DELETE FROM friendship WHERE (requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?)",
        (user.id, user_id, user_id, user.id),
    )
    return _friends_out(db, user.id)
