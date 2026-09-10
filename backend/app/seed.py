"""시드 — 타겟 분류·내장 종목 라이브러리·머신 카탈로그를 기동 시 INSERT OR IGNORE.

데이터는 seed_data/ 패키지, 여기는 삽입 로직만. 커밋은 호출측(db.init_db)이 한다.
"""

import sqlite3

from .seed_data.exercises import EXERCISES
from .seed_data.machines import MACHINES
from .seed_data.secondary import SECONDARY
from .seed_data.targets import TARGETS


def tags_to_text(tags: tuple[str, ...] | list[str]) -> str | None:
    cleaned = [t.strip() for t in tags if t and t.strip()]
    return ",".join(cleaned) if cleaned else None


def seed_targets(conn: sqlite3.Connection) -> None:
    """level 2 먼저(부모), level 3 다음. 기존 행은 이름·정렬만 최신으로 맞춘다 (코드 불변)."""
    for code, name_ko, region, level, parent_code, sort_order in sorted(TARGETS, key=lambda t: t[3]):
        parent_id = None
        if parent_code is not None:
            parent_id = conn.execute(
                "SELECT id FROM muscle_group WHERE code = ?", (parent_code,)
            ).fetchone()[0]
        cur = conn.execute(
            "INSERT OR IGNORE INTO muscle_group (code, name_ko, region, sort_order, level, parent_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (code, name_ko, region, sort_order, level, parent_id),
        )
        if cur.rowcount == 0:
            # v3 이전 행(12분류)은 level/parent 컬럼이 기본값 — 분류 메타만 갱신
            conn.execute(
                "UPDATE muscle_group SET name_ko = ?, region = ?, sort_order = ?, level = ?, parent_id = ?"
                " WHERE code = ?",
                (name_ko, region, sort_order, level, parent_id, code),
            )


def target_id_by_code(conn: sqlite3.Connection, code: str) -> int | None:
    row = conn.execute("SELECT id FROM muscle_group WHERE code = ?", (code,)).fetchone()
    return None if row is None else row[0]


def replace_secondary_targets(
    conn: sqlite3.Connection, exercise_id: int, target_ids: list[int] | tuple[int, ...]
) -> None:
    """§11.2 종목의 보조 근육 목록 교체 (라우터·시드 공용)."""
    conn.execute("DELETE FROM exercise_secondary_target WHERE exercise_id = ?", (exercise_id,))
    for tid in target_ids:
        conn.execute(
            "INSERT OR IGNORE INTO exercise_secondary_target (exercise_id, target_id) VALUES (?, ?)",
            (exercise_id, tid),
        )


def seed_exercises(conn: sqlite3.Connection) -> int:
    """내장 종목 INSERT OR IGNORE (name_ko 기준). 반환: 새로 들어간 행 수.
    새로 들어간 행만 보조 근육(SECONDARY)도 함께 — 기존 행의 보조 근육은 앱에서 관리."""
    inserted = 0
    for name_ko, name_en, base, tags, target, bw, mult, aliases in EXERCISES:
        target_id = target_id_by_code(conn, target)
        if target_id is None:
            raise ValueError(f"seed exercise '{name_ko}': unknown target '{target}'")
        cur = conn.execute(
            "INSERT OR IGNORE INTO exercise"
            " (name_ko, name_en, bodyweight_factor, load_multiplier, is_builtin,"
            "  base_movement, tags, aliases, default_target_id)"
            " VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
            (name_ko, name_en, bw, mult, base, tags_to_text(tags), aliases, target_id),
        )
        if cur.rowcount:
            inserted += 1
            ids = []
            for code in SECONDARY.get(name_ko, ()):
                tid = target_id_by_code(conn, code)
                if tid is None:
                    raise ValueError(f"seed secondary '{name_ko}': unknown target '{code}'")
                if tid != target_id:
                    ids.append(tid)
            replace_secondary_targets(conn, cur.lastrowid, ids)
    return inserted


def seed_machines(conn: sqlite3.Connection) -> None:
    for brand, model, name_ko, target in MACHINES:
        target_id = target_id_by_code(conn, target) if target else None
        conn.execute(
            "INSERT OR IGNORE INTO machine (brand, model, name_ko, target_id) VALUES (?, ?, ?, ?)",
            (brand, model, name_ko, target_id),
        )


def seed(conn: sqlite3.Connection) -> None:
    seed_targets(conn)
    seed_exercises(conn)
    seed_machines(conn)
