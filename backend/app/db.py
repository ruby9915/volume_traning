import sqlite3
from collections.abc import Iterator
from pathlib import Path

from .config import get_settings
from .seed_exercises import backfill_attributes, seed

# set_volume VIEW 단일 정의 — DDL(신규 DB)과 v3 마이그레이션(DROP 후 재생성)이
# 같은 문자열을 쓴다. §3.7: intent_muscle_group_id 패스스루 포함.
SET_VOLUME_VIEW = """
CREATE VIEW IF NOT EXISTS set_volume AS
SELECT
    ws.id           AS set_id,
    s.id            AS session_id,
    s.date          AS date,
    ws.exercise_id  AS exercise_id,
    ws.is_warmup    AS is_warmup,
    ws.weight_kg    AS weight_kg,
    ws.reps         AS reps,
    ws.intent_muscle_group_id AS intent_muscle_group_id,
    ( ws.weight_kg
      + e.bodyweight_factor * COALESCE(
          (SELECT bw.weight_kg FROM body_weight_log bw
           WHERE bw.date <= s.date ORDER BY bw.date DESC LIMIT 1), 0)
    ) * e.load_multiplier * ws.reps AS volume_kg
FROM workout_set ws
JOIN workout_session s ON s.id = ws.session_id
JOIN exercise e        ON e.id = ws.exercise_id;
"""

# §6.1 추정 1RM(Epley) — set_volume 별칭 `sv` 기준 SQL 식. 웜업 제외·weight>0·1≤reps≤12
# 밖이면 NULL. 세트 저장 응답의 PR 플래그(routers/sessions)와 stats 집계가 같은 식을 쓴다.
E1RM_EXPR = (
    "CASE WHEN sv.is_warmup = 0 AND sv.weight_kg > 0"
    " AND sv.reps BETWEEN 1 AND 12"
    " THEN sv.weight_kg * (1 + sv.reps / 30.0) END"
)

DDL = """
CREATE TABLE IF NOT EXISTS muscle_group (
    id         INTEGER PRIMARY KEY,
    code       TEXT    NOT NULL UNIQUE,
    name_ko    TEXT    NOT NULL,
    region     TEXT    NOT NULL CHECK (region IN
               ('chest','back','shoulders','arms','legs','core')),
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exercise (
    id                INTEGER PRIMARY KEY,
    name_ko           TEXT NOT NULL UNIQUE,
    name_en           TEXT,
    bodyweight_factor REAL NOT NULL DEFAULT 0
                      CHECK (bodyweight_factor >= 0 AND bodyweight_factor <= 1),
    load_multiplier   REAL NOT NULL DEFAULT 1 CHECK (load_multiplier > 0),
    is_builtin        INTEGER NOT NULL DEFAULT 0 CHECK (is_builtin IN (0,1)),
    is_archived       INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0,1)),
    note              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    -- §3.6 종목 속성 체계 (v2) — 전부 NULL 허용 자유 텍스트, enum·CHECK 없음
    base_movement     TEXT,
    equipment         TEXT,
    support           TEXT,
    grip              TEXT,
    angle             TEXT,
    aliases           TEXT
);

CREATE TABLE IF NOT EXISTS exercise_muscle (
    exercise_id     INTEGER NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
    muscle_group_id INTEGER NOT NULL REFERENCES muscle_group(id),
    role            TEXT    NOT NULL CHECK (role IN ('primary','secondary')),
    PRIMARY KEY (exercise_id, muscle_group_id)
);
CREATE INDEX IF NOT EXISTS idx_exercise_muscle_mg ON exercise_muscle(muscle_group_id);

CREATE TABLE IF NOT EXISTS workout_session (
    id         INTEGER PRIMARY KEY,
    date       TEXT NOT NULL,
    note       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_date ON workout_session(date);

CREATE TABLE IF NOT EXISTS workout_set (
    id          INTEGER PRIMARY KEY,
    client_id   TEXT UNIQUE,
    session_id  INTEGER NOT NULL REFERENCES workout_session(id) ON DELETE CASCADE,
    exercise_id INTEGER NOT NULL REFERENCES exercise(id),
    set_index   INTEGER NOT NULL,
    weight_kg   REAL    NOT NULL DEFAULT 0 CHECK (weight_kg >= 0),
    reps        INTEGER NOT NULL CHECK (reps > 0),
    is_warmup   INTEGER NOT NULL DEFAULT 0 CHECK (is_warmup IN (0,1)),
    rpe         REAL    CHECK (rpe IS NULL OR (rpe >= 1 AND rpe <= 10)),
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    -- §3.7 기록 의도 주동근 (v3) — NULL = 종목 기본 매핑 사용
    intent_muscle_group_id INTEGER REFERENCES muscle_group(id)
);
CREATE INDEX IF NOT EXISTS idx_set_session  ON workout_set(session_id);
CREATE INDEX IF NOT EXISTS idx_set_exercise ON workout_set(exercise_id);

CREATE TABLE IF NOT EXISTS body_weight_log (
    id        INTEGER PRIMARY KEY,
    date      TEXT NOT NULL UNIQUE,
    weight_kg REAL NOT NULL CHECK (weight_kg > 0)
);
""" + SET_VOLUME_VIEW


SCHEMA_VERSION = 3

# v1 → v2: §3.6 종목 속성 6컬럼 (순수 additive ALTER)
EXERCISE_ATTR_COLUMNS = (
    "base_movement", "equipment", "support", "grip", "angle", "aliases",
)


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(conn: sqlite3.Connection) -> None:
    """PRAGMA user_version 기반 마이그레이션.

    - 신규 DB: DDL이 처음부터 최신 스키마이므로 각 블록은 사실상 no-op
      (컬럼 존재 확인으로 건너뛰고, VIEW 재생성은 동일 정의라 무해).
    - 기존 DB: 버전별 블록이 순서대로 적용된다. 각 블록은 컬럼 존재 확인
      기반 멱등 — 중간에 죽어 반쯤 적용된 상태에서 재기동해도 안전하다.
    - 버전 기록은 각 블록 안에서만 (v2 블록은 2, v3 블록은 3) — 미래 버전
      (v4+) DB를 구버전 코드로 열어도 버전을 하향 기록하지 않는다
      (롤백·백업 복원 시나리오 안전).
    - DML(백필 UPDATE)과 버전 기록은 init_db의 commit 전에 죽으면 함께
      롤백되고, 다음 기동에 다시 시도된다.

    v1→v2 (§3.6): exercise 속성 6컬럼 ALTER + 시드 속성 백필 1회
      (사용자 수정 보존 — 매 기동 실행 금지).
    v2→v3 (§3.7): workout_set.intent_muscle_group_id ALTER +
      set_volume VIEW DROP 후 intent 패스스루 포함 재생성.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 2:
        existing = _columns(conn, "exercise")
        for col in EXERCISE_ATTR_COLUMNS:
            if col not in existing:
                conn.execute(f"ALTER TABLE exercise ADD COLUMN {col} TEXT")
        backfill_attributes(conn)
        conn.execute("PRAGMA user_version = 2")
    if version < 3:
        if "intent_muscle_group_id" not in _columns(conn, "workout_set"):
            conn.execute(
                "ALTER TABLE workout_set ADD COLUMN"
                " intent_muscle_group_id INTEGER REFERENCES muscle_group(id)"
            )
        # 구버전 VIEW에는 intent 패스스루가 없다 — DROP 후 단일 정의로 재생성
        conn.execute("DROP VIEW IF EXISTS set_volume")
        conn.execute(SET_VOLUME_VIEW)
        conn.execute("PRAGMA user_version = 3")


def init_db(db_path: str | None = None) -> None:
    conn = _connect(db_path or get_settings().DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(DDL)
        _migrate(conn)
        seed(conn)
        conn.commit()
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    conn = _connect(get_settings().DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
