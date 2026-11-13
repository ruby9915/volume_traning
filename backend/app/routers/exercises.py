import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CurrentUser, require_auth
from ..db import get_db
from ..schemas import (
    ExerciseCreate,
    ExerciseOut,
    ExerciseUpdate,
    FavoritesOut,
    FavoritesReplace,
    LastRecordOut,
)
from ..seed import replace_secondary_targets, tags_to_text
from .catalog import target_id_or_422

router = APIRouter(prefix="/api", tags=["exercises"])

# 내장(user_id NULL)은 모두에게, 커스텀은 소유자에게만 보인다
_VISIBLE = "(e.user_id IS NULL OR e.user_id = ?)"

_EXERCISE_SQL = """
SELECT e.*, t.code AS default_target, t.name_ko AS default_target_ko
FROM exercise e
LEFT JOIN muscle_group t ON t.id = e.default_target_id
"""

# §15.3 종목별 "내가 마지막으로 쓴 머신" — 기록 화면 머신 칩의 기본값.
# 그 종목의 내 세트를 최근 순으로 보되, 내 머신에서 뺀 머신의 세트는 건너뛴다(헬스장을 옮겨
# 머신을 빼면 옛 머신이 기본값으로 따라오지 않는다). 가장 최근 세트에 머신이 없으면 결과에 없다.
_LAST_MACHINE_SQL = """
SELECT x.exercise_id AS exercise_id, x.machine_id AS machine_id, m.name_ko AS machine_name
FROM (
    SELECT ws.exercise_id, ws.machine_id,
           ROW_NUMBER() OVER (
               PARTITION BY ws.exercise_id
               ORDER BY s.date DESC, s.id DESC, ws.set_index DESC
           ) AS rn
    FROM workout_set ws
    JOIN workout_session s ON s.id = ws.session_id
    WHERE s.user_id = :uid
      AND (:eid IS NULL OR ws.exercise_id = :eid)
      AND (ws.machine_id IS NULL
           OR ws.machine_id IN (SELECT machine_id FROM user_machine WHERE user_id = :uid))
) x
JOIN machine m ON m.id = x.machine_id
WHERE x.rn = 1
"""


def _last_machines(
    db: sqlite3.Connection, user_id: int, exercise_id: int | None = None
) -> dict[int, sqlite3.Row]:
    """종목 id → (machine_id, machine_name). exercise_id를 주면 그 종목만."""
    rows = db.execute(_LAST_MACHINE_SQL, {"uid": user_id, "eid": exercise_id}).fetchall()
    return {r["exercise_id"]: r for r in rows}


def _split_tags(text: str | None) -> list[str]:
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def _secondaries(db: sqlite3.Connection, exercise_ids: list[int]) -> dict[int, list[sqlite3.Row]]:
    """§11.2 종목 id → 보조 근육 행(code, name_ko) 목록. 목록 조회는 한 번의 쿼리로."""
    out: dict[int, list[sqlite3.Row]] = {}
    if not exercise_ids:
        return out
    marks = ",".join("?" * len(exercise_ids))
    for r in db.execute(
        f"""
        SELECT est.exercise_id, mg.code, mg.name_ko FROM exercise_secondary_target est
        JOIN muscle_group mg ON mg.id = est.target_id
        WHERE est.exercise_id IN ({marks}) ORDER BY mg.sort_order, mg.id
        """,
        exercise_ids,
    ).fetchall():
        out.setdefault(r["exercise_id"], []).append(r)
    return out


def _secondary_ids_or_422(
    db: sqlite3.Connection, codes: list[str], default_target_id: int
) -> list[int]:
    ids: list[int] = []
    for code in codes:
        tid = target_id_or_422(db, code)
        if tid == default_target_id:
            raise HTTPException(status_code=422, detail=f"보조 근육 '{code}'는 기본 타겟과 같습니다")
        if tid not in ids:
            ids.append(tid)
    return ids


def _to_out(
    row: sqlite3.Row,
    user: CurrentUser,
    secondaries: list[sqlite3.Row] = (),
    last_machine: sqlite3.Row | None = None,
) -> ExerciseOut:
    if row["default_target"] is None:
        # 마이그레이션이 채우지 못한 행 — 숨기지 말고 드러낸다 (§10.3)
        raise HTTPException(status_code=500, detail=f"종목 '{row['name_ko']}'에 기본 타겟이 없습니다")
    return ExerciseOut(
        id=row["id"],
        name_ko=row["name_ko"],
        name_en=row["name_en"],
        base_movement=row["base_movement"],
        tags=_split_tags(row["tags"]),
        default_target=row["default_target"],
        default_target_ko=row["default_target_ko"],
        secondary_targets=[r["code"] for r in secondaries],
        secondary_targets_ko=[r["name_ko"] for r in secondaries],
        last_machine_id=last_machine["machine_id"] if last_machine else None,
        last_machine_name=last_machine["machine_name"] if last_machine else None,
        bodyweight_factor=row["bodyweight_factor"],
        load_multiplier=row["load_multiplier"],
        is_builtin=bool(row["is_builtin"]),
        is_archived=bool(row["is_archived"]),
        is_own=row["user_id"] == user.id,
        note=row["note"],
        aliases=row["aliases"],
    )


def _get_visible_row(db: sqlite3.Connection, user: CurrentUser, exercise_id: int) -> sqlite3.Row:
    row = db.execute(
        _EXERCISE_SQL + f" WHERE e.id = ? AND {_VISIBLE}", (exercise_id, user.id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    return row


def _require_editable(row: sqlite3.Row, user: CurrentUser) -> None:
    """내장은 관리자만, 커스텀은 소유자만 수정·삭제 (§10.3 — 공용 데이터 보호)."""
    if row["is_builtin"]:
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="내장 종목은 관리자만 수정할 수 있습니다")
    elif row["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")


@router.get("/exercises", response_model=list[ExerciseOut])
def list_exercises(
    include_archived: bool = False,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> list[ExerciseOut]:
    rows = db.execute(
        _EXERCISE_SQL + f" WHERE {_VISIBLE} AND (? OR e.is_archived = 0) ORDER BY e.id",
        (user.id, 1 if include_archived else 0),
    ).fetchall()
    secondaries = _secondaries(db, [r["id"] for r in rows])
    last_machines = _last_machines(db, user.id)
    return [
        _to_out(r, user, secondaries.get(r["id"], []), last_machines.get(r["id"])) for r in rows
    ]


def _out_one(db: sqlite3.Connection, user: CurrentUser, exercise_id: int) -> ExerciseOut:
    row = _get_visible_row(db, user, exercise_id)
    return _to_out(
        row,
        user,
        _secondaries(db, [exercise_id]).get(exercise_id, []),
        _last_machines(db, user.id, exercise_id).get(exercise_id),
    )


@router.post("/exercises", status_code=201)
def create_exercise(
    payload: ExerciseCreate,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    existing = db.execute(
        "SELECT id, name_ko, is_archived, user_id FROM exercise WHERE name_ko = ?",
        (payload.name_ko,),
    ).fetchone()
    if existing is not None:
        visible = existing["user_id"] is None or existing["user_id"] == user.id
        if visible and existing["is_archived"]:
            # 계약(types.ts ArchivedConflictDetail): 409 + detail.code="archived_exists"
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "archived_exists",
                    "exercise_id": existing["id"],
                    "name_ko": existing["name_ko"],
                },
            )
        raise HTTPException(status_code=409, detail="같은 이름의 종목이 이미 있습니다")
    target_id = target_id_or_422(db, payload.default_target)
    secondary_ids = _secondary_ids_or_422(db, payload.secondary_targets, target_id)
    cur = db.execute(
        "INSERT INTO exercise (name_ko, name_en, bodyweight_factor, load_multiplier, note,"
        " base_movement, tags, aliases, default_target_id, user_id, is_builtin)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (
            payload.name_ko, payload.name_en, payload.bodyweight_factor,
            payload.load_multiplier, payload.note, payload.base_movement,
            tags_to_text(payload.tags), payload.aliases, target_id, user.id,
        ),
    )
    replace_secondary_targets(db, cur.lastrowid, secondary_ids)
    return _out_one(db, user, cur.lastrowid)


@router.patch("/exercises/{exercise_id}", response_model=ExerciseOut)
def update_exercise(
    exercise_id: int,
    payload: ExerciseUpdate,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> ExerciseOut:
    row = _get_visible_row(db, user, exercise_id)
    _require_editable(row, user)
    data = payload.model_dump(exclude_unset=True)
    if "name_ko" in data:
        dup = db.execute(
            "SELECT id FROM exercise WHERE name_ko = ? AND id != ?",
            (data["name_ko"], exercise_id),
        ).fetchone()
        if dup is not None:
            raise HTTPException(status_code=409, detail="같은 이름의 종목이 이미 있습니다")
    if "tags" in data:
        data["tags"] = None if data["tags"] is None else tags_to_text(data["tags"])
    if "default_target" in data:
        code = data.pop("default_target")
        if code is None:
            raise HTTPException(status_code=422, detail="default_target는 null일 수 없습니다")
        data["default_target_id"] = target_id_or_422(db, code)
    new_default_id = data.get("default_target_id", row["default_target_id"])
    secondary_ids: list[int] | None = None
    if "secondary_targets" in data:
        codes = data.pop("secondary_targets")
        if codes is None:
            raise HTTPException(status_code=422, detail="secondary_targets는 null일 수 없습니다 (빈 배열로 해제)")
        secondary_ids = _secondary_ids_or_422(db, codes, new_default_id)
    elif "default_target_id" in data:
        # 기본 타겟이 바뀌어 기존 보조 근육과 겹치면 그 보조 근육은 조용히 뺀다 (겹침 불변식 유지)
        db.execute(
            "DELETE FROM exercise_secondary_target WHERE exercise_id = ? AND target_id = ?",
            (exercise_id, new_default_id),
        )
    if "is_archived" in data:
        data["is_archived"] = int(data["is_archived"])
    if data:
        assignments = ", ".join(f"{k} = ?" for k in data)
        db.execute(
            f"UPDATE exercise SET {assignments} WHERE id = ?",
            (*data.values(), exercise_id),
        )
    if secondary_ids is not None:
        replace_secondary_targets(db, exercise_id, secondary_ids)
    return _out_one(db, user, exercise_id)


@router.delete("/exercises/{exercise_id}")
def delete_exercise(
    exercise_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    row = _get_visible_row(db, user, exercise_id)
    _require_editable(row, user)
    has_sets = db.execute(
        "SELECT 1 FROM workout_set WHERE exercise_id = ? LIMIT 1", (exercise_id,)
    ).fetchone()
    # 계약(types.ts ExerciseDeleteResponse): {deleted, archived}
    if has_sets is not None:
        db.execute("UPDATE exercise SET is_archived = 1 WHERE id = ?", (exercise_id,))
        return {"deleted": False, "archived": True}
    db.execute("DELETE FROM exercise WHERE id = ?", (exercise_id,))
    return {"deleted": True, "archived": False}


@router.post("/exercises/{exercise_id}/restore", response_model=ExerciseOut)
def restore_exercise(
    exercise_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> ExerciseOut:
    row = _get_visible_row(db, user, exercise_id)
    _require_editable(row, user)
    db.execute("UPDATE exercise SET is_archived = 0 WHERE id = ?", (exercise_id,))
    return _out_one(db, user, exercise_id)


@router.get("/exercises/{exercise_id}/last-record", response_model=LastRecordOut)
def last_record(
    exercise_id: int,
    machine: str | None = Query(
        default=None,
        pattern=r"^(none|\d+)$",
        description="§15.3 머신 범위: 생략 = 머신과 무관, 'none' = 머신 없이 한 기록, 숫자 = 그 머신 id",
    ),
    exclude_session: int | None = Query(
        default=None,
        description="이 세션은 빼고 찾는다 — 지금 기록 중인 세션의 세트가 '지난번'으로 나오지 않게",
    ),
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> LastRecordOut:
    """이 종목을 마지막으로 한 세션의 세트. machine을 주면 그 머신으로 한 세트만 본다 (§15.3 —
    머신이 다르면 걸리는 무게가 달라 지난 기록도 머신별로 따로 보여 준다)."""
    _get_visible_row(db, user, exercise_id)
    scope_sql, scope_params = "", []
    if machine == "none":
        scope_sql = " AND ws.machine_id IS NULL"
    elif machine is not None:
        scope_sql, scope_params = " AND ws.machine_id = ?", [int(machine)]
    if exclude_session is not None:
        scope_sql += " AND ws.session_id != ?"
        scope_params = [*scope_params, exclude_session]
    last = db.execute(
        f"""
        SELECT s.id AS session_id, s.date AS date,
               ws.machine_id AS machine_id, m.name_ko AS machine_name
        FROM workout_set ws
        JOIN workout_session s ON s.id = ws.session_id
        LEFT JOIN machine m ON m.id = ws.machine_id
        WHERE ws.exercise_id = ? AND s.user_id = ?{scope_sql}
        ORDER BY s.date DESC, s.id DESC, ws.set_index DESC
        LIMIT 1
        """,
        (exercise_id, user.id, *scope_params),
    ).fetchone()
    if last is None:
        raise HTTPException(status_code=404, detail="이전 기록이 없습니다")
    sets = db.execute(
        "SELECT ws.weight_kg, ws.reps, ws.is_warmup FROM workout_set ws"
        f" WHERE ws.session_id = ? AND ws.exercise_id = ?{scope_sql} ORDER BY ws.set_index",
        (last["session_id"], exercise_id, *scope_params),
    ).fetchall()
    return LastRecordOut(
        session_id=last["session_id"],
        session_date=last["date"],
        machine_id=last["machine_id"],
        machine_name=last["machine_name"],
        sets=[
            {
                "weight_kg": r["weight_kg"],
                "reps": r["reps"],
                "is_warmup": bool(r["is_warmup"]),
            }
            for r in sets
        ],
    )


# ---------- 즐겨찾기 (§10.3) ----------


def _favorites(db: sqlite3.Connection, user_id: int) -> FavoritesOut:
    rows = db.execute(
        "SELECT exercise_id FROM favorite WHERE user_id = ? ORDER BY sort_order, exercise_id",
        (user_id,),
    ).fetchall()
    return FavoritesOut(exercise_ids=[r["exercise_id"] for r in rows])


@router.get("/favorites", response_model=FavoritesOut)
def list_favorites(
    user: CurrentUser = Depends(require_auth), db: sqlite3.Connection = Depends(get_db)
) -> FavoritesOut:
    return _favorites(db, user.id)


@router.put("/favorites", response_model=FavoritesOut)
def replace_favorites(
    body: FavoritesReplace,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> FavoritesOut:
    """순서 포함 전체 교체 — 즐겨찾기 정렬 편집용."""
    ids: list[int] = []
    for eid in body.exercise_ids:
        if eid not in ids:
            ids.append(eid)
    for eid in ids:
        _get_visible_row(db, user, eid)
    db.execute("DELETE FROM favorite WHERE user_id = ?", (user.id,))
    for i, eid in enumerate(ids):
        db.execute(
            "INSERT INTO favorite (user_id, exercise_id, sort_order) VALUES (?, ?, ?)",
            (user.id, eid, i),
        )
    return _favorites(db, user.id)


@router.post("/favorites/{exercise_id}", response_model=FavoritesOut)
def add_favorite(
    exercise_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> FavoritesOut:
    _get_visible_row(db, user, exercise_id)
    next_order = db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM favorite WHERE user_id = ?", (user.id,)
    ).fetchone()[0]
    db.execute(
        "INSERT OR IGNORE INTO favorite (user_id, exercise_id, sort_order) VALUES (?, ?, ?)",
        (user.id, exercise_id, next_order),
    )
    return _favorites(db, user.id)


@router.delete("/favorites/{exercise_id}", response_model=FavoritesOut)
def remove_favorite(
    exercise_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> FavoritesOut:
    db.execute(
        "DELETE FROM favorite WHERE user_id = ? AND exercise_id = ?", (user.id, exercise_id)
    )
    return _favorites(db, user.id)
