"""타겟 분류·머신 카탈로그 조회 (§10.2, §10.4). 분류는 데이터라 프론트가 여기서 받아 쓴다."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CurrentUser, require_auth
from ..db import get_db
from ..schemas import BrandCountOut, MachineCreate, MachineOut, TargetOut

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
