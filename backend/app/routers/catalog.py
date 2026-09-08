"""타겟 분류·머신 카탈로그 조회 (§10.2, §10.4). 분류는 데이터라 프론트가 여기서 받아 쓴다."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..db import get_db
from ..schemas import MachineCreate, MachineOut, TargetOut

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


@router.get("/machines", response_model=list[MachineOut])
def list_machines(db: sqlite3.Connection = Depends(get_db)) -> list[MachineOut]:
    rows = db.execute(_MACHINE_SQL + " ORDER BY m.brand, m.model").fetchall()
    return [_machine_out(r) for r in rows]


@router.post("/machines", response_model=MachineOut, status_code=201)
def create_machine(body: MachineCreate, db: sqlite3.Connection = Depends(get_db)) -> MachineOut:
    """카탈로그에 없는 머신을 누구나 추가 (공용). 같은 브랜드·모델은 409."""
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
    row = db.execute(_MACHINE_SQL + " WHERE m.id = ?", (cur.lastrowid,)).fetchone()
    return _machine_out(row)
