import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..db import E1RM_EXPR, get_db
from ..seed_exercises import REGION_NAMES_KO
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

router = APIRouter(prefix="/api", tags=["sessions"])


def _pr_flags(db: sqlite3.Connection, row: sqlite3.Row) -> tuple[bool, bool]:
    # "이전" = (date, id) 순서 — 소급 입력·세션 date 이동에도 §6.3 정합
    if row["is_warmup"] or row["weight_kg"] <= 0:
        return False, False
    has_prev_session = db.execute(
        """
        SELECT 1 FROM set_volume sv
        WHERE sv.exercise_id = ? AND sv.session_id != ?
          AND (sv.date < ? OR (sv.date = ? AND sv.set_id < ?))
        LIMIT 1
        """,
        (row["exercise_id"], row["session_id"], row["date"], row["date"], row["id"]),
    ).fetchone()
    if has_prev_session is None:
        return False, False
    prev = db.execute(
        f"""
        SELECT MAX(sv.weight_kg) AS max_weight,
               MAX({E1RM_EXPR}) AS max_e1rm
        FROM set_volume sv
        WHERE sv.exercise_id = ? AND sv.is_warmup = 0 AND sv.weight_kg > 0
          AND (sv.date < ? OR (sv.date = ? AND sv.set_id < ?))
        """,
        (row["exercise_id"], row["date"], row["date"], row["id"]),
    ).fetchone()
    is_weight_pr = prev["max_weight"] is not None and row["weight_kg"] > prev["max_weight"]
    is_e1rm_pr = False
    if row["reps"] <= 12 and prev["max_e1rm"] is not None:
        e1rm = row["weight_kg"] * (1 + row["reps"] / 30.0)
        is_e1rm_pr = e1rm > prev["max_e1rm"]
    return is_weight_pr, is_e1rm_pr


def _set_out(db: sqlite3.Connection, set_id: int) -> SetOut:
    row = db.execute(
        """
        SELECT ws.id, ws.client_id, ws.session_id, ws.exercise_id, ws.set_index,
               ws.weight_kg, ws.reps, ws.is_warmup, ws.note, ws.created_at,
               sv.volume_kg, sv.date,
               img.code AS intent_muscle, img.name_ko AS intent_muscle_ko
        FROM workout_set ws
        JOIN set_volume sv ON sv.set_id = ws.id
        LEFT JOIN muscle_group img ON img.id = ws.intent_muscle_group_id
        WHERE ws.id = ?
        """,
        (set_id,),
    ).fetchone()
    is_weight_pr, is_e1rm_pr = _pr_flags(db, row)
    return SetOut(
        **dict(row), is_weight_pr=is_weight_pr, is_e1rm_pr=is_e1rm_pr
    )


def _intent_muscle_id(db: sqlite3.Connection, code: str) -> int:
    # code는 Pydantic MuscleCode Literal로 이미 422 검증됨 — 시드 무결 방어용
    row = db.execute(
        "SELECT id FROM muscle_group WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=422, detail="유효하지 않은 근육 code입니다")
    return row["id"]


@router.post("/sets", response_model=SetOut, status_code=201)
def create_set(
    body: SetCreate, response: Response, db: sqlite3.Connection = Depends(get_db)
) -> SetOut:
    existing = db.execute(
        "SELECT id FROM workout_set WHERE client_id = ?", (body.client_id,)
    ).fetchone()
    if existing is not None:
        response.status_code = 200
        return _set_out(db, existing["id"])

    exercise = db.execute(
        "SELECT id FROM exercise WHERE id = ?", (body.exercise_id,)
    ).fetchone()
    if exercise is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    session_id: int | None = None
    if body.session_id is not None:
        # §3.7-B 세션 직접 귀속 — lazy 생성 생략. date만으로 보내면 같은 날
        # 두 번째 세션에 잘못 붙던 결함의 수정 경로.
        session = db.execute(
            "SELECT id, date FROM workout_session WHERE id = ?", (body.session_id,)
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
            "SELECT id FROM workout_session WHERE date = ? ORDER BY id DESC LIMIT 1",
            (body.date,),
        ).fetchone()
        if latest is not None:
            session_id = latest["id"]
    if session_id is None:
        session_id = db.execute(
            "INSERT INTO workout_session (date) VALUES (?)", (body.date,)
        ).lastrowid

    intent_id = (
        None if body.intent_muscle is None else _intent_muscle_id(db, body.intent_muscle)
    )
    try:
        # set_index 산출과 INSERT를 단일 문장으로 — 동시 요청 간 중복 index 방지
        cur = db.execute(
            """
            INSERT INTO workout_set (client_id, session_id, exercise_id, set_index,
                                     weight_kg, reps, is_warmup, intent_muscle_group_id)
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
                intent_id,
            ),
        )
    except sqlite3.IntegrityError:
        db.rollback()
        existing = db.execute(
            "SELECT id FROM workout_set WHERE client_id = ?", (body.client_id,)
        ).fetchone()
        if existing is None:
            raise
        response.status_code = 200
        return _set_out(db, existing["id"])
    db.commit()
    return _set_out(db, cur.lastrowid)


@router.patch("/sets/{set_id}", response_model=SetOut)
def update_set(
    set_id: int, body: SetUpdate, db: sqlite3.Connection = Depends(get_db)
) -> SetOut:
    row = db.execute("SELECT id FROM workout_set WHERE id = ?", (set_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="세트를 찾을 수 없습니다")
    data = body.model_dump(exclude_unset=True)
    # intent_muscle만 명시적 null 허용(= intent 해제). NOT NULL 필드의
    # 명시적 null은 기존과 동일하게 무시한다.
    if "intent_muscle" in data:
        code = data.pop("intent_muscle")
        data["intent_muscle_group_id"] = (
            None if code is None else _intent_muscle_id(db, code)
        )
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
def delete_set(set_id: int, db: sqlite3.Connection = Depends(get_db)) -> None:
    cur = db.execute("DELETE FROM workout_set WHERE id = ?", (set_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="세트를 찾을 수 없습니다")


_SESSION_SUMMARY_SQL = """
SELECT s.id, s.date, s.note,
       COALESCE(SUM(CASE WHEN sv.is_warmup = 0 THEN sv.volume_kg END), 0) AS total_volume,
       COUNT(DISTINCT sv.exercise_id) AS exercise_count,
       COUNT(sv.set_id) AS set_count
FROM workout_session s
LEFT JOIN set_volume sv ON sv.session_id = s.id
"""

# REGION_NAMES_KO(seed_exercises) 순서가 동률 시 최후 tie-break 기준 (§3.4)
_REGION_ORDER = {region: i for i, region in enumerate(REGION_NAMES_KO)}

# 세션×region 가중 볼륨(primary 1.0 / secondary 0.5, 웜업 제외)과
# region 내 최대 단일 종목 가중 볼륨(동률 tie-break용)
# §3.7A intent 규칙 미적용은 의도적 스코프: 스펙이 intent 반영 대상으로 열거한 것은
# stats의 부위 귀속 쿼리(summary muscle_sets / volume per_muscle·per_region / muscles)뿐이고,
# 세션 주부위 태그는 "무슨 운동을 구성했나"를 나타내는 종목 정적 매핑 기준을 유지한다.
# intent 반영으로 바꾸려면 stats.py의 MUSCLE_ATTRIB를 재사용할 것.
_MAIN_REGION_SQL = """
SELECT session_id, region, SUM(ex_vol) AS vol, MAX(ex_vol) AS top_ex_vol
FROM (
    SELECT sv.session_id AS session_id, mg.region AS region,
           SUM(sv.volume_kg * CASE em.role WHEN 'primary' THEN 1.0 ELSE 0.5 END)
               AS ex_vol
    FROM set_volume sv
    JOIN exercise_muscle em ON em.exercise_id = sv.exercise_id
    JOIN muscle_group mg ON mg.id = em.muscle_group_id
    WHERE sv.is_warmup = 0 AND sv.session_id IN ({placeholders})
    GROUP BY sv.session_id, mg.region, sv.exercise_id
)
GROUP BY session_id, region
"""


def _main_regions(db: sqlite3.Connection, session_ids: list[int]) -> dict[int, str]:
    """세션별 주부위 region. 가중 볼륨 최대 region — 동률이면 볼륨 큰 종목을
    가진 region, 그래도 같으면 고정 region 순서. 항상 결정적."""
    if not session_ids:
        return {}
    placeholders = ",".join("?" * len(session_ids))
    rows = db.execute(
        _MAIN_REGION_SQL.format(placeholders=placeholders), session_ids
    ).fetchall()
    best: dict[int, tuple[float, float, int]] = {}
    result: dict[int, str] = {}
    for r in rows:
        key = (r["vol"], r["top_ex_vol"], -_REGION_ORDER[r["region"]])
        if r["session_id"] not in best or key > best[r["session_id"]]:
            best[r["session_id"]] = key
            result[r["session_id"]] = r["region"]
    return result


def _region_fields(region: str | None) -> dict:
    return {
        "main_region": region,
        "main_region_ko": REGION_NAMES_KO[region] if region is not None else None,
    }


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
) -> list[SessionSummary]:
    rows = db.execute(
        _SESSION_SUMMARY_SQL
        + """
        WHERE (:date_from IS NULL OR s.date >= :date_from)
          AND (:date_to IS NULL OR s.date <= :date_to)
        GROUP BY s.id
        ORDER BY s.date DESC, s.id DESC
        LIMIT :limit OFFSET :offset
        """,
        {"date_from": date_from, "date_to": date_to, "limit": limit, "offset": offset},
    ).fetchall()
    regions = _main_regions(db, [r["id"] for r in rows])
    return [
        SessionSummary(**dict(r), **_region_fields(regions.get(r["id"]))) for r in rows
    ]


def _session_summary(db: sqlite3.Connection, session_id: int) -> SessionSummary | None:
    row = db.execute(
        _SESSION_SUMMARY_SQL + " WHERE s.id = ? GROUP BY s.id", (session_id,)
    ).fetchone()
    if row is None:
        return None
    region = _main_regions(db, [session_id]).get(session_id)
    return SessionSummary(**dict(row), **_region_fields(region))


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: int, db: sqlite3.Connection = Depends(get_db)
) -> SessionDetail:
    summary = _session_summary(db, session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    session_created_at = db.execute(
        "SELECT created_at FROM workout_session WHERE id = ?", (session_id,)
    ).fetchone()["created_at"]
    rows = db.execute(
        """
        SELECT ws.id, ws.client_id, ws.exercise_id, ws.set_index, ws.weight_kg,
               ws.reps, ws.is_warmup, ws.note, ws.created_at, sv.volume_kg, e.name_ko,
               img.code AS intent_muscle, img.name_ko AS intent_muscle_ko
        FROM workout_set ws
        JOIN set_volume sv ON sv.set_id = ws.id
        JOIN exercise e ON e.id = ws.exercise_id
        LEFT JOIN muscle_group img ON img.id = ws.intent_muscle_group_id
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
                exercise_id=r["exercise_id"], name_ko=r["name_ko"], sets=[]
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
                intent_muscle=r["intent_muscle"],
                intent_muscle_ko=r["intent_muscle_ko"],
            )
        )
    return SessionDetail(
        **summary.model_dump(),
        created_at=session_created_at,
        exercises=list(groups.values()),
    )


@router.patch("/sessions/{session_id}", response_model=SessionSummary)
def update_session(
    session_id: int, body: SessionUpdate, db: sqlite3.Connection = Depends(get_db)
) -> SessionSummary:
    row = db.execute(
        "SELECT id FROM workout_session WHERE id = ?", (session_id,)
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
    summary = _session_summary(db, session_id)
    assert summary is not None
    return summary


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, db: sqlite3.Connection = Depends(get_db)) -> None:
    cur = db.execute("DELETE FROM workout_session WHERE id = ?", (session_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")


@router.get("/bodyweight", response_model=list[BodyWeightOut])
def list_bodyweight(
    limit: int = Query(default=30, ge=1, le=1000),
    db: sqlite3.Connection = Depends(get_db),
) -> list[BodyWeightOut]:
    rows = db.execute(
        "SELECT id, date, weight_kg FROM body_weight_log ORDER BY date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [BodyWeightOut(**dict(r)) for r in rows]


@router.post("/bodyweight", response_model=BodyWeightOut)
def upsert_bodyweight(
    body: BodyWeightUpsert, db: sqlite3.Connection = Depends(get_db)
) -> BodyWeightOut:
    db.execute(
        """
        INSERT INTO body_weight_log (date, weight_kg) VALUES (?, ?)
        ON CONFLICT(date) DO UPDATE SET weight_kg = excluded.weight_kg
        """,
        (body.date, body.weight_kg),
    )
    row = db.execute(
        "SELECT id, date, weight_kg FROM body_weight_log WHERE date = ?", (body.date,)
    ).fetchone()
    return BodyWeightOut(**dict(row))
