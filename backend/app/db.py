import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from .config import get_settings
from .seed import seed, tags_to_text
from .seed_data.exercises import EXERCISES

logger = logging.getLogger("app.db")

# §6.1 추정 1RM(Epley) — set_volume 별칭 `sv` 기준 SQL 식. 웜업 제외·weight>0·1≤reps≤12
# 밖이면 NULL. 세트 저장 응답의 PR 플래그(routers/sessions)와 stats 집계가 같은 식을 쓴다.
E1RM_EXPR = (
    "CASE WHEN sv.is_warmup = 0 AND sv.weight_kg > 0"
    " AND sv.reps BETWEEN 1 AND 12"
    " THEN sv.weight_kg * (1 + sv.reps / 30.0) END"
)

# set_volume VIEW 단일 정의 (§3.2·§10). v2: user_id 패스스루 + 체중 조회가 세션 소유자 기준,
# target_id 패스스루 (볼륨은 세트의 타겟에 100% 귀속 — 집계는 target_path와 JOIN).
SET_VOLUME_VIEW = """
CREATE VIEW IF NOT EXISTS set_volume AS
SELECT
    ws.id           AS set_id,
    s.id            AS session_id,
    s.user_id       AS user_id,
    s.date          AS date,
    ws.exercise_id  AS exercise_id,
    ws.is_warmup    AS is_warmup,
    ws.weight_kg    AS weight_kg,
    ws.reps         AS reps,
    ws.target_id    AS target_id,
    ( ws.weight_kg
      + e.bodyweight_factor * COALESCE(
          (SELECT bw.weight_kg FROM body_weight_log bw
           WHERE bw.user_id = s.user_id AND bw.date <= s.date
           ORDER BY bw.date DESC LIMIT 1), 0)
    ) * e.load_multiplier * ws.reps AS volume_kg
FROM workout_set ws
JOIN workout_session s ON s.id = ws.session_id
JOIN exercise e        ON e.id = ws.exercise_id;
"""

# 타겟 행 → (근육 level 2 코드, 부위) 경로. level 3 행은 parent가 근육, level 2 행은 자기 자신.
TARGET_PATH_VIEW = """
CREATE VIEW IF NOT EXISTS target_path AS
SELECT
    t.id                             AS id,
    t.code                           AS code,
    t.name_ko                        AS name_ko,
    t.level                          AS level,
    t.region                         AS region,
    COALESCE(p.code, t.code)         AS muscle_code,
    COALESCE(p.name_ko, t.name_ko)   AS muscle_name_ko,
    CASE WHEN t.level = 3 THEN t.code END AS detail_code
FROM muscle_group t
LEFT JOIN muscle_group p ON p.id = t.parent_id;
"""

DDL = """
CREATE TABLE IF NOT EXISTS user (
    id            INTEGER PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    display_name  TEXT    NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0,1)),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS muscle_group (
    id         INTEGER PRIMARY KEY,
    code       TEXT    NOT NULL UNIQUE,
    name_ko    TEXT    NOT NULL,
    region     TEXT    NOT NULL CHECK (region IN
               ('chest','back','shoulders','arms','legs','core')),
    sort_order INTEGER NOT NULL DEFAULT 0,
    -- §10.2 타겟 분류: level 2 = 근육, level 3 = 세부(parent_id = 근육)
    level      INTEGER NOT NULL DEFAULT 2 CHECK (level IN (2,3)),
    parent_id  INTEGER REFERENCES muscle_group(id)
);

CREATE TABLE IF NOT EXISTS machine (
    id         INTEGER PRIMARY KEY,
    brand      TEXT NOT NULL,
    model      TEXT NOT NULL,
    name_ko    TEXT NOT NULL,
    target_id  INTEGER REFERENCES muscle_group(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (brand, model)
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
    -- §10.3: 계열(base_movement)만 전용 필드, 나머지 속성은 tags(쉼표 구분) 자유 태그
    base_movement     TEXT,
    aliases           TEXT,
    tags              TEXT,
    -- §10.3: 기본 타겟 (세트 저장 시 target 미지정이면 이 값), 소유자(NULL = 내장 공용), 머신
    default_target_id INTEGER REFERENCES muscle_group(id),
    user_id           INTEGER REFERENCES user(id),
    machine_id        INTEGER REFERENCES machine(id)
);

CREATE TABLE IF NOT EXISTS favorite (
    user_id     INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    exercise_id INTEGER NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, exercise_id)
);

CREATE TABLE IF NOT EXISTS workout_session (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER REFERENCES user(id),
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
    -- §10.2 세트의 타겟 (앱이 항상 채운다 — NULL은 마이그레이션 중간 상태에서만)
    target_id   INTEGER REFERENCES muscle_group(id)
);
CREATE INDEX IF NOT EXISTS idx_set_session  ON workout_set(session_id);
CREATE INDEX IF NOT EXISTS idx_set_exercise ON workout_set(exercise_id);

CREATE TABLE IF NOT EXISTS body_weight_log (
    id        INTEGER PRIMARY KEY,
    user_id   INTEGER REFERENCES user(id),
    date      TEXT NOT NULL,
    weight_kg REAL NOT NULL CHECK (weight_kg > 0),
    UNIQUE (user_id, date)
);
"""

SCHEMA_VERSION = 4

# v1 → v2 (§3.6): 당시 추가된 속성 6컬럼. v4에서 4개는 tags로 흡수·삭제된다.
_V2_ATTR_COLUMNS = ("base_movement", "equipment", "support", "grip", "angle", "aliases")
_V4_DROPPED_ATTR_COLUMNS = ("equipment", "support", "grip", "angle")


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        is not None
    )


def _migrate_structure(conn: sqlite3.Connection) -> bool:
    """PRAGMA user_version 기반 구조 마이그레이션. 반환: v4 데이터 단계가 필요한지.

    - 각 블록은 컬럼 존재 확인 기반 멱등 — 반쯤 적용된 상태에서 재기동해도 안전.
    - 버전 기록은 init_db 끝에서 한 번 (v4 데이터 단계까지 끝난 뒤). 미래 버전 DB를
      구버전 코드로 열어도 하향 기록하지 않는다.
    - VIEW는 여기서 만들지 않는다 — 구조가 끝난 뒤 _ensure_views가 단일 정의로 재생성.

    v1→v2 (§3.6): exercise 속성 컬럼 ALTER (시드 백필은 v4가 tags로 대체하므로 생략).
    v2→v3 (§3.7): workout_set.intent_muscle_group_id ALTER.
    v3→v4 (§10): user/machine/favorite 테이블(DDL), muscle_group 계층 컬럼,
      exercise(user_id·default_target_id·tags·machine_id, 속성 4컬럼 → tags 후 DROP),
      workout_set.intent_muscle_group_id → target_id RENAME,
      workout_session.user_id, body_weight_log 재구축(UNIQUE(user_id, date)).
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return False

    if version < 2 and "base_movement" not in _columns(conn, "exercise"):
        # 진짜 v1 테이블만 (신규 DB는 DDL이 이미 v4 형태라 건너뛴다)
        for col in _V2_ATTR_COLUMNS:
            conn.execute(f"ALTER TABLE exercise ADD COLUMN {col} TEXT")
    if version < 3:
        ws = _columns(conn, "workout_set")
        if "intent_muscle_group_id" not in ws and "target_id" not in ws:
            conn.execute(
                "ALTER TABLE workout_set ADD COLUMN"
                " intent_muscle_group_id INTEGER REFERENCES muscle_group(id)"
            )

    # ---- v4 ----
    # 구버전 VIEW는 삭제된 컬럼을 참조하므로 구조 변경 전에 내린다 (_ensure_views가 재생성)
    conn.execute("DROP VIEW IF EXISTS set_volume")
    conn.execute("DROP VIEW IF EXISTS target_path")

    mg = _columns(conn, "muscle_group")
    if "level" not in mg:
        conn.execute("ALTER TABLE muscle_group ADD COLUMN level INTEGER NOT NULL DEFAULT 2")
    if "parent_id" not in mg:
        conn.execute("ALTER TABLE muscle_group ADD COLUMN parent_id INTEGER REFERENCES muscle_group(id)")

    ex = _columns(conn, "exercise")
    for col, ddl in (
        ("tags", "TEXT"),
        ("default_target_id", "INTEGER REFERENCES muscle_group(id)"),
        ("user_id", "INTEGER REFERENCES user(id)"),
        ("machine_id", "INTEGER REFERENCES machine(id)"),
    ):
        if col not in ex:
            conn.execute(f"ALTER TABLE exercise ADD COLUMN {col} {ddl}")
    if any(c in ex for c in _V4_DROPPED_ATTR_COLUMNS):
        present = [c for c in _V4_DROPPED_ATTR_COLUMNS if c in ex]
        rows = conn.execute(
            f"SELECT id, tags, {', '.join(present)} FROM exercise"
        ).fetchall()
        for r in rows:
            merged = [r["tags"]] + [r[c] for c in present]
            parts: list[str] = []
            for chunk in merged:
                for t in (chunk or "").split(","):
                    t = t.strip()
                    if t and t not in parts:
                        parts.append(t)
            conn.execute(
                "UPDATE exercise SET tags = ? WHERE id = ?",
                (",".join(parts) if parts else None, r["id"]),
            )
        for c in present:
            conn.execute(f"ALTER TABLE exercise DROP COLUMN {c}")

    ws = _columns(conn, "workout_set")
    if "target_id" not in ws:
        if "intent_muscle_group_id" in ws:
            conn.execute("ALTER TABLE workout_set RENAME COLUMN intent_muscle_group_id TO target_id")
        else:
            conn.execute(
                "ALTER TABLE workout_set ADD COLUMN target_id INTEGER REFERENCES muscle_group(id)"
            )

    if "user_id" not in _columns(conn, "workout_session"):
        conn.execute("ALTER TABLE workout_session ADD COLUMN user_id INTEGER REFERENCES user(id)")

    if "user_id" not in _columns(conn, "body_weight_log"):
        # UNIQUE(date) → UNIQUE(user_id, date): 제약 변경은 테이블 재구축이 정석
        conn.execute(
            """
            CREATE TABLE body_weight_log_v4 (
                id        INTEGER PRIMARY KEY,
                user_id   INTEGER REFERENCES user(id),
                date      TEXT NOT NULL,
                weight_kg REAL NOT NULL CHECK (weight_kg > 0),
                UNIQUE (user_id, date)
            )
            """
        )
        conn.execute(
            "INSERT INTO body_weight_log_v4 (id, user_id, date, weight_kg)"
            " SELECT id, NULL, date, weight_kg FROM body_weight_log"
        )
        conn.execute("DROP TABLE body_weight_log")
        conn.execute("ALTER TABLE body_weight_log_v4 RENAME TO body_weight_log")
    return True


def _ensure_views(conn: sqlite3.Connection) -> None:
    conn.execute("DROP VIEW IF EXISTS set_volume")
    conn.execute("DROP VIEW IF EXISTS target_path")
    conn.execute(SET_VOLUME_VIEW)
    conn.execute(TARGET_PATH_VIEW)
    # v4 컬럼(user_id)에 걸리는 인덱스는 마이그레이션 뒤에만 만들 수 있다 (DDL 단계엔 컬럼이 없을 수 있음)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session_user ON workout_session(user_id, date)")


def _normalize_name(name: str) -> str:
    return name.replace(" ", "").replace("푸쉬", "푸시").replace("이지바", "EZ바").lower()


# v3 커스텀 종목 → 내장 종목 병합 표 (정규화 이름이 같으면 자동, 아래는 그 외 명시 매핑)
# 사용자 결정(2026-09-08): "남아 있는 기록은 새 카테고리 이름으로 바꿔서 병합"
CUSTOM_MERGE_MAP: dict[str, str] = {
    "스탠딩 바벨 스쿼트": "백스쿼트",
    "스탠딩 이지바 컬": "EZ바 컬",
    "오버헤드 케이블 푸쉬다운": "케이블 오버헤드 트라이셉스 익스텐션",
    "스탠딩 원암 케이블 푸쉬다운": "원암 케이블 푸시다운",
    "시티드 디클라인 체스트 프레스 머신": "디클라인 프레스 머신",
    "암풀다운": "스트레이트 암 풀다운",
}


def _apply_v4_data(conn: sqlite3.Connection) -> list[str]:
    """v4 데이터 단계 (seed 이후 실행). 반환: 병합 로그.

    1. 사용자 테이블이 비어 있으면 .env(ADMIN_USERNAME/APP_PASSWORD)로 첫 관리자 생성
    2. 소유자 없는 세션·체중·커스텀 종목을 관리자에게 귀속
    3. 내장 종목의 기본 타겟·계열·태그·별칭을 시드 값으로 채움 (default_target 비어 있는 행만)
    4. 커스텀 종목의 기본 타겟 = 옛 주동근 첫 번째 (exercise_muscle이 남아 있을 때)
    5. 세트의 target_id 비어 있으면 종목 기본 타겟
    6. exercise_muscle 삭제, 관리자 즐겨찾기 초기값(세트 수 상위 15), 커스텀→내장 병합
    """
    from .auth import hash_password

    log: list[str] = []
    settings = get_settings()
    admin = conn.execute("SELECT id FROM user WHERE is_admin = 1 ORDER BY id LIMIT 1").fetchone()
    if admin is None:
        conn.execute(
            "INSERT INTO user (username, password_hash, display_name, is_admin) VALUES (?, ?, ?, 1)",
            (settings.ADMIN_USERNAME, hash_password(settings.APP_PASSWORD), settings.ADMIN_USERNAME),
        )
        admin_id = conn.execute("SELECT id FROM user WHERE username = ?", (settings.ADMIN_USERNAME,)).fetchone()[0]
        log.append(f"admin user created: {settings.ADMIN_USERNAME}")
    else:
        admin_id = admin["id"]

    conn.execute("UPDATE workout_session SET user_id = ? WHERE user_id IS NULL", (admin_id,))
    conn.execute("UPDATE body_weight_log SET user_id = ? WHERE user_id IS NULL", (admin_id,))
    conn.execute("UPDATE exercise SET user_id = ? WHERE is_builtin = 0 AND user_id IS NULL", (admin_id,))

    seed_by_name = {e[0]: e for e in EXERCISES}
    for r in conn.execute(
        "SELECT id, name_ko FROM exercise WHERE is_builtin = 1 AND default_target_id IS NULL"
    ).fetchall():
        s = seed_by_name.get(r["name_ko"])
        if s is None:
            continue
        _, name_en, base, tags, target, _bw, _mult, aliases = s
        conn.execute(
            "UPDATE exercise SET name_en = COALESCE(name_en, ?), base_movement = ?, tags = ?,"
            " aliases = ?, default_target_id = (SELECT id FROM muscle_group WHERE code = ?)"
            " WHERE id = ?",
            (name_en, base, tags_to_text(tags), aliases, target, r["id"]),
        )

    if _table_exists(conn, "exercise_muscle"):
        conn.execute(
            """
            UPDATE exercise SET default_target_id = (
                SELECT em.muscle_group_id FROM exercise_muscle em
                JOIN muscle_group mg ON mg.id = em.muscle_group_id
                WHERE em.exercise_id = exercise.id
                ORDER BY CASE em.role WHEN 'primary' THEN 0 ELSE 1 END, mg.sort_order
                LIMIT 1
            ) WHERE default_target_id IS NULL
            """
        )
        conn.execute("DROP TABLE exercise_muscle")
    # 시드에도 옛 매핑에도 없는 행(이론상 없음)은 '가슴'으로 두지 않고 NULL 유지 → API가 422로 드러낸다

    conn.execute(
        "UPDATE workout_set SET target_id = (SELECT default_target_id FROM exercise e"
        " WHERE e.id = workout_set.exercise_id) WHERE target_id IS NULL"
    )

    # 커스텀 → 내장 (정규화 이름 일치 + 명시 매핑).
    # - 내장 행이 따로 있으면: 세트를 옮기고 커스텀 삭제 (병합)
    # - 이름이 라이브러리와 같아 시드 INSERT가 무시된 경우: 그 행을 내장으로 승격 (id·기록 보존)
    seed_by_norm = {_normalize_name(e[0]): e for e in EXERCISES}
    builtin_by_norm = {
        _normalize_name(r["name_ko"]): r["id"]
        for r in conn.execute("SELECT id, name_ko FROM exercise WHERE is_builtin = 1").fetchall()
    }
    for c in conn.execute("SELECT id, name_ko FROM exercise WHERE is_builtin = 0").fetchall():
        mapped = CUSTOM_MERGE_MAP.get(c["name_ko"])
        key = _normalize_name(mapped) if mapped else _normalize_name(c["name_ko"])
        builtin_id = builtin_by_norm.get(key)
        if builtin_id is not None and builtin_id != c["id"]:
            moved = conn.execute(
                "UPDATE workout_set SET exercise_id = ? WHERE exercise_id = ?",
                (builtin_id, c["id"]),
            ).rowcount
            conn.execute("DELETE FROM favorite WHERE exercise_id = ?", (c["id"],))
            conn.execute("DELETE FROM exercise WHERE id = ?", (c["id"],))
            name = conn.execute(
                "SELECT name_ko FROM exercise WHERE id = ?", (builtin_id,)
            ).fetchone()[0]
            log.append(f"custom merged: {c['name_ko']} -> {name} ({moved} sets)")
        elif key in seed_by_norm:
            name_ko, name_en, base, tags, target, bw, mult, aliases = seed_by_norm[key]
            conn.execute(
                "UPDATE exercise SET name_ko = ?, name_en = ?, base_movement = ?, tags = ?,"
                " aliases = ?, bodyweight_factor = ?, load_multiplier = ?, is_builtin = 1,"
                " user_id = NULL,"
                " default_target_id = (SELECT id FROM muscle_group WHERE code = ?)"
                " WHERE id = ?",
                (name_ko, name_en, base, tags_to_text(tags), aliases, bw, mult, target, c["id"]),
            )
            builtin_by_norm[key] = c["id"]
            log.append(f"custom promoted: {c['name_ko']} -> builtin '{name_ko}'")
        else:
            log.append(f"custom kept: {c['name_ko']}")

    if conn.execute("SELECT 1 FROM favorite WHERE user_id = ? LIMIT 1", (admin_id,)).fetchone() is None:
        top = conn.execute(
            """
            SELECT ws.exercise_id AS eid, COUNT(*) AS c
            FROM workout_set ws JOIN workout_session s ON s.id = ws.session_id
            WHERE s.user_id = ?
            GROUP BY ws.exercise_id ORDER BY c DESC, MAX(s.date) DESC LIMIT 15
            """,
            (admin_id,),
        ).fetchall()
        for i, r in enumerate(top):
            conn.execute(
                "INSERT OR IGNORE INTO favorite (user_id, exercise_id, sort_order) VALUES (?, ?, ?)",
                (admin_id, r["eid"], i),
            )
        if top:
            log.append(f"favorites seeded for admin: {len(top)}")
    return log


def init_db(db_path: str | None = None) -> list[str]:
    """스키마 생성·마이그레이션·시드. 반환: 마이그레이션 로그 (테스트·기동 로그용)."""
    conn = _connect(db_path or get_settings().DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(DDL)
        need_v4_data = _migrate_structure(conn)
        _ensure_views(conn)
        seed(conn)
        log: list[str] = []
        if need_v4_data:
            log = _apply_v4_data(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        for line in log:
            logger.info("migration: %s", line)
        return log
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    conn = _connect(get_settings().DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
