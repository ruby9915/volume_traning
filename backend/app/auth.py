"""인증 (SETTING.MD §10.1, v2): 사용자 테이블 + 아이디/비밀번호 + JWT(HS256, sub = user id).

보안 수준은 사용자 결정대로 최소 — 무차별 대입 지연·잠금·이메일 인증 없음. 비밀번호는
표준 라이브러리 scrypt로만 해시한다 (비용 0). 토큰 만료 90일, refresh 없음 (§4.1 유지).
"""

import base64
import dataclasses
import datetime as dt
import hashlib
import secrets
import sqlite3

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .db import get_db
from .schemas import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RegisterRequest,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, digest_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return secrets.compare_digest(digest, expected)


@dataclasses.dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    is_admin: bool


def _user_out(row: sqlite3.Row) -> UserOut:
    keys = row.keys()
    return UserOut(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        is_admin=bool(row["is_admin"]),
        created_at=row["created_at"],
        bio=row["bio"] if "bio" in keys else None,
        avatar=row["avatar"] if "avatar" in keys else None,
        share_with_friends=bool(row["share_with_friends"]) if "share_with_friends" in keys else True,
    )


def _issue_token(user_id: int) -> LoginResponse:
    settings = get_settings()
    ttl = dt.timedelta(days=settings.TOKEN_TTL_DAYS)
    token = jwt.encode(
        {"sub": str(user_id), "exp": dt.datetime.now(dt.timezone.utc) + ttl},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    return LoginResponse(access_token=token, expires_in=int(ttl.total_seconds()))


@router.post("/register", response_model=LoginResponse, status_code=201)
def register(body: RegisterRequest, db: sqlite3.Connection = Depends(get_db)) -> LoginResponse:
    """가입 즉시 로그인 토큰 발급. 첫 사용자는 마이그레이션이 만드는 관리자 계정이므로
    여기서 만드는 계정은 항상 일반 사용자다."""
    exists = db.execute("SELECT 1 FROM user WHERE username = ?", (body.username,)).fetchone()
    if exists is not None:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다")
    cur = db.execute(
        "INSERT INTO user (username, password_hash, display_name, is_admin) VALUES (?, ?, ?, 0)",
        (body.username, hash_password(body.password), body.display_name or body.username),
    )
    db.commit()
    return _issue_token(cur.lastrowid)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: sqlite3.Connection = Depends(get_db)) -> LoginResponse:
    row = db.execute(
        "SELECT id, password_hash FROM user WHERE username = ?", (body.username,)
    ).fetchone()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")
    return _issue_token(row["id"])


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: sqlite3.Connection = Depends(get_db),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    try:
        payload = jwt.decode(
            credentials.credentials,
            get_settings().JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},  # v1 토큰(sub 없음)은 재로그인 유도
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다")
    row = db.execute(
        "SELECT id, username, display_name, is_admin FROM user WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다")
    return CurrentUser(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        is_admin=bool(row["is_admin"]),
    )


def require_admin(user: CurrentUser = Depends(require_auth)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="관리자만 사용할 수 있습니다")
    return user


def is_friends(db: sqlite3.Connection, a: int, b: int) -> bool:
    """§13 수락된 친구 관계(양방향)."""
    return (
        db.execute(
            "SELECT 1 FROM friendship WHERE status = 'accepted'"
            " AND ((requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?))",
            (a, b, b, a),
        ).fetchone()
        is not None
    )


def subject_user(
    user_id: int | None = Query(None, description="§13 친구의 데이터를 읽을 때 그 사용자 id"),
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> CurrentUser:
    """§13 친구 공유: `?user_id=`가 있으면 그 사용자를 '대상'으로 돌려준다 — 조회(GET) 핸들러 전용.

    조건: 수락된 친구이고 상대가 공개(share_with_friends)를 켜 둔 경우. 관리자는 항상 가능.
    쓰기 핸들러는 계속 require_auth(본인)를 쓰므로 user_id를 붙여도 남의 기록에 쓸 수 없다.
    """
    if user_id is None or user_id == user.id:
        return user
    row = db.execute(
        "SELECT id, username, display_name, is_admin, share_with_friends FROM user WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    if not user.is_admin and (not row["share_with_friends"] or not is_friends(db, user.id, user_id)):
        raise HTTPException(
            status_code=403, detail={"code": "not_friends", "message": "친구만 볼 수 있습니다"}
        )
    return CurrentUser(
        id=row["id"], username=row["username"], display_name=row["display_name"],
        is_admin=bool(row["is_admin"]),
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(require_auth), db: sqlite3.Connection = Depends(get_db)) -> UserOut:
    row = db.execute("SELECT * FROM user WHERE id = ?", (user.id,)).fetchone()
    return _user_out(row)


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChangeRequest,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    row = db.execute("SELECT password_hash FROM user WHERE id = ?", (user.id,)).fetchone()
    if not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다")
    db.execute(
        "UPDATE user SET password_hash = ? WHERE id = ?",
        (hash_password(body.new_password), user.id),
    )
