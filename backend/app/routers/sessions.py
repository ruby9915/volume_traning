import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..auth import CurrentUser, require_auth
from ..db import E1RM_EXPR, get_db
from ..schemas import (
    BodyWeightOut,
    BodyWeightUpsert,
    SessionDetail,
    SessionExerciseGroup,
    SessionSetOut,
    SessionSummary,
    SessionUpdate,
    SetCreate,
    SetOut,
    SetUpdate,
)
from ..seed_data.targets import REGION_NAMES_KO
from .catalog import target_id_or_422

router = APIRouter(prefix="/api", tags=["sessions"])

# 세션 부위 라벨: 2위 부위가 세션 볼륨의 이 비율 이상이면 "하체·등"처럼 둘 다 표시 (§10.2, 추정치)
SECOND_REGION_MIN_SHARE = 0.25
_REGION_ORDER = {region: i for i, region in enumerate(REGION_NAMES_KO)}


def _pr_flags(db: sqlite3.Connection, row: sqlite3.Row) -> tuple[bool, bool]:
    # "이전" = (date, id) 순서 — 소급 입력·세션 date 이동에도 §6.3 정합. 같은 사용자 기록만.
    if row["is_warmup"] or row["weight_kg"] <= 0:
        return False, False
    has_prev_session = db.execute(
        """
        SELECT 1 FROM set_volume sv
        WHERE sv.user_id = ? AND sv.exercise_id = ? AND sv.session_id != ?
          AND (sv.date < ? OR (sv.date = ? AND sv.set_id < ?))
        LIMIT 1
        """,
        (row["user_id"], row["exercise_id"], row["session_id"], row["date"], row["date"], row["id"]),
    ).fetchone()
    if has_prev_session is None:
        return False, False
    prev = db.execute(
        f"""
        SELECT MAX(sv.weight_kg) AS max_weight,
               MAX({E1RM_EXPR}) AS max_e1rm
        FROM set_volume sv
        WHERE sv.user_id = ? AND sv.exercise_id = ? AND sv.is_warmup = 0 AND sv.weight_kg > 0
          AND (sv.date < ? OR (sv.date = ? AND sv.set_id < ?))
        """,
        (row["user_id"], row["exercise_id"], row["date"], row["date"], row["id"]),
    ).fetchone()
    is_weight_pr = prev["max_weight"] is not None and row["weight_kg"] > prev["max_weight"]
    is_e1rm_pr = False
    if row["reps"] <= 12 and prev["max_e1rm"] is not None:
        e1rm = row["weight_kg"] * (1 + row["reps"] / 30.0)
        is_e1rm_pr = e1rm > prev["max_e1rm"]
    return is_weight_pr, is_e1rm_pr


# 세트의 타겟: 세트 target_id, 비어 있으면 종목 기본 타겟 (마이그레이션 중간 상태 방어)
_TARGET_COLS = (
    "COALESCE(t.code, dt.code) AS target, COALESCE(t.name_ko, dt.name_ko) AS target_ko"
)
_TARGET_JOINS = """
LEFT JOIN muscle_group t ON t.id = ws.target_id
LEFT JOIN muscle_group dt ON dt.id = e.default_target_id
"""


def _set_out(db: sqlite3.Connection, set_id: int) -> SetOut:
    row = db.execute(
        f"""
        SELECT ws.id, ws.client_id, ws.session_id, ws.exercise_id, ws.set_index,
               ws.weight_kg, ws.reps, ws.is_warmup, ws.note, ws.created_at,
               sv.volume_kg, sv.date, sv.user_id, {_TARGET_COLS}
        FROM workout_set ws
        JOIN set_volume sv ON sv.set_id = ws.id
        JOIN exercise e ON e.id = ws.exercise_id
        {_TARGET_JOINS}
        WHERE ws.id = ?
        """,
        (set_id,),
    ).fetchone()
    is_weight_pr, is_e1rm_pr = _pr_flags(db, row)
    data = dict(row)
    data.pop("user_id")
    return SetOut(**data, is_weight_pr=is_weight_pr, is_e1rm_pr=is_e1rm_pr)


def _owned_set(db: sqlite3.Connection, user: CurrentUser, set_id: int) -> sqlite3.Row:
    row = db.execute(
        """
        SELECT ws.id, ws.exercise_id FROM workout_set ws
        JOIN workout_session s ON s.id = ws.session_id
        WHERE ws.id = ? AND s.user_id = ?
        """,
        (set_id, user.id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="세트를 찾을 수 없습니다")
    return row


@router.post("/sets", response_model=SetOut, status_code=201)
def create_set(
    body: SetCreate,
    response: Response,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> SetOut:
    existing = db.execute(
        """
        SELECT ws.id FROM workout_set ws JOIN workout_session s ON s.id = ws.session_id
        WHERE ws.client_id = ? AND s.user_id = ?
        """,
        (body.client_id, user.id),
    ).fetchone()
    if existing is not None:
        response.status_code = 200
        return _set_out(db, existing["id"])

    exercise = db.execute(
        "SELECT id, default_target_id FROM exercise"
        " WHERE id = ? AND (user_id IS NULL OR user_id = ?)",
        (body.exercise_id, user.id),
    ).fetchone()
    if exercise is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    session_id: int | None = None
    if body.session_id is not None:
        # §3.7-B 세션 직접 귀속 — lazy 생성 생략. date만으로 보내면 같은 날
        # 두 번째 세션에 잘못 붙던 결함의 수정 경로.
        session = db.execute(
            "SELECT id, date FROM workout_session WHERE id = ? AND user_id = ?",
            (body.session_id, user.id),
        ).fetchone()
        if session is None:
            raise HTTPException(
                status_code=422, detail="session_id에 해당하는 세션이 없습니다"
            )
        if session["date"] != body.date:
            raise HTTPException(
                status_code=422, detail="세션의 날짜와 요청 date가 일치하지 않습니다"
            )
        session_id = session["id"]
    elif not body.new_session:
        latest = db.execute(
            "SELECT id FROM workout_session WHERE date = ? AND user_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (body.date, user.id),
        ).fetchone()
        if latest is not None:
            session_id = latest["id"]
    if session_id is None:
        session_id = db.execute(
            "INSERT INTO workout_session (date, user_id) VALUES (?, ?)", (body.date, user.id)
        ).lastrowid

    target_id = (
        exercise["default_target_id"]
        if body.target is None
        else target_id_or_422(db, body.target)
    )
    try:
        # set_index 산출과 INSERT를 단일 문장으로 — 동시 요청 간 중복 index 방지
        cur = db.execute(
            """
            INSERT INTO workout_set (client_id, session_id, exercise_id, set_index,
                                     weight_kg, reps, is_warmup, target_id)
            VALUES (?, ?, ?,
                    (SELECT COALESCE(MAX(set_index), 0) + 1 FROM workout_set WHERE session_id = ?),
                    ?, ?, ?, ?)
            """,
            (
                body.client_id,
                session_id,
                body.exercise_id,
                session_id,
                body.weight_kg,
                body.reps,
                int(body.is_warmup),
                target_id,
            ),
        )
    except sqlite3.IntegrityError:
        db.rollback()
        existing = db.execute(
            """
            SELECT ws.id FROM workout_set ws JOIN workout_session s ON s.id = ws.session_id
            WHERE ws.client_id = ? AND s.user_id = ?
            """,
            (body.client_id, user.id),
        ).fetchone()
        if existing is None:
            # client_id UNIQUE는 전역 — 다른 사용자의 세트와 충돌 (UUID라 사실상 발생하지 않음)
            raise HTTPException(status_code=409, detail="client_id가 이미 사용되었습니다")
        response.status_code = 200
        return _set_out(db, existing["id"])
    db.commit()
    return _set_out(db, cur.lastrowid)


@router.patch("/sets/{set_id}", response_model=SetOut)
def update_set(
    set_id: int,
    body: SetUpdate,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> SetOut:
    owned = _owned_set(db, user, set_id)
    data = body.model_dump(exclude_unset=True)
    # target만 명시적 null 허용(= 종목 기본 타겟으로 복귀). NOT NULL 필드의 명시적 null은 무시.
    if "target" in data:
        code = data.pop("target")
        if code is None:
            data["target_id"] = db.execute(
                "SELECT default_target_id FROM exercise WHERE id = ?", (owned["exercise_id"],)
            ).fetchone()[0]
        else:
            data["target_id"] = target_id_or_422(db, code)
    for key in ("weight_kg", "reps", "is_warmup"):
        if data.get(key) is None and key in data:
            del data[key]
    if data:
        if "is_warmup" in data:
            data["is_warmup"] = int(data["is_warmup"])
        assignments = ", ".join(f"{key} = ?" for key in data)
        db.execute(
            f"UPDATE workout_set SET {assignments} WHERE id = ?",
            (*data.values(), set_id),
        )
    return _set_out(db, set_id)


@router.delete("/sets/{set_id}", status_code=204)
def delete_set(
    set_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    _owned_set(db, user, set_id)
    db.execute("DELETE FROM workout_set WHERE id = ?", (set_id,))


_SESSION_SUMMARY_SQL = """
SELECT s.id, s.date, s.note,
       COALESCE(SUM(CASE WHEN sv.is_warmup = 0 THEN sv.volume_kg END), 0) AS total_volume,
       COUNT(DISTINCT sv.exercise_id) AS exercise_count,
       COUNT(sv.set_id) AS set_count
FROM workout_session s
LEFT JOIN set_volume sv ON sv.session_id = s.id
"""

# 세션×부위 볼륨 (세트 타겟 100% 귀속, 웜업 제외) — 부위 라벨 판정 재료
_REGION_VOLUME_SQL = """
SELECT sv.session_id AS session_id, tp.region AS region, SUM(sv.volume_kg) AS vol
FROM set_volume sv
JOIN target_path tp ON tp.id = sv.target_id
WHERE sv.is_warmup = 0 AND sv.session_id IN ({placeholders})
GROUP BY sv.session_id, tp.region
"""


def _region_fields(db: sqlite3.Connection, session_ids: list[int]) -> dict[int, dict]:
    """세션별 {main_region, main_region_ko, region_label}. 볼륨 1위 부위, 2위가
    SECOND_REGION_MIN_SHARE 이상이면 "1위·2위". 동률은 고정 부위 순서 — 항상 결정적."""
    empty = {"main_region": None, "main_region_ko": None, "region_label": None}
    if not session_ids:
        return {}
    placeholders = ",".join("?" * len(session_ids))
    rows = db.execute(
        _REGION_VOLUME_SQL.format(placeholders=placeholders), session_ids
    ).fetchall()
    by_session: dict[int, list[tuple[float, str]]] = {}
    for r in rows:
        by_session.setdefault(r["session_id"], []).append((r["vol"], r["region"]))
    out: dict[int, dict] = {sid: dict(empty) for sid in session_ids}
    for sid, items in by_session.items():
        total = sum(v for v, _ in items)
        if total <= 0:
            continue
        items.sort(key=lambda x: (-x[0], _REGION_ORDER[x[1]]))
        regions = [items[0][1]]
        if len(items) > 1 and items[1][0] >= total * SECOND_REGION_MIN_SHARE:
            regions.append(items[1][1])
        out[sid] = {
            "main_region": regions[0],
            "main_region_ko": REGION_NAMES_KO[regions[0]],
            "region_label": "·".join(REGION_NAMES_KO[r] for r in regions),
        }
    return out


def list_sessions_for(
    db: sqlite3.Connection,
    user_id: int,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    offset: int,
) -> list[SessionSummary]:
    """사용자 범위 세션 목록 — 본인 조회와 관리자 조회(admin 라우터)가 공유."""
    rows = db.execute(
        _SESSION_SUMMARY_SQL
        + """
        WHERE s.user_id = :uid
          AND (:date_from IS NULL OR s.date >= :date_from)
          AND (:date_to IS NULL OR s.date <= :date_to)
        GROUP BY s.id
        ORDER BY s.date DESC, s.id DESC
        LIMIT :limit OFFSET :offset
        """,
        {"uid": user_id, "date_from": date_from, "date_to": date_to, "limit": limit, "offset": offset},
    ).fetchall()
    regions = _region_fields(db, [r["id"] for r in rows])
    return [SessionSummary(**dict(r), **regions[r["id"]]) for r in rows]


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> list[SessionSummary]:
    return list_sessions_for(db, user.id, date_from, date_to, limit, offset)


def _session_summary(db: sqlite3.Connection, user_id: int, session_id: int) -> SessionSummary | None:
    row = db.execute(
        _SESSION_SUMMARY_SQL + " WHERE s.id = ? AND s.user_id = ? GROUP BY s.id",
        (session_id, user_id),
    ).fetchone()
    if row is None:
        return None
    regions = _region_fields(db, [session_id])
    return SessionSummary(**dict(row), **regions[session_id])


def session_detail_for(db: sqlite3.Connection, user_id: int, session_id: int) -> SessionDetail:
    summary = _session_summary(db, user_id, session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    session_created_at = db.execute(
        "SELECT created_at FROM workout_session WHERE id = ?", (session_id,)
    ).fetchone()["created_at"]
    rows = db.execute(
        f"""
        SELECT ws.id, ws.client_id, ws.exercise_id, ws.set_index, ws.weight_kg,
               ws.reps, ws.is_warmup, ws.note, ws.created_at, sv.volume_kg, e.name_ko,
               dt.code AS exercise_default_target, {_TARGET_COLS}
        FROM workout_set ws
        JOIN set_volume sv ON sv.set_id = ws.id
        JOIN exercise e ON e.id = ws.exercise_id
        {_TARGET_JOINS}
        WHERE ws.session_id = ?
        ORDER BY ws.set_index
        """,
        (session_id,),
    ).fetchall()
    groups: dict[int, SessionExerciseGroup] = {}
    for r in rows:
        group = groups.get(r["exercise_id"])
        if group is None:
            group = SessionExerciseGroup(
                exercise_id=r["exercise_id"],
                name_ko=r["name_ko"],
                default_target=r["exercise_default_target"] or r["target"],
                sets=[],
            )
            groups[r["exercise_id"]] = group
        group.sets.append(
            SessionSetOut(
                id=r["id"],
                client_id=r["client_id"],
                set_index=r["set_index"],
                weight_kg=r["weight_kg"],
                reps=r["reps"],
                is_warmup=bool(r["is_warmup"]),
                volume_kg=r["volume_kg"],
                note=r["note"],
                created_at=r["created_at"],
                target=r["target"],
                target_ko=r["target_ko"],
            )
        )
    return SessionDetail(
        **summary.model_dump(),
        created_at=session_created_at,
        exercises=list(groups.values()),
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> SessionDetail:
    return session_detail_for(db, user.id, session_id)


@router.patch("/sessions/{session_id}", response_model=SessionSummary)
def update_session(
    session_id: int,
    body: SessionUpdate,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> SessionSummary:
    row = db.execute(
        "SELECT id FROM workout_session WHERE id = ? AND user_id = ?", (session_id, user.id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    data = body.model_dump(exclude_unset=True)
    if data:
        assignments = ", ".join(f"{key} = ?" for key in data)
        db.execute(
            f"UPDATE workout_session SET {assignments} WHERE id = ?",
            (*data.values(), session_id),
        )
    summary = _session_summary(db, user.id, session_id)
    assert summary is not None
    return summary


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    cur = db.execute(
        "DELETE FROM workout_session WHERE id = ? AND user_id = ?", (session_id, user.id)
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")


def list_bodyweight_for(db: sqlite3.Connection, user_id: int, limit: int) -> list[BodyWeightOut]:
    rows = db.execute(
        "SELECT id, date, weight_kg FROM body_weight_log WHERE user_id = ?"
        " ORDER BY date DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [BodyWeightOut(**dict(r)) for r in rows]


@router.get("/bodyweight", response_model=list[BodyWeightOut])
def list_bodyweight(
    limit: int = Query(default=30, ge=1, le=1000),
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> list[BodyWeightOut]:
    return list_bodyweight_for(db, user.id, limit)


@router.post("/bodyweight", response_model=BodyWeightOut)
def upsert_bodyweight(
    body: BodyWeightUpsert,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> BodyWeightOut:
    db.execute(
        """
        INSERT INTO body_weight_log (user_id, date, weight_kg) VALUES (?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET weight_kg = excluded.weight_kg
        """,
        (user.id, body.date, body.weight_kg),
    )
    row = db.execute(
        "SELECT id, date, weight_kg FROM body_weight_log WHERE user_id = ? AND date = ?",
        (user.id, body.date),
    ).fetchone()
    return BodyWeightOut(**dict(row))
