import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..db import get_db
from ..schemas import (
    ExerciseCreate,
    ExerciseOut,
    ExerciseUpdate,
    LastRecordOut,
    MuscleAssignment,
)

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


def _muscles_for(db: sqlite3.Connection, exercise_ids: list[int]) -> dict[int, list[dict]]:
    if not exercise_ids:
        return {}
    placeholders = ",".join("?" * len(exercise_ids))
    rows = db.execute(
        f"""
        SELECT em.exercise_id, mg.code, em.role
        FROM exercise_muscle em
        JOIN muscle_group mg ON mg.id = em.muscle_group_id
        WHERE em.exercise_id IN ({placeholders})
        ORDER BY em.exercise_id,
                 CASE em.role WHEN 'primary' THEN 0 ELSE 1 END,
                 mg.sort_order
        """,
        exercise_ids,
    ).fetchall()
    out: dict[int, list[dict]] = {eid: [] for eid in exercise_ids}
    for r in rows:
        out[r["exercise_id"]].append({"code": r["code"], "role": r["role"]})
    return out


def _to_out(row: sqlite3.Row, muscles: list[dict]) -> ExerciseOut:
    return ExerciseOut(
        id=row["id"],
        name_ko=row["name_ko"],
        name_en=row["name_en"],
        bodyweight_factor=row["bodyweight_factor"],
        load_multiplier=row["load_multiplier"],
        is_builtin=bool(row["is_builtin"]),
        is_archived=bool(row["is_archived"]),
        note=row["note"],
        muscles=muscles,
        base_movement=row["base_movement"],
        equipment=row["equipment"],
        support=row["support"],
        grip=row["grip"],
        angle=row["angle"],
        aliases=row["aliases"],
    )


def _get_exercise_out(db: sqlite3.Connection, exercise_id: int) -> ExerciseOut:
    row = db.execute("SELECT * FROM exercise WHERE id = ?", (exercise_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    return _to_out(row, _muscles_for(db, [exercise_id])[exercise_id])


def _replace_muscles(
    db: sqlite3.Connection, exercise_id: int, muscles: list[MuscleAssignment]
) -> None:
    db.execute("DELETE FROM exercise_muscle WHERE exercise_id = ?", (exercise_id,))
    for m in muscles:
        db.execute(
            "INSERT INTO exercise_muscle (exercise_id, muscle_group_id, role)"
            " SELECT ?, id, ? FROM muscle_group WHERE code = ?",
            (exercise_id, m.role, m.code),
        )


@router.get("", response_model=list[ExerciseOut])
def list_exercises(
    include_archived: bool = False, db: sqlite3.Connection = Depends(get_db)
) -> list[ExerciseOut]:
    rows = db.execute(
        "SELECT * FROM exercise WHERE ? OR is_archived = 0 ORDER BY id",
        (1 if include_archived else 0,),
    ).fetchall()
    muscles = _muscles_for(db, [r["id"] for r in rows])
    return [_to_out(r, muscles[r["id"]]) for r in rows]


@router.post("", status_code=201)
def create_exercise(payload: ExerciseCreate, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute(
        "SELECT * FROM exercise WHERE name_ko = ?", (payload.name_ko,)
    ).fetchone()
    if existing is not None:
        if existing["is_archived"]:
            # 계약(types.ts ArchivedConflictDetail): 409 + detail.code="archived_exists"
            # — 프론트가 이 detail로 복원 안내 UI를 띄운다 (§4.2 복원 안내 응답)
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "archived_exists",
                    "exercise_id": existing["id"],
                    "name_ko": existing["name_ko"],
                },
            )
        raise HTTPException(status_code=409, detail="같은 이름의 종목이 이미 있습니다")
    cur = db.execute(
        "INSERT INTO exercise (name_ko, name_en, bodyweight_factor, load_multiplier, note,"
        " base_movement, equipment, support, grip, angle, aliases)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            payload.name_ko, payload.name_en, payload.bodyweight_factor,
            payload.load_multiplier, payload.note,
            payload.base_movement, payload.equipment, payload.support,
            payload.grip, payload.angle, payload.aliases,
        ),
    )
    exercise_id = cur.lastrowid
    _replace_muscles(db, exercise_id, payload.muscles)
    return _get_exercise_out(db, exercise_id)


@router.patch("/{exercise_id}", response_model=ExerciseOut)
def update_exercise(
    exercise_id: int, payload: ExerciseUpdate, db: sqlite3.Connection = Depends(get_db)
) -> ExerciseOut:
    row = db.execute("SELECT id FROM exercise WHERE id = ?", (exercise_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    data = payload.model_dump(exclude_unset=True)
    data.pop("muscles", None)
    if "name_ko" in data:
        dup = db.execute(
            "SELECT id FROM exercise WHERE name_ko = ? AND id != ?",
            (data["name_ko"], exercise_id),
        ).fetchone()
        if dup is not None:
            raise HTTPException(status_code=409, detail="같은 이름의 종목이 이미 있습니다")
    if "is_archived" in data:
        data["is_archived"] = int(data["is_archived"])
    if data:
        assignments = ", ".join(f"{k} = ?" for k in data)
        db.execute(
            f"UPDATE exercise SET {assignments} WHERE id = ?",
            (*data.values(), exercise_id),
        )
    if payload.muscles is not None:
        _replace_muscles(db, exercise_id, payload.muscles)
    return _get_exercise_out(db, exercise_id)


@router.delete("/{exercise_id}")
def delete_exercise(exercise_id: int, db: sqlite3.Connection = Depends(get_db)) -> dict:
    row = db.execute("SELECT id FROM exercise WHERE id = ?", (exercise_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    has_sets = db.execute(
        "SELECT 1 FROM workout_set WHERE exercise_id = ? LIMIT 1", (exercise_id,)
    ).fetchone()
    # 계약(types.ts ExerciseDeleteResponse): {deleted, archived}
    if has_sets is not None:
        db.execute("UPDATE exercise SET is_archived = 1 WHERE id = ?", (exercise_id,))
        return {"deleted": False, "archived": True}
    db.execute("DELETE FROM exercise WHERE id = ?", (exercise_id,))
    return {"deleted": True, "archived": False}


@router.post("/{exercise_id}/restore", response_model=ExerciseOut)
def restore_exercise(
    exercise_id: int, db: sqlite3.Connection = Depends(get_db)
) -> ExerciseOut:
    row = db.execute("SELECT id FROM exercise WHERE id = ?", (exercise_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    db.execute("UPDATE exercise SET is_archived = 0 WHERE id = ?", (exercise_id,))
    return _get_exercise_out(db, exercise_id)


@router.get("/{exercise_id}/last-record", response_model=LastRecordOut)
def last_record(
    exercise_id: int, db: sqlite3.Connection = Depends(get_db)
) -> LastRecordOut:
    ex = db.execute("SELECT id FROM exercise WHERE id = ?", (exercise_id,)).fetchone()
    if ex is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    last = db.execute(
        """
        SELECT s.id AS session_id, s.date AS date
        FROM workout_set ws
        JOIN workout_session s ON s.id = ws.session_id
        WHERE ws.exercise_id = ?
        ORDER BY s.date DESC, s.id DESC
        LIMIT 1
        """,
        (exercise_id,),
    ).fetchone()
    if last is None:
        raise HTTPException(status_code=404, detail="이전 기록이 없습니다")
    sets = db.execute(
        "SELECT weight_kg, reps, is_warmup FROM workout_set"
        " WHERE session_id = ? AND exercise_id = ? ORDER BY set_index",
        (last["session_id"], exercise_id),
    ).fetchall()
    return LastRecordOut(
        session_id=last["session_id"],
        session_date=last["date"],
        sets=[
            {
                "weight_kg": r["weight_kg"],
                "reps": r["reps"],
                "is_warmup": bool(r["is_warmup"]),
            }
            for r in sets
        ],
    )
