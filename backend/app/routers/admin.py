"""관리자 페이지용 읽기 전용 조회 (§10.5) — 사용자 목록과 각 사용자의 기록.

시스템 수정 기능은 두지 않는다 (사용자 결정: 시스템 수정은 작업 PC에서 직접).
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_admin
from ..db import get_db
from ..schemas import AdminUserOut, BodyWeightOut, SessionDetail, SessionSummary
from .sessions import list_bodyweight_for, list_sessions_for, session_detail_for

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _user_or_404(db: sqlite3.Connection, user_id: int) -> None:
    if db.execute("SELECT 1 FROM user WHERE id = ?", (user_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: sqlite3.Connection = Depends(get_db)) -> list[AdminUserOut]:
    rows = db.execute(
        """
        SELECT u.id, u.username, u.display_name, u.is_admin, u.created_at,
               (SELECT COUNT(*) FROM workout_session s WHERE s.user_id = u.id) AS session_count,
               (SELECT COUNT(*) FROM workout_set ws JOIN workout_session s ON s.id = ws.session_id
                 WHERE s.user_id = u.id) AS set_count,
               (SELECT MAX(s.date) FROM workout_session s WHERE s.user_id = u.id) AS last_date
        FROM user u ORDER BY u.id
        """
    ).fetchall()
    return [
        AdminUserOut(**{**dict(r), "is_admin": bool(r["is_admin"])}) for r in rows
    ]


@router.get("/users/{user_id}/sessions", response_model=list[SessionSummary])
def user_sessions(
    user_id: int,
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
) -> list[SessionSummary]:
    _user_or_404(db, user_id)
    return list_sessions_for(db, user_id, date_from, date_to, limit, offset)


@router.get("/users/{user_id}/sessions/{session_id}", response_model=SessionDetail)
def user_session_detail(
    user_id: int, session_id: int, db: sqlite3.Connection = Depends(get_db)
) -> SessionDetail:
    _user_or_404(db, user_id)
    return session_detail_for(db, user_id, session_id)


@router.get("/users/{user_id}/bodyweight", response_model=list[BodyWeightOut])
def user_bodyweight(
    user_id: int,
    limit: int = Query(default=30, ge=1, le=1000),
    db: sqlite3.Connection = Depends(get_db),
) -> list[BodyWeightOut]:
    _user_or_404(db, user_id)
    return list_bodyweight_for(db, user_id, limit)
