"""user_version 기반 마이그레이션(§3.6 v1→v2, §3.7 v2→v3) 테스트.

구버전 스키마 DB를 코드로 만들어 init_db로 마이그레이션한 뒤
컬럼 존재·기존 데이터 무손상·멱등성·백필 가드·VIEW 재생성을 단언한다.
"""

import sqlite3

from app.db import EXERCISE_ATTR_COLUMNS, SCHEMA_VERSION, init_db
from app.seed_exercises import EXERCISES, MUSCLE_GROUPS

# 마이그레이션 도입 전(v1)의 실제 DDL — exercise에 속성 6컬럼이 없다
V1_DDL = """
CREATE TABLE muscle_group (
    id         INTEGER PRIMARY KEY,
    code       TEXT    NOT NULL UNIQUE,
    name_ko    TEXT    NOT NULL,
    region     TEXT    NOT NULL CHECK (region IN
               ('chest','back','shoulders','arms','legs','core')),
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE exercise (
    id                INTEGER PRIMARY KEY,
    name_ko           TEXT NOT NULL UNIQUE,
    name_en           TEXT,
    bodyweight_factor REAL NOT NULL DEFAULT 0
                      CHECK (bodyweight_factor >= 0 AND bodyweight_factor <= 1),
    load_multiplier   REAL NOT NULL DEFAULT 1 CHECK (load_multiplier > 0),
    is_builtin        INTEGER NOT NULL DEFAULT 0 CHECK (is_builtin IN (0,1)),
    is_archived       INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0,1)),
    note              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE exercise_muscle (
    exercise_id     INTEGER NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
    muscle_group_id INTEGER NOT NULL REFERENCES muscle_group(id),
    role            TEXT    NOT NULL CHECK (role IN ('primary','secondary')),
    PRIMARY KEY (exercise_id, muscle_group_id)
);
CREATE INDEX idx_exercise_muscle_mg ON exercise_muscle(muscle_group_id);

CREATE TABLE workout_session (
    id         INTEGER PRIMARY KEY,
    date       TEXT NOT NULL,
    note       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_session_date ON workout_session(date);

CREATE TABLE workout_set (
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
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_set_session  ON workout_set(session_id);
CREATE INDEX idx_set_exercise ON workout_set(exercise_id);

CREATE TABLE body_weight_log (
    id        INTEGER PRIMARY KEY,
    date      TEXT NOT NULL UNIQUE,
    weight_kg REAL NOT NULL CHECK (weight_kg > 0)
);

CREATE VIEW set_volume AS
SELECT
    ws.id           AS set_id,
    s.id            AS session_id,
    s.date          AS date,
    ws.exercise_id  AS exercise_id,
    ws.is_warmup    AS is_warmup,
    ws.weight_kg    AS weight_kg,
    ws.reps         AS reps,
    ( ws.weight_kg
      + e.bodyweight_factor * COALESCE(
          (SELECT bw.weight_kg FROM body_weight_log bw
           WHERE bw.date <= s.date ORDER BY bw.date DESC LIMIT 1), 0)
    ) * e.load_multiplier * ws.reps AS volume_kg
FROM workout_set ws
JOIN workout_session s ON s.id = ws.session_id
JOIN exercise e        ON e.id = ws.exercise_id;
"""


def _connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _make_v1_db(path) -> None:
    """실사용 v1 DB 재현: v1 DDL + v1 시드 + 사용자 데이터."""
    conn = _connect(path)
    try:
        conn.executescript(V1_DDL)
        conn.execute("PRAGMA user_version = 1")
        for code, name_ko, region, sort_order in MUSCLE_GROUPS:
            conn.execute(
                "INSERT INTO muscle_group (code, name_ko, region, sort_order)"
                " VALUES (?, ?, ?, ?)",
                (code, name_ko, region, sort_order),
            )
        for name_ko, name_en, _primary, _secondary, bw, mult in EXERCISES:
            conn.execute(
                "INSERT INTO exercise"
                " (name_ko, name_en, bodyweight_factor, load_multiplier, is_builtin)"
                " VALUES (?, ?, ?, ?, 1)",
                (name_ko, name_en, bw, mult),
            )
        # 사용자 데이터: 내장 종목 수정 + 커스텀 종목 + 세트 + 체중
        conn.execute(
            "UPDATE exercise SET note = '내 벤치 메모', bodyweight_factor = 0.1"
            " WHERE name_ko = '벤치프레스'"
        )
        conn.execute(
            "INSERT INTO exercise (name_ko, is_builtin) VALUES ('커스텀 로우', 0)"
        )
        session_id = conn.execute(
            "INSERT INTO workout_session (date, note) VALUES ('2026-07-01', '세션 메모')"
        ).lastrowid
        bench_id = conn.execute(
            "SELECT id FROM exercise WHERE name_ko = '벤치프레스'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO workout_set (session_id, exercise_id, set_index, weight_kg, reps)"
            " VALUES (?, ?, 1, 102.5, 8)",
            (session_id, bench_id),
        )
        conn.execute(
            "INSERT INTO body_weight_log (date, weight_kg) VALUES ('2026-07-01', 80.5)"
        )
        conn.commit()
    finally:
        conn.close()


def _make_v2_db(path) -> None:
    """실사용 v2 DB 재현: v1 DB + §3.6 속성 6컬럼 ALTER + user_version=2.

    (v2 시점의 workout_set에는 intent_muscle_group_id가 없고,
    set_volume VIEW에도 intent 패스스루가 없다 — V1_DDL의 VIEW 그대로.)
    """
    _make_v1_db(path)
    conn = _connect(path)
    try:
        for col in ("base_movement", "equipment", "support", "grip", "angle", "aliases"):
            conn.execute(f"ALTER TABLE exercise ADD COLUMN {col} TEXT")
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    finally:
        conn.close()


def _columns(conn, table) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_migrate_v1_to_v2_adds_columns_and_preserves_data(tmp_path):
    path = str(tmp_path / "v1.db")
    _make_v1_db(path)

    init_db(path)

    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert set(EXERCISE_ATTR_COLUMNS) <= _columns(conn, "exercise")

        # 기존 데이터 무손상
        bench = conn.execute(
            "SELECT * FROM exercise WHERE name_ko = '벤치프레스'"
        ).fetchone()
        assert bench["note"] == "내 벤치 메모"
        assert bench["bodyweight_factor"] == 0.1
        custom = conn.execute(
            "SELECT * FROM exercise WHERE name_ko = '커스텀 로우'"
        ).fetchone()
        assert custom is not None and custom["is_builtin"] == 0
        ws = conn.execute("SELECT * FROM workout_set").fetchall()
        assert len(ws) == 1
        assert (ws[0]["weight_kg"], ws[0]["reps"]) == (102.5, 8)
        assert conn.execute(
            "SELECT weight_kg FROM body_weight_log WHERE date = '2026-07-01'"
        ).fetchone()[0] == 80.5
        assert conn.execute("SELECT COUNT(*) FROM exercise").fetchone()[0] == 46

        # 백필: 내장 + 속성 미보유 행에 명백한 값만
        assert bench["base_movement"] == "벤치프레스"
        assert bench["equipment"] == "바벨"
        assert bench["grip"] is None
        dips = conn.execute("SELECT * FROM exercise WHERE name_ko = '딥스'").fetchone()
        assert all(dips[c] is None for c in EXERCISE_ATTR_COLUMNS)
        # 커스텀 종목은 백필 대상 아님
        assert all(custom[c] is None for c in EXERCISE_ATTR_COLUMNS)
    finally:
        conn.close()


def test_migration_idempotent_on_restart(tmp_path):
    path = str(tmp_path / "v1.db")
    _make_v1_db(path)

    init_db(path)
    init_db(path)  # 재기동 반복 — ALTER 중복·시드 중복 없이 안전해야 한다
    init_db(path)

    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("SELECT COUNT(*) FROM exercise").fetchone()[0] == 46
        assert conn.execute("SELECT COUNT(*) FROM workout_set").fetchone()[0] == 1
        # 속성 컬럼이 중복 추가되지 않았다
        cols = [r[1] for r in conn.execute("PRAGMA table_info(exercise)").fetchall()]
        assert len(cols) == len(set(cols))
    finally:
        conn.close()


def test_backfill_preserves_user_attribute_edits(tmp_path):
    path = str(tmp_path / "v1.db")
    _make_v1_db(path)
    init_db(path)

    # 사용자가 내장 종목의 속성을 수정 (base_movement는 여전히 NULL인 행)
    conn = _connect(path)
    conn.execute(
        "UPDATE exercise SET equipment = '스미스머신' WHERE name_ko = '슈러그'"
    )
    conn.commit()
    conn.close()

    init_db(path)  # 재기동 — 시드 백필이 사용자 수정을 덮어쓰면 안 된다

    conn = _connect(path)
    try:
        shrug = conn.execute(
            "SELECT * FROM exercise WHERE name_ko = '슈러그'"
        ).fetchone()
        assert shrug["equipment"] == "스미스머신"
        assert shrug["base_movement"] is None
    finally:
        conn.close()


def test_backfill_not_reapplied_after_user_clears_all_attributes(tmp_path):
    """사용자가 내장 종목 속성 6개를 전부 비워도(전-6-NULL) 재기동 시 유지.

    백필은 v1→v2 마이그레이션 1회만 실행되므로, 이미 v2인 DB에서
    전부 NULL이 된 행에 시드값이 되살아나면 안 된다.
    """
    path = str(tmp_path / "v1.db")
    _make_v1_db(path)
    init_db(path)  # v1→v2 마이그레이션 + 백필

    # 사용자가 '벤치프레스'의 속성을 전부 비움 (PATCH null = 값 비우기)
    conn = _connect(path)
    conn.execute(
        "UPDATE exercise SET base_movement = NULL, equipment = NULL, support = NULL,"
        " grip = NULL, angle = NULL, aliases = NULL WHERE name_ko = '벤치프레스'"
    )
    conn.commit()
    conn.close()

    init_db(path)  # 재기동 — 시드값이 재주입되면 안 된다

    conn = _connect(path)
    try:
        bench = conn.execute(
            "SELECT * FROM exercise WHERE name_ko = '벤치프레스'"
        ).fetchone()
        assert all(bench[c] is None for c in EXERCISE_ATTR_COLUMNS)
    finally:
        conn.close()


def test_future_version_not_downgraded(tmp_path):
    """미래 버전(v4+) DB를 현행 코드로 열어도 user_version을 하향 기록하지 않는다."""
    path = str(tmp_path / "future.db")
    init_db(path)  # 현행 버전으로 생성

    future = SCHEMA_VERSION + 1
    conn = _connect(path)
    conn.execute(f"PRAGMA user_version = {future}")
    conn.commit()
    conn.close()

    init_db(path)  # 현행 코드(SCHEMA_VERSION)로 재기동 — 하향 금지

    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == future
    finally:
        conn.close()


def test_fresh_db_created_at_current_version(tmp_path):
    path = str(tmp_path / "fresh.db")
    init_db(path)

    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert set(EXERCISE_ATTR_COLUMNS) <= _columns(conn, "exercise")
        assert "intent_muscle_group_id" in _columns(conn, "workout_set")
        # 신규 DB의 VIEW에도 intent 패스스루 존재
        conn.execute("SELECT intent_muscle_group_id FROM set_volume LIMIT 1")
        assert conn.execute("SELECT COUNT(*) FROM exercise").fetchone()[0] == 45
        bench = conn.execute(
            "SELECT * FROM exercise WHERE name_ko = '벤치프레스'"
        ).fetchone()
        assert bench["base_movement"] == "벤치프레스"
        assert bench["equipment"] == "바벨"
    finally:
        conn.close()


# ---------- v2 → v3 (§3.7 intent) ----------


def test_migrate_v2_to_v3_adds_intent_column_and_view_passthrough(tmp_path):
    path = str(tmp_path / "v2.db")
    _make_v2_db(path)

    init_db(path)

    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert "intent_muscle_group_id" in _columns(conn, "workout_set")

        # 기존 데이터 무손상 + 기존 세트의 intent는 NULL(기본 매핑)
        ws = conn.execute("SELECT * FROM workout_set").fetchall()
        assert len(ws) == 1
        assert (ws[0]["weight_kg"], ws[0]["reps"]) == (102.5, 8)
        assert ws[0]["intent_muscle_group_id"] is None
        assert conn.execute("SELECT COUNT(*) FROM exercise").fetchone()[0] == 46

        # VIEW 재생성: intent 패스스루 + volume_kg 값 불변 (bw 0.1 × 80.5 반영)
        sv = conn.execute("SELECT * FROM set_volume").fetchone()
        assert sv["intent_muscle_group_id"] is None
        assert sv["volume_kg"] == (102.5 + 0.1 * 80.5) * 1 * 8

        # intent 값을 넣으면 VIEW로 그대로 통과된다
        hamstrings = conn.execute(
            "SELECT id FROM muscle_group WHERE code = 'hamstrings'"
        ).fetchone()["id"]
        conn.execute(
            "UPDATE workout_set SET intent_muscle_group_id = ?", (hamstrings,)
        )
        assert conn.execute(
            "SELECT intent_muscle_group_id FROM set_volume"
        ).fetchone()[0] == hamstrings
    finally:
        conn.close()


def test_migrate_v1_to_v3_direct(tmp_path):
    """v1 DB도 한 번의 기동으로 v2 블록(속성)과 v3 블록(intent)이 순서 적용."""
    path = str(tmp_path / "v1-direct.db")
    _make_v1_db(path)

    init_db(path)

    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert set(EXERCISE_ATTR_COLUMNS) <= _columns(conn, "exercise")
        assert "intent_muscle_group_id" in _columns(conn, "workout_set")
        conn.execute("SELECT intent_muscle_group_id FROM set_volume LIMIT 1")
    finally:
        conn.close()


def test_v2_to_v3_idempotent_on_restart(tmp_path):
    path = str(tmp_path / "v2.db")
    _make_v2_db(path)

    init_db(path)
    init_db(path)  # 재기동 반복 — ALTER 중복·VIEW 재생성 오류 없이 안전해야 한다
    init_db(path)

    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        cols = [r[1] for r in conn.execute("PRAGMA table_info(workout_set)").fetchall()]
        assert cols.count("intent_muscle_group_id") == 1
        assert conn.execute("SELECT COUNT(*) FROM workout_set").fetchone()[0] == 1
        conn.execute("SELECT intent_muscle_group_id FROM set_volume LIMIT 1")
    finally:
        conn.close()


def test_v3_half_applied_restart_recovers(tmp_path):
    """컬럼 ALTER까지만 적용되고 버전 기록 전에 죽은 상태(반쯤 적용) 재기동 안전."""
    path = str(tmp_path / "half.db")
    _make_v2_db(path)
    conn = _connect(path)
    conn.execute(
        "ALTER TABLE workout_set ADD COLUMN"
        " intent_muscle_group_id INTEGER REFERENCES muscle_group(id)"
    )
    conn.commit()  # user_version은 여전히 2, VIEW도 구버전
    conn.close()

    init_db(path)

    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        cols = [r[1] for r in conn.execute("PRAGMA table_info(workout_set)").fetchall()]
        assert cols.count("intent_muscle_group_id") == 1
        conn.execute("SELECT intent_muscle_group_id FROM set_volume LIMIT 1")
    finally:
        conn.close()
