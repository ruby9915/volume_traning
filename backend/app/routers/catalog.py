"""타겟 분류·머신 카탈로그 조회 (§10.2, §10.4). 분류는 데이터라 프론트가 여기서 받아 쓴다."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CurrentUser, require_auth
from ..db import get_db
from ..machine_match import ExerciseInfo, MachineInfo, suggest
from ..schemas import (
    BrandCountOut,
    MachineCreate,
    MachineExercisesOut,
    MachineExerciseUse,
    MachineOut,
    TargetOut,
)

router = APIRouter(prefix="/api", tags=["catalog"])


def target_id_or_422(db: sqlite3.Connection, code: str) -> int:
    row = db.execute("SELECT id FROM muscle_group WHERE code = ?", (code,)).fetchone()
    if row is None:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 타겟 code입니다: {code}")
    return row["id"]


@router.get("/targets", response_model=list[TargetOut])
def list_targets(db: sqlite3.Connection = Depends(get_db)) -> list[TargetOut]:
    rows = db.execute(
        """
        SELECT t.code, t.name_ko, t.region, t.level, p.code AS parent_code
        FROM muscle_group t LEFT JOIN muscle_group p ON p.id = t.parent_id
        ORDER BY t.sort_order, t.id
        """
    ).fetchall()
    return [TargetOut(**dict(r)) for r in rows]


def machine_id_or_422(db: sqlite3.Connection, machine_id: int | None) -> int | None:
    """세트에 붙일 머신 id 검증 (§15.1). None은 그대로 — 머신 없음."""
    if machine_id is None:
        return None
    if db.execute("SELECT 1 FROM machine WHERE id = ?", (machine_id,)).fetchone() is None:
        raise HTTPException(status_code=422, detail="machine_id에 해당하는 머신이 없습니다")
    return machine_id


def ensure_my_machine(db: sqlite3.Connection, user_id: int, machine_id: int | None) -> None:
    """세트에 쓴 머신은 내 머신에 들어 있게 한다 (§15.3) — 다음 기록의 기본 머신 계산이 내 머신 기준이라서."""
    if machine_id is not None:
        db.execute(
            "INSERT OR IGNORE INTO user_machine (user_id, machine_id) VALUES (?, ?)",
            (user_id, machine_id),
        )


def _machine_out(row: sqlite3.Row) -> MachineOut:
    return MachineOut(
        id=row["id"], brand=row["brand"], model=row["model"],
        name_ko=row["name_ko"], target=row["target"],
    )


_MACHINE_SQL = """
SELECT m.id, m.brand, m.model, m.name_ko, t.code AS target
FROM machine m LEFT JOIN muscle_group t ON t.id = m.target_id
"""


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/machines", response_model=list[MachineOut])
def list_machines(
    q: str | None = Query(None, max_length=80),
    brand: str | None = Query(None, max_length=50),
    region: str | None = Query(None, max_length=20),
    limit: int | None = Query(None, ge=1, le=500),
    db: sqlite3.Connection = Depends(get_db),
) -> list[MachineOut]:
    """아카이브 검색 (§10.4). 파라미터 없으면 전체.

    q는 공백 단위 토큰을 모두 포함해야 매치 (브랜드·모델·한글 별칭 합친 문자열, 대소문자 무시).
    region은 기본 타겟의 부위(chest/back/…) — 타겟 없는 랙·벤치는 부위 필터에 안 잡힌다.
    """
    where: list[str] = []
    params: list[str] = []
    if brand:
        where.append("m.brand = ?")
        params.append(brand)
    if region:
        where.append("t.region = ?")
        params.append(region)
    for tok in (q or "").split():
        where.append("(m.brand || ' ' || m.model || ' ' || m.name_ko) LIKE ? ESCAPE '\\'")
        params.append(f"%{_like_escape(tok)}%")
    sql = _MACHINE_SQL
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY m.brand, m.model"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [_machine_out(r) for r in db.execute(sql, params).fetchall()]


@router.get("/machines/brands", response_model=list[BrandCountOut])
def list_machine_brands(db: sqlite3.Connection = Depends(get_db)) -> list[BrandCountOut]:
    """검색 시트의 브랜드 칩용 — 브랜드별 대수 (많은 순)."""
    rows = db.execute(
        "SELECT brand, COUNT(*) AS count FROM machine GROUP BY brand ORDER BY count DESC, brand"
    ).fetchall()
    return [BrandCountOut(brand=r["brand"], count=r["count"]) for r in rows]


@router.get("/machines/{machine_id}/exercises", response_model=MachineExercisesOut)
def machine_exercises(
    machine_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> MachineExercisesOut:
    """머신을 먼저 골랐을 때의 종목 후보 (§15.4).

    used = 내가 이 머신으로 기록한 종목(최근 순). suggested = 그 밖의 추천(machine_match).
    둘 다 지금 내게 보이는 활성 종목만 — 숨긴 종목은 기록이 있어도 후보에서 빠진다.
    """
    row = db.execute(
        """
        SELECT m.id, m.brand, m.model, m.name_ko,
               tp.code AS target, tp.muscle_code AS muscle, tp.region AS region
        FROM machine m LEFT JOIN target_path tp ON tp.id = m.target_id
        WHERE m.id = ?
        """,
        (machine_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="머신을 찾을 수 없습니다")

    used_rows = db.execute(
        """
        SELECT ws.exercise_id AS exercise_id, COUNT(*) AS set_count, MAX(s.date) AS last_date
        FROM workout_set ws
        JOIN workout_session s ON s.id = ws.session_id
        JOIN exercise e ON e.id = ws.exercise_id
        WHERE s.user_id = ? AND ws.machine_id = ? AND e.is_archived = 0
        GROUP BY ws.exercise_id
        ORDER BY last_date DESC, set_count DESC, ws.exercise_id
        """,
        (user.id, machine_id),
    ).fetchall()
    used_ids = {r["exercise_id"] for r in used_rows}

    # 다른 사용자의 사용 이력은 "그런 적이 있다"는 사실만 추천 점수에 쓴다 (누가·얼마나는 내보내지 않는다)
    used_by_anyone = {
        r[0]
        for r in db.execute(
            "SELECT DISTINCT exercise_id FROM workout_set WHERE machine_id = ?", (machine_id,)
        ).fetchall()
    }
    my_sets = {
        r[0]: r[1]
        for r in db.execute(
            "SELECT ws.exercise_id, COUNT(*) FROM workout_set ws"
            " JOIN workout_session s ON s.id = ws.session_id"
            " WHERE s.user_id = ? GROUP BY ws.exercise_id",
            (user.id,),
        ).fetchall()
    }
    candidates = [
        ExerciseInfo(
            id=r["id"],
            name_ko=r["name_ko"],
            name_en=r["name_en"],
            target=r["target"],
            muscle=r["muscle"],
            region=r["region"],
            tags=frozenset(t.strip() for t in (r["tags"] or "").split(",") if t.strip()),
            aliases=tuple(a.strip() for a in (r["aliases"] or "").split(",") if a.strip()),
            my_sets=my_sets.get(r["id"], 0),
            others_used=r["id"] in used_by_anyone,
        )
        for r in db.execute(
            """
            SELECT e.id, e.name_ko, e.name_en, e.tags, e.aliases,
                   tp.code AS target, tp.muscle_code AS muscle, tp.region AS region
            FROM exercise e JOIN target_path tp ON tp.id = e.default_target_id
            WHERE e.is_archived = 0 AND (e.user_id IS NULL OR e.user_id = ?)
            """,
            (user.id,),
        ).fetchall()
        if r["id"] not in used_ids
    ]
    machine = MachineInfo(
        brand=row["brand"], model=row["model"], name_ko=row["name_ko"],
        target=row["target"], muscle=row["muscle"], region=row["region"],
    )
    return MachineExercisesOut(
        machine=_machine_out(row),
        used=[MachineExerciseUse(**dict(r)) for r in used_rows],
        suggested=suggest(machine, candidates),
    )


# ---------- 내 머신 (§10.4) ----------


def _my_machines(db: sqlite3.Connection, user_id: int) -> list[MachineOut]:
    rows = db.execute(
        _MACHINE_SQL
        + " JOIN user_machine um ON um.machine_id = m.id WHERE um.user_id = ?"
        " ORDER BY um.created_at DESC, m.id DESC",
        (user_id,),
    ).fetchall()
    return [_machine_out(r) for r in rows]


@router.get("/me/machines", response_model=list[MachineOut])
def list_my_machines(
    user: CurrentUser = Depends(require_auth), db: sqlite3.Connection = Depends(get_db)
) -> list[MachineOut]:
    return _my_machines(db, user.id)


@router.post("/me/machines/{machine_id}", response_model=list[MachineOut])
def add_my_machine(
    machine_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> list[MachineOut]:
    if db.execute("SELECT 1 FROM machine WHERE id = ?", (machine_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="머신을 찾을 수 없습니다")
    db.execute(
        "INSERT OR IGNORE INTO user_machine (user_id, machine_id) VALUES (?, ?)",
        (user.id, machine_id),
    )
    return _my_machines(db, user.id)


@router.delete("/me/machines/{machine_id}", response_model=list[MachineOut])
def remove_my_machine(
    machine_id: int,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> list[MachineOut]:
    db.execute(
        "DELETE FROM user_machine WHERE user_id = ? AND machine_id = ?", (user.id, machine_id)
    )
    return _my_machines(db, user.id)


@router.post("/machines", response_model=MachineOut, status_code=201)
def create_machine(
    body: MachineCreate,
    user: CurrentUser = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
) -> MachineOut:
    """아카이브에 없는 머신을 누구나 추가 (공용). 같은 브랜드·모델은 409. 추가한 사람의 내 머신에 자동 등록."""
    dup = db.execute(
        "SELECT id FROM machine WHERE brand = ? AND model = ?", (body.brand, body.model)
    ).fetchone()
    if dup is not None:
        raise HTTPException(status_code=409, detail="같은 브랜드·모델의 머신이 이미 있습니다")
    target_id = target_id_or_422(db, body.target) if body.target else None
    cur = db.execute(
        "INSERT INTO machine (brand, model, name_ko, target_id) VALUES (?, ?, ?, ?)",
        (body.brand, body.model, body.name_ko or f"{body.brand} {body.model}", target_id),
    )
    db.execute(
        "INSERT OR IGNORE INTO user_machine (user_id, machine_id) VALUES (?, ?)",
        (user.id, cur.lastrowid),
    )
    row = db.execute(_MACHINE_SQL + " WHERE m.id = ?", (cur.lastrowid,)).fetchone()
    return _machine_out(row)
