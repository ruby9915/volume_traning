import sqlite3

# (code, name_ko, region, sort_order) — SETTING.MD §3.4
MUSCLE_GROUPS: list[tuple[str, str, str, int]] = [
    ("chest", "가슴", "chest", 1),
    ("back", "등", "back", 2),
    ("lower_back", "허리(기립근)", "back", 3),
    ("shoulders", "어깨", "shoulders", 4),
    ("biceps", "이두", "arms", 5),
    ("triceps", "삼두", "arms", 6),
    ("forearms", "전완", "arms", 7),
    ("quads", "대퇴사두", "legs", 8),
    ("hamstrings", "햄스트링", "legs", 9),
    ("glutes", "둔근", "legs", 10),
    ("calves", "종아리", "legs", 11),
    ("abs", "복근", "core", 12),
]

# §3.4 상위 region 6분류 — 순서는 types.ts REGION_NAMES_KO와 동일.
# sessions(주부위 tie-break 순서)·stats(per_region 키)가 공유하는 단일 정의.
REGION_NAMES_KO: dict[str, str] = {
    "chest": "가슴",
    "back": "등",
    "shoulders": "어깨",
    "arms": "팔",
    "legs": "하체",
    "core": "코어",
}
REGIONS: list[str] = list(REGION_NAMES_KO)

# (name_ko, name_en, primary, secondary, bodyweight_factor, load_multiplier) — SETTING.MD §3.5
EXERCISES: list[tuple[str, str, list[str], list[str], float, float]] = [
    ("벤치프레스", "Barbell Bench Press", ["chest"], ["triceps", "shoulders"], 0, 1),
    ("인클라인 벤치프레스", "Incline Barbell Bench Press", ["chest"], ["shoulders", "triceps"], 0, 1),
    ("덤벨 벤치프레스", "Dumbbell Bench Press", ["chest"], ["triceps", "shoulders"], 0, 2),
    ("인클라인 덤벨프레스", "Incline Dumbbell Press", ["chest"], ["shoulders", "triceps"], 0, 2),
    ("체스트 프레스 머신", "Chest Press Machine", ["chest"], ["triceps"], 0, 1),
    ("딥스", "Dips", ["chest"], ["triceps", "shoulders"], 1.0, 1),
    ("푸시업", "Push-up", ["chest"], ["triceps", "shoulders"], 0.65, 1),
    ("케이블 크로스오버", "Cable Crossover", ["chest"], [], 0, 1),
    ("펙덱 플라이", "Pec Deck Fly", ["chest"], [], 0, 1),
    ("데드리프트", "Conventional Deadlift", ["hamstrings", "glutes", "lower_back"], ["back", "quads", "forearms"], 0, 1),
    ("바벨 로우", "Barbell Row", ["back"], ["biceps", "lower_back"], 0, 1),
    ("풀업", "Pull-up", ["back"], ["biceps"], 1.0, 1),
    ("친업", "Chin-up", ["back"], ["biceps"], 1.0, 1),
    ("랫풀다운", "Lat Pulldown", ["back"], ["biceps"], 0, 1),
    ("시티드 케이블 로우", "Seated Cable Row", ["back"], ["biceps"], 0, 1),
    ("원암 덤벨 로우", "One-arm Dumbbell Row", ["back"], ["biceps"], 0, 1),
    ("티바 로우", "T-Bar Row", ["back"], ["biceps"], 0, 1),
    ("슈러그", "Barbell Shrug", ["back"], ["forearms"], 0, 1),
    ("백 익스텐션", "Back Extension", ["lower_back"], ["glutes", "hamstrings"], 0.6, 1),
    ("오버헤드 프레스", "Overhead Press", ["shoulders"], ["triceps"], 0, 1),
    ("덤벨 숄더프레스", "Dumbbell Shoulder Press", ["shoulders"], ["triceps"], 0, 2),
    ("사이드 레터럴 레이즈", "Lateral Raise", ["shoulders"], [], 0, 2),
    ("프론트 레이즈", "Front Raise", ["shoulders"], [], 0, 2),
    ("리어델트 플라이", "Rear Delt Fly", ["shoulders"], ["back"], 0, 2),
    ("페이스풀", "Face Pull", ["shoulders"], ["back"], 0, 1),
    ("바벨 컬", "Barbell Curl", ["biceps"], ["forearms"], 0, 1),
    ("덤벨 컬", "Dumbbell Curl", ["biceps"], ["forearms"], 0, 2),
    ("해머 컬", "Hammer Curl", ["biceps"], ["forearms"], 0, 2),
    ("케이블 푸시다운", "Cable Pushdown", ["triceps"], [], 0, 1),
    ("라잉 트라이셉스 익스텐션", "Lying Triceps Extension", ["triceps"], [], 0, 1),
    ("오버헤드 트라이셉스 익스텐션", "Overhead Triceps Extension", ["triceps"], [], 0, 1),
    ("리스트 컬", "Wrist Curl", ["forearms"], [], 0, 1),
    ("백스쿼트", "Barbell Back Squat", ["quads", "glutes"], ["hamstrings", "lower_back"], 0, 1),
    ("프론트 스쿼트", "Front Squat", ["quads"], ["glutes", "abs"], 0, 1),
    ("레그 프레스", "Leg Press", ["quads"], ["glutes", "hamstrings"], 0, 1),
    ("런지", "Dumbbell Lunge", ["quads", "glutes"], ["hamstrings"], 0, 2),
    ("불가리안 스플릿 스쿼트", "Bulgarian Split Squat", ["quads", "glutes"], ["hamstrings"], 0, 1),
    ("루마니안 데드리프트", "Romanian Deadlift", ["hamstrings", "glutes"], ["lower_back"], 0, 1),
    ("레그 컬", "Leg Curl", ["hamstrings"], [], 0, 1),
    ("레그 익스텐션", "Leg Extension", ["quads"], [], 0, 1),
    ("힙 쓰러스트", "Hip Thrust", ["glutes"], ["hamstrings"], 0, 1),
    ("스탠딩 카프 레이즈", "Standing Calf Raise", ["calves"], [], 0, 1),
    ("크런치", "Crunch", ["abs"], [], 0.3, 1),
    ("행잉 레그 레이즈", "Hanging Leg Raise", ["abs"], ["forearms"], 0.5, 1),
    ("케이블 크런치", "Cable Crunch", ["abs"], [], 0, 1),
]


# §3.6 시드 속성 백필 — "명백한 것만" 원칙 (자의적 결정 금지)
# name_ko → (base_movement, equipment, support, grip, angle, aliases)
#   base_movement: 확실한 계열만 — 벤치프레스 5종 / 로우 / 스쿼트 / 컬(이두).
#     프레스 base 통합 여부 등 백필 시험에서 애매 판정된 것은 NULL.
#     레그 컬·리스트 컬은 이름만 '컬'일 뿐 부위가 달라 계열 합산이 왜곡되므로 NULL.
#   equipment: 이름에 바벨/덤벨/케이블/머신이 명시된 것 + 바벨/덤벨 기본 관행이
#     확실한 것(오버헤드 프레스=바벨, 레이즈류=덤벨(시드 ×2가 이미 덤벨 전제) 등).
#     랫풀다운(케이블/머신 경계 애매)·티바 로우·백 익스텐션 등은 NULL.
#   support: 시티드/스탠딩/라잉이 이름에 명백한 것만.
#   grip: 전부 NULL (명백 사례 없음 — 해머 컬의 뉴트럴도 정체성 논쟁 여지).
#   angle: 이름에 인클라인이 명시된 것만.
#   aliases: 확실한 통용 동의어만, 쉼표 구분.
ATTR_BACKFILL: dict[str, tuple[str | None, str | None, str | None, str | None, str | None, str | None]] = {
    # (base, equipment, support, grip, angle, aliases)
    "벤치프레스": ("벤치프레스", "바벨", None, None, None, None),
    "인클라인 벤치프레스": ("벤치프레스", "바벨", None, None, "인클라인", None),
    "덤벨 벤치프레스": ("벤치프레스", "덤벨", None, None, None, None),
    "인클라인 덤벨프레스": ("벤치프레스", "덤벨", None, None, "인클라인", None),
    "체스트 프레스 머신": ("벤치프레스", "머신", None, None, None, None),
    "케이블 크로스오버": (None, "케이블", None, None, None, None),
    "펙덱 플라이": (None, "머신", None, None, None, None),
    "데드리프트": (None, "바벨", None, None, None, "컨벤셔널 데드리프트"),
    "바벨 로우": ("로우", "바벨", None, None, None, None),
    "시티드 케이블 로우": ("로우", "케이블", "시티드", None, None, "시티드 로우"),
    "원암 덤벨 로우": ("로우", "덤벨", None, None, None, None),
    "티바 로우": ("로우", None, None, None, None, None),
    "슈러그": (None, "바벨", None, None, None, None),
    "오버헤드 프레스": (None, "바벨", None, None, None, "숄더프레스,밀리터리 프레스"),
    "덤벨 숄더프레스": (None, "덤벨", None, None, None, None),
    "사이드 레터럴 레이즈": (None, "덤벨", None, None, None, "레터럴레이즈,사이드 레이즈"),
    "프론트 레이즈": (None, "덤벨", None, None, None, None),
    "리어델트 플라이": (None, "덤벨", None, None, None, None),
    "페이스풀": (None, "케이블", None, None, None, None),
    "바벨 컬": ("컬", "바벨", None, None, None, None),
    "덤벨 컬": ("컬", "덤벨", None, None, None, None),
    "해머 컬": ("컬", "덤벨", None, None, None, None),
    "케이블 푸시다운": (None, "케이블", None, None, None, "트라이셉스 푸시다운"),
    "라잉 트라이셉스 익스텐션": (None, None, "라잉", None, None, None),
    "백스쿼트": ("스쿼트", "바벨", None, None, None, "바벨 스쿼트"),
    "프론트 스쿼트": ("스쿼트", "바벨", None, None, None, None),
    "레그 프레스": (None, "머신", None, None, None, None),
    "런지": (None, "덤벨", None, None, None, None),
    "루마니안 데드리프트": (None, "바벨", None, None, None, "RDL"),
    "레그 컬": (None, "머신", None, None, None, None),
    "레그 익스텐션": (None, "머신", None, None, None, None),
    "스탠딩 카프 레이즈": (None, None, "스탠딩", None, None, None),
    "케이블 크런치": (None, "케이블", None, None, None, None),
}


def backfill_attributes(conn: sqlite3.Connection) -> None:
    """§3.6 시드 백필 — v1→v2 마이그레이션(db._migrate)에서 1회만 호출.

    매 기동 seed 경로에서 실행하지 않는다 — 그러면 사용자가 내장 종목의
    속성 6개를 전부 비웠을 때(PATCH null) 재기동마다 시드값이 되살아나
    '비우기' 결정이 유지 불가능해진다. 신규 DB의 내장 종목 속성은
    seed()의 INSERT가 직접 채운다.

    가드는 6컬럼 전부 NULL인 내장 행만 UPDATE. 스펙 §3.6의 원 가드
    `is_builtin=1 AND base_movement IS NULL`은 base NULL로 남는 백필 행
    (예: 슈러그)을 마이그레이션 재시도 때 다시 덮어쓸 수 있어, 그 부분집합인
    전-6-NULL 가드로 좁혔다 (SETTING.MD §3.6에 반영됨).
    """
    for name_ko, attrs in ATTR_BACKFILL.items():
        conn.execute(
            """
            UPDATE exercise
            SET base_movement = ?, equipment = ?, support = ?,
                grip = ?, angle = ?, aliases = ?
            WHERE name_ko = ? AND is_builtin = 1
              AND base_movement IS NULL AND equipment IS NULL
              AND support IS NULL AND grip IS NULL
              AND angle IS NULL AND aliases IS NULL
            """,
            (*attrs, name_ko),
        )


def seed(conn: sqlite3.Connection) -> None:
    for code, name_ko, region, sort_order in MUSCLE_GROUPS:
        conn.execute(
            "INSERT OR IGNORE INTO muscle_group (code, name_ko, region, sort_order)"
            " VALUES (?, ?, ?, ?)",
            (code, name_ko, region, sort_order),
        )
    for name_ko, name_en, primary, secondary, bw_factor, multiplier in EXERCISES:
        # §3.6 속성은 INSERT에 포함 — 신규 행만 시드값을 받고, 기존 행은
        # INSERT OR IGNORE로 건드리지 않아 사용자 수정·비우기가 보존된다
        attrs = ATTR_BACKFILL.get(name_ko, (None, None, None, None, None, None))
        cur = conn.execute(
            "INSERT OR IGNORE INTO exercise"
            " (name_ko, name_en, bodyweight_factor, load_multiplier, is_builtin,"
            "  base_movement, equipment, support, grip, angle, aliases)"
            " VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
            (name_ko, name_en, bw_factor, multiplier, *attrs),
        )
        if cur.rowcount == 0:
            continue  # 기존 행(사용자 수정 포함) 보존
        exercise_id = cur.lastrowid
        for role, codes in (("primary", primary), ("secondary", secondary)):
            for code in codes:
                conn.execute(
                    "INSERT OR IGNORE INTO exercise_muscle (exercise_id, muscle_group_id, role)"
                    " SELECT ?, id, ? FROM muscle_group WHERE code = ?",
                    (exercise_id, role, code),
                )
    conn.commit()
