"""테스트 공용 헬퍼 — 여러 테스트 모듈에 복사돼 있던 함수를 한곳에 모았다.

fixture(app/client/auth_client/user_client/db)는 conftest.py, 일반 함수는 이 모듈.
DB 직접 삽입 헬퍼는 v4 규칙을 따른다: 세션·체중은 user_id(기본 관리자), 세트는 target_id
(기본 = 종목 기본 타겟).
"""

import sqlite3
import uuid
from datetime import datetime, timedelta


def effective_today():
    """§5.3·§6.1 하루 경계 03:00 — stats._effective_today와 같은 규칙."""
    return (datetime.now() - timedelta(hours=3)).date()


def seed_exercise_id(name_ko: str) -> int:
    """자체 연결로 시드 종목 id 조회 (db fixture 없이 auth_client만 쓰는 테스트용)."""
    from app.config import get_settings

    conn = sqlite3.connect(get_settings().DB_PATH)
    try:
        row = conn.execute(
            "SELECT id FROM exercise WHERE name_ko = ?", (name_ko,)
        ).fetchone()
        assert row is not None, f"seed exercise missing: {name_ko}"
        return row[0]
    finally:
        conn.close()


def ex_id(db: sqlite3.Connection, name_ko: str) -> int:
    return db.execute("SELECT id FROM exercise WHERE name_ko = ?", (name_ko,)).fetchone()[0]


def admin_id(db: sqlite3.Connection) -> int:
    return db.execute("SELECT id FROM user WHERE is_admin = 1 ORDER BY id LIMIT 1").fetchone()[0]


def target_id(db: sqlite3.Connection, code: str) -> int:
    return db.execute("SELECT id FROM muscle_group WHERE code = ?", (code,)).fetchone()[0]


def post_set(client, *, date, exercise_id, weight_kg, reps, **extra):
    """POST /api/sets — client_id는 매번 새 UUID. 응답 객체를 그대로 반환."""
    payload = {
        "client_id": str(uuid.uuid4()),
        "date": date,
        "exercise_id": exercise_id,
        "weight_kg": weight_kg,
        "reps": reps,
        **extra,
    }
    return client.post("/api/sets", json=payload)


def add_session(db: sqlite3.Connection, date: str, user_id: int | None = None) -> int:
    cur = db.execute(
        "INSERT INTO workout_session (date, user_id) VALUES (?, ?)",
        (date, user_id if user_id is not None else admin_id(db)),
    )
    db.commit()
    return cur.lastrowid


def add_set(
    db, session_id, exercise_id, weight, reps, warmup=0, note=None, target: str | None = None
) -> int:
    """DB 직접 삽입 (API 우회) — set_index는 세션 내 다음 번호, target 기본 = 종목 기본 타겟."""
    idx = db.execute(
        "SELECT COALESCE(MAX(set_index), 0) + 1 FROM workout_set WHERE session_id = ?",
        (session_id,),
    ).fetchone()[0]
    tid = (
        target_id(db, target)
        if target
        else db.execute(
            "SELECT default_target_id FROM exercise WHERE id = ?", (exercise_id,)
        ).fetchone()[0]
    )
    cur = db.execute(
        "INSERT INTO workout_set"
        " (session_id, exercise_id, set_index, weight_kg, reps, is_warmup, note, target_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, exercise_id, idx, weight, reps, warmup, note, tid),
    )
    db.commit()
    return cur.lastrowid


def add_bodyweight(db: sqlite3.Connection, date: str, kg: float, user_id: int | None = None) -> None:
    db.execute(
        "INSERT INTO body_weight_log (user_id, date, weight_kg) VALUES (?, ?, ?)",
        (user_id if user_id is not None else admin_id(db), date, kg),
    )
    db.commit()


def assert_keys(obj, expected: set, label: str) -> None:
    """응답 dict의 키 집합이 types.ts 정본과 정확히 일치하는지 (계약 테스트 공용)."""
    assert isinstance(obj, dict), f"{label}: dict가 아님 ({type(obj).__name__})"
    assert set(obj.keys()) == expected, (
        f"{label} 키 불일치 — 누락 {expected - set(obj)}, 초과 {set(obj) - expected}"
    )
