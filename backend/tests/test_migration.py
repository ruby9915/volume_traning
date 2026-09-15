"""user_version 기반 마이그레이션(v1→v2→v3→v4) 테스트.

구버전 스키마 DB를 코드로 만들어 init_db로 마이그레이션한 뒤 컬럼·데이터 무손상·멱등성·
v4 데이터 단계(관리자 생성, 소유자 귀속, 기본 타겟, 세트 타겟, 커스텀 병합/승격, 즐겨찾기)를 단언한다.
"""

import sqlite3

import pytest

from app.db import SCHEMA_VERSION, init_db
from app.seed_data.exercises import EXERCISES

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
SELECT ws.id AS set_id, s.id AS session_id, s.date AS date, ws.exercise_id AS exercise_id,
       ws.is_warmup AS is_warmup, ws.weight_kg AS weight_kg, ws.reps AS reps,
       ( ws.weight_kg + e.bodyweight_factor * COALESCE(
           (SELECT bw.weight_kg FROM body_weight_log bw WHERE bw.date <= s.date ORDER BY bw.date DESC LIMIT 1), 0)
       ) * e.load_multiplier * ws.reps AS volume_kg
FROM workout_set ws JOIN workout_session s ON s.id = ws.session_id JOIN exercise e ON e.id = ws.exercise_id;
"""

V1_MUSCLES = [
    ("chest", "가슴", "chest", 1), ("back", "등", "back", 2), ("lower_back", "허리(기립근)", "back", 3),
    ("shoulders", "어깨", "shoulders", 4), ("biceps", "이두", "arms", 5), ("triceps", "삼두", "arms", 6),
    ("forearms", "전완", "arms", 7), ("quads", "대퇴사두", "legs", 8), ("hamstrings", "햄스트링", "legs", 9),
    ("glutes", "둔근", "legs", 10), ("calves", "종아리", "legs", 11), ("abs", "복근", "core", 12),
]
# v1 시드 45종 (name_ko, name_en, bw, mult) — 라이브러리의 같은 이름 행에서 가져온다
from test_seed_consistency import LEGACY_45  # noqa: E402

_BY_NAME = {e[0]: e for e in EXERCISES}
V1_SEED = [(n, _BY_NAME[n][1], _BY_NAME[n][5], _BY_NAME[n][6]) for n in LEGACY_45]


def _connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _mg(conn, code):
    return conn.execute("SELECT id FROM muscle_group WHERE code = ?", (code,)).fetchone()[0]


def _make_v1_db(path) -> None:
    """실사용 v1 DB 재현: v1 DDL + v1 시드 + 사용자 데이터."""
    conn = _connect(path)
    try:
        conn.executescript(V1_DDL)
        conn.execute("PRAGMA user_version = 1")
        conn.executemany(
            "INSERT INTO muscle_group (code, name_ko, region, sort_order) VALUES (?, ?, ?, ?)", V1_MUSCLES
        )
        for name_ko, name_en, bw, mult in V1_SEED:
            conn.execute(
                "INSERT INTO exercise (name_ko, name_en, bodyweight_factor, load_multiplier, is_builtin)"
                " VALUES (?, ?, ?, ?, 1)",
                (name_ko, name_en, bw, mult),
            )
        bench_id = conn.execute("SELECT id FROM exercise WHERE name_ko = '벤치프레스'").fetchone()["id"]
        conn.execute("INSERT INTO exercise_muscle VALUES (?, ?, 'primary')", (bench_id, _mg(conn, "chest")))
        conn.execute("INSERT INTO exercise_muscle VALUES (?, ?, 'secondary')", (bench_id, _mg(conn, "triceps")))
        # 사용자 데이터: 내장 종목 수정 + 커스텀 종목(주동근 back) + 세트 + 체중
        conn.execute(
            "UPDATE exercise SET note = '내 벤치 메모', bodyweight_factor = 0.1 WHERE name_ko = '벤치프레스'"
        )
        custom_id = conn.execute(
            "INSERT INTO exercise (name_ko, is_builtin) VALUES ('커스텀 로우', 0)"
        ).lastrowid
        conn.execute("INSERT INTO exercise_muscle VALUES (?, ?, 'primary')", (custom_id, _mg(conn, "back")))
        conn.execute("INSERT INTO exercise_muscle VALUES (?, ?, 'secondary')", (custom_id, _mg(conn, "biceps")))
        session_id = conn.execute(
            "INSERT INTO workout_session (date, note) VALUES ('2026-07-01', '세션 메모')"
        ).lastrowid
        conn.execute(
            "INSERT INTO workout_set (session_id, exercise_id, set_index, weight_kg, reps)"
            " VALUES (?, ?, 1, 102.5, 8)",
            (session_id, bench_id),
        )
        conn.execute("INSERT INTO body_weight_log (date, weight_kg) VALUES ('2026-07-01', 80.5)")
        conn.commit()
    finally:
        conn.close()


def _make_v3_db(path) -> None:
    """실사용 v3 DB 재현: v1 + §3.6 속성 6컬럼 + §3.7 intent 컬럼 + 커스텀·intent 데이터."""
    _make_v1_db(path)
    conn = _connect(path)
    try:
        for col in ("base_movement", "equipment", "support", "grip", "angle", "aliases"):
            conn.execute(f"ALTER TABLE exercise ADD COLUMN {col} TEXT")
        conn.execute(
            "ALTER TABLE workout_set ADD COLUMN intent_muscle_group_id INTEGER REFERENCES muscle_group(id)"
        )
        conn.execute(
            "UPDATE exercise SET base_movement = '벤치프레스', equipment = '바벨' WHERE name_ko = '벤치프레스'"
        )
        # 커스텀 '푸쉬업' (내장 '푸시업'과 정규화 이름 동일 → 병합 대상), 속성은 tags로 흡수돼야 함
        pushup_id = conn.execute(
            "INSERT INTO exercise (name_ko, is_builtin, equipment, support, grip) VALUES ('푸쉬업', 0, '맨몸', '플랫', NULL)"
        ).lastrowid
        conn.execute("INSERT INTO exercise_muscle VALUES (?, ?, 'primary')", (pushup_id, _mg(conn, "chest")))
        # 커스텀 '인클라인 프레스 머신' — 라이브러리와 이름이 같으면 승격, 아니면 유지
        machine_id = conn.execute(
            "INSERT INTO exercise (name_ko, is_builtin, equipment) VALUES ('인클라인 프레스 머신', 0, '머신')"
        ).lastrowid
        conn.execute("INSERT INTO exercise_muscle VALUES (?, ?, 'primary')", (machine_id, _mg(conn, "chest")))
        sid = conn.execute("SELECT id FROM workout_session").fetchone()["id"]
        conn.execute(
            "INSERT INTO workout_set (session_id, exercise_id, set_index, weight_kg, reps, intent_muscle_group_id)"
            " VALUES (?, ?, 2, 0, 15, ?)",
            (sid, pushup_id, _mg(conn, "hamstrings")),  # intent 지정 세트 (일부러 엉뚱한 근육)
        )
        conn.execute(
            "INSERT INTO workout_set (session_id, exercise_id, set_index, weight_kg, reps) VALUES (?, ?, 3, 50, 10)",
            (sid, machine_id),
        )
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
    finally:
        conn.close()


def _columns(conn, table) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "migrate-pw")
    monkeypatch.setenv("ADMIN_USERNAME", "owner")
    monkeypatch.setenv("JWT_SECRET", "s" * 64)
    monkeypatch.setenv("BACKUP_DIR", "")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_migrate_v3_to_v4_full(tmp_path, env):
    path = str(tmp_path / "v3.db")
    _make_v3_db(path)

    log = init_db(path)

    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        # 구조
        ex_cols = _columns(conn, "exercise")
        assert {"tags", "default_target_id", "user_id", "machine_id"} <= ex_cols
        assert not {"equipment", "support", "grip", "angle"} & ex_cols
        assert "target_id" in _columns(conn, "workout_set") and "intent_muscle_group_id" not in _columns(conn, "workout_set")
        assert "user_id" in _columns(conn, "workout_session") and "user_id" in _columns(conn, "body_weight_log")
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'exercise_muscle'").fetchone()[0] == 0
        assert {"level", "parent_id"} <= _columns(conn, "muscle_group")
        # 관리자 계정 + 소유자 귀속
        admin = conn.execute("SELECT * FROM user").fetchone()
        assert (admin["username"], admin["is_admin"]) == ("owner", 1)
        assert "admin user created: owner" in log
        assert conn.execute("SELECT COUNT(*) FROM workout_session WHERE user_id != ?", (admin["id"],)).fetchone()[0] == 0
        assert conn.execute("SELECT user_id, weight_kg FROM body_weight_log").fetchone()[:] == (admin["id"], 80.5)
        # 내장 종목: 시드 값으로 기본 타겟·계열·태그, 사용자 수정(note·bw)은 보존
        bench = conn.execute(
            "SELECT e.*, t.code AS target FROM exercise e JOIN muscle_group t ON t.id = e.default_target_id"
            " WHERE e.name_ko = '벤치프레스'"
        ).fetchone()
        assert (bench["target"], bench["base_movement"], bench["tags"]) == ("mid_chest", "벤치프레스", "바벨,플랫")
        assert (bench["note"], bench["bodyweight_factor"]) == ("내 벤치 메모", 0.1)
        # 커스텀 '커스텀 로우': 옛 주동근 back → 기본 타겟, 소유자 = 관리자, 그대로 유지
        custom = conn.execute(
            "SELECT e.*, t.code AS target FROM exercise e JOIN muscle_group t ON t.id = e.default_target_id"
            " WHERE e.name_ko = '커스텀 로우'"
        ).fetchone()
        assert (custom["target"], custom["user_id"], custom["is_builtin"]) == ("back", admin["id"], 0)
        assert "custom kept: 커스텀 로우" in log
        # 커스텀 '푸쉬업' → 내장 '푸시업'으로 병합 (세트 이동, 행 삭제), intent는 target으로 보존
        assert conn.execute("SELECT COUNT(*) FROM exercise WHERE name_ko = '푸쉬업'").fetchone()[0] == 0
        pushup_set = conn.execute(
            "SELECT e.name_ko, t.code AS target FROM workout_set ws JOIN exercise e ON e.id = ws.exercise_id"
            " JOIN muscle_group t ON t.id = ws.target_id WHERE ws.set_index = 2"
        ).fetchone()
        assert (pushup_set["name_ko"], pushup_set["target"]) == ("푸시업", "hamstrings")
        assert any(line.startswith("custom merged: 푸쉬업 -> 푸시업") for line in log)
        # intent 없던 세트 = 종목 기본 타겟
        bench_set = conn.execute(
            "SELECT t.code FROM workout_set ws JOIN muscle_group t ON t.id = ws.target_id WHERE ws.set_index = 1"
        ).fetchone()[0]
        assert bench_set == "mid_chest"
        assert conn.execute("SELECT COUNT(*) FROM workout_set WHERE target_id IS NULL").fetchone()[0] == 0
        # VIEW: volume 불변 (bw 0.1 × 80.5 반영) + target_path
        sv = conn.execute("SELECT * FROM set_volume WHERE set_index_hint IS NULL" if False else
                          "SELECT volume_kg, user_id, target_id FROM set_volume WHERE set_id = 1").fetchone()
        assert sv["volume_kg"] == (102.5 + 0.1 * 80.5) * 1 * 8 and sv["user_id"] == admin["id"]
        tp = conn.execute("SELECT muscle_code, region FROM target_path WHERE code = 'mid_chest'").fetchone()
        assert (tp["muscle_code"], tp["region"]) == ("chest", "chest")
        # 즐겨찾기 초기값 = 세트 수 상위 종목
        favs = conn.execute("SELECT COUNT(*) FROM favorite WHERE user_id = ?", (admin["id"],)).fetchone()[0]
        assert favs >= 1
        # 커스텀 '인클라인 프레스 머신': 라이브러리에 같은 이름이 있으면 승격(내장·id 보존), 없으면 유지
        row = conn.execute("SELECT id, is_builtin, user_id FROM exercise WHERE name_ko = '인클라인 프레스 머신'").fetchone()
        assert row is not None
        in_library = any(e[0] == "인클라인 프레스 머신" for e in EXERCISES)
        assert (row["is_builtin"], row["user_id"]) == ((1, None) if in_library else (0, admin["id"]))
        assert conn.execute("SELECT COUNT(*) FROM workout_set WHERE exercise_id = ?", (row["id"],)).fetchone()[0] == 1
    finally:
        conn.close()


def test_migrate_v3_fills_builtin_secondary_targets(tmp_path, env):
    """v3 → v5: 승격·병합된 내장 종목까지 보조 근육 초안이 채워진다 (§11.2)."""
    path = str(tmp_path / "v3.db")
    _make_v3_db(path)
    log = init_db(path)
    assert any(line.startswith("secondary targets seeded") for line in log), log
    conn = _connect(path)
    try:
        codes = {
            r[0]
            for r in conn.execute(
                """
                SELECT mg.code FROM exercise_secondary_target est
                JOIN exercise e ON e.id = est.exercise_id
                JOIN muscle_group mg ON mg.id = est.target_id
                WHERE e.name_ko = '벤치프레스'
                """
            ).fetchall()
        }
        assert codes == {"triceps", "front_delt"}
        # 승격된 커스텀('푸쉬업' → 내장 '푸시업')도 라이브러리 초안을 받는다
        n = conn.execute(
            "SELECT COUNT(*) FROM exercise_secondary_target est JOIN exercise e ON e.id = est.exercise_id"
            " WHERE e.name_ko = '푸시업'"
        ).fetchone()[0]
        assert n >= 1
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'set_indirect'").fetchone()
    finally:
        conn.close()


def test_migrate_v4_to_v5_fills_once_and_respects_edits(tmp_path, env):
    """v4 DB(보조 근육 테이블 없음)를 열면 한 번 채우고, 이후 관리자가 비운 값은 재기동이 되살리지 않는다."""
    path = str(tmp_path / "v4.db")
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute("DROP TABLE exercise_secondary_target")
        conn.execute("DROP VIEW IF EXISTS set_indirect")
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    finally:
        conn.close()

    log = init_db(path)
    assert any(line.startswith("secondary targets seeded") for line in log), log
    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        bench = conn.execute("SELECT id FROM exercise WHERE name_ko = '벤치프레스'").fetchone()[0]
        assert conn.execute(
            "SELECT COUNT(*) FROM exercise_secondary_target WHERE exercise_id = ?", (bench,)
        ).fetchone()[0] == 2
        # 관리자가 앱에서 비운 상태를 흉내
        conn.execute("DELETE FROM exercise_secondary_target WHERE exercise_id = ?", (bench,))
        conn.commit()
    finally:
        conn.close()

    log = init_db(path)  # 재기동
    assert not any(line.startswith("secondary targets seeded") for line in log), log
    conn = _connect(path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM exercise_secondary_target WHERE exercise_id = ?", (bench,)
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_migrate_v5_to_v6_backfills_user_machines(tmp_path, env):
    """v5 DB(user_machine 없음): 커스텀 종목에 연결된 머신이 소유자의 내 머신으로 한 번 등록된다."""
    path = str(tmp_path / "v5.db")
    init_db(path)
    conn = _connect(path)
    try:
        admin = conn.execute("SELECT id FROM user ORDER BY id LIMIT 1").fetchone()[0]
        machine = conn.execute("SELECT id FROM machine ORDER BY id LIMIT 1").fetchone()[0]
        chest = conn.execute("SELECT id FROM muscle_group WHERE code = 'chest'").fetchone()[0]
        conn.execute(
            "INSERT INTO exercise (name_ko, default_target_id, machine_id, user_id, is_builtin)"
            " VALUES ('마이그 머신 종목', ?, ?, ?, 0)",
            (chest, machine, admin),
        )
        conn.execute("DROP TABLE user_machine")
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
    finally:
        conn.close()

    log = init_db(path)
    assert any(line.startswith("user machines backfilled: 1") for line in log), log
    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute(
            "SELECT 1 FROM user_machine WHERE user_id = ? AND machine_id = ?", (admin, machine)
        ).fetchone()
        # 사용자가 지운 뒤 재기동해도 되살아나지 않는다 (데이터 단계는 한 번)
        conn.execute("DELETE FROM user_machine")
        conn.commit()
    finally:
        conn.close()
    log = init_db(path)
    assert not any(line.startswith("user machines backfilled") for line in log), log
    conn = _connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM user_machine").fetchone()[0] == 0
    finally:
        conn.close()


def test_migrate_v6_to_v7_adds_profile_columns_and_friendship(tmp_path, env):
    """v6 DB(프로필 컬럼·friendship 없음)를 열면 컬럼이 생기고(기본 공개=1) 테이블이 만들어진다."""
    path = str(tmp_path / "v6.db")
    init_db(path)
    conn = _connect(path)
    try:
        # CHECK 제약이 걸린 컬럼은 DROP COLUMN이 안 되므로 v6 모양의 user 테이블로 재구축
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            CREATE TABLE user_v6 (
                id            INTEGER PRIMARY KEY,
                username      TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                display_name  TEXT    NOT NULL,
                is_admin      INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "INSERT INTO user_v6 SELECT id, username, password_hash, display_name, is_admin, created_at FROM user"
        )
        conn.execute("DROP TABLE user")
        conn.execute("ALTER TABLE user_v6 RENAME TO user")
        conn.execute("DROP TABLE friendship")
        conn.execute("PRAGMA user_version = 6")
        conn.commit()
    finally:
        conn.close()

    init_db(path)
    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        cols = {r[1] for r in conn.execute("PRAGMA table_info(user)").fetchall()}
        assert {"bio", "avatar", "share_with_friends"} <= cols
        assert conn.execute("SELECT share_with_friends FROM user LIMIT 1").fetchone()[0] == 1
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'friendship'").fetchone()
    finally:
        conn.close()


def test_migrate_v7_to_v8_adds_technique_column(tmp_path, env):
    """v7 DB(workout_set.technique 없음)를 열면 컬럼이 생기고 기존 세트는 NULL(일반 세트)."""
    path = str(tmp_path / "v7.db")
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute("ALTER TABLE workout_set DROP COLUMN technique")
        conn.execute("PRAGMA user_version = 7")
        conn.commit()
    finally:
        conn.close()
    init_db(path)
    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert "technique" in {r[1] for r in conn.execute("PRAGMA table_info(workout_set)").fetchall()}
    finally:
        conn.close()


def test_migration_idempotent_on_restart(tmp_path, env):
    path = str(tmp_path / "v3.db")
    _make_v3_db(path)
    init_db(path)
    sets_before = _connect(path).execute("SELECT COUNT(*) FROM workout_set").fetchone()[0]
    assert init_db(path) == []  # 두 번째 기동은 데이터 단계 없음
    init_db(path)
    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("SELECT COUNT(*) FROM user").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM workout_set").fetchone()[0] == sets_before
        cols = [r[1] for r in conn.execute("PRAGMA table_info(exercise)").fetchall()]
        assert len(cols) == len(set(cols))
    finally:
        conn.close()


def test_migrate_v1_to_v4_direct(tmp_path, env):
    path = str(tmp_path / "v1.db")
    _make_v1_db(path)
    init_db(path)
    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert not {"equipment", "support", "grip", "angle"} & _columns(conn, "exercise")
        assert conn.execute("SELECT COUNT(*) FROM workout_set WHERE target_id IS NULL").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM exercise WHERE default_target_id IS NULL").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM workout_set").fetchone()[0] == 1
    finally:
        conn.close()


def test_v4_half_applied_restart_recovers(tmp_path, env):
    """컬럼 ALTER 일부만 적용되고 버전 기록 전에 죽은 상태 재기동 안전."""
    path = str(tmp_path / "half.db")
    _make_v3_db(path)
    conn = _connect(path)
    conn.execute("ALTER TABLE workout_set RENAME COLUMN intent_muscle_group_id TO target_id")
    conn.execute("ALTER TABLE exercise ADD COLUMN tags TEXT")
    conn.commit()
    conn.close()

    init_db(path)
    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        cols = [r[1] for r in conn.execute("PRAGMA table_info(workout_set)").fetchall()]
        assert cols.count("target_id") == 1
        assert conn.execute("SELECT COUNT(*) FROM user").fetchone()[0] == 1
    finally:
        conn.close()


def test_future_version_not_downgraded(tmp_path, env):
    path = str(tmp_path / "future.db")
    init_db(path)
    future = SCHEMA_VERSION + 1
    conn = _connect(path)
    conn.execute(f"PRAGMA user_version = {future}")
    conn.commit()
    conn.close()
    init_db(path)
    assert _connect(path).execute("PRAGMA user_version").fetchone()[0] == future


def test_fresh_db_created_at_current_version(tmp_path, env):
    path = str(tmp_path / "fresh.db")
    log = init_db(path)
    conn = _connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("SELECT COUNT(*) FROM exercise").fetchone()[0] == len(EXERCISES)
        assert conn.execute("SELECT COUNT(*) FROM exercise WHERE default_target_id IS NULL").fetchone()[0] == 0
        assert conn.execute("SELECT username, is_admin FROM user").fetchone()[:] == ("owner", 1)
        assert log == ["admin user created: owner"]
        conn.execute("SELECT target_id, user_id FROM set_volume LIMIT 1")
        conn.execute("SELECT muscle_code FROM target_path LIMIT 1")
    finally:
        conn.close()
