"""타겟 부위 분류 — SETTING.MD §10.2 (v2).

2단계 테이블(muscle_group) + 가상 상위 단계(region 컬럼):
- level 2 = 근육 (기존 12분류 코드 그대로 + adductors·hip_flexors 추가)
- level 3 = 세부 (근육 아래 세부 부위, parent_code로 연결)
- region  = 부위 6분류 (chest/back/shoulders/arms/legs/core), 컬럼으로만 존재

세트는 level 2 또는 3 어느 행이든 타겟으로 고를 수 있고, 볼륨은 그 행에 100% 귀속된 뒤
근육(level 2)·부위(region)로 자동 합산된다. 코드는 안정 식별자라 변경 금지 — 이름만 고칠 것.
"""

# §3.4 상위 region 6분류 — 순서는 types.ts REGION_NAMES_KO와 동일 (동률 tie-break 순서)
REGION_NAMES_KO: dict[str, str] = {
    "chest": "가슴",
    "back": "등",
    "shoulders": "어깨",
    "arms": "팔",
    "legs": "하체",
    "core": "코어",
}
REGIONS: list[str] = list(REGION_NAMES_KO)

# (code, name_ko, region, level, parent_code, sort_order)
TARGETS: list[tuple[str, str, str, int, str | None, int]] = [
    # ---- 가슴 ----
    ("chest", "가슴", "chest", 2, None, 10),
    ("upper_chest", "상부 가슴", "chest", 3, "chest", 11),
    ("mid_chest", "중부 가슴", "chest", 3, "chest", 12),
    ("lower_chest", "하부 가슴", "chest", 3, "chest", 13),
    ("serratus", "전거근", "chest", 3, "chest", 14),
    # ---- 등 ----
    ("back", "등", "back", 2, None, 20),
    ("lats", "광배근", "back", 3, "back", 21),
    ("upper_traps", "승모근 상부", "back", 3, "back", 22),
    ("mid_traps", "승모근 중부", "back", 3, "back", 23),
    ("lower_traps", "승모근 하부", "back", 3, "back", 24),
    ("rhomboids", "능형근", "back", 3, "back", 25),
    ("teres_major", "대원근", "back", 3, "back", 26),
    ("lower_back", "허리(기립근)", "back", 2, None, 30),
    ("erector_spinae", "척추기립근", "back", 3, "lower_back", 31),
    ("quadratus_lumborum", "요방형근", "back", 3, "lower_back", 32),
    # ---- 어깨 ----
    ("shoulders", "어깨", "shoulders", 2, None, 40),
    ("front_delt", "전면 삼각근", "shoulders", 3, "shoulders", 41),
    ("side_delt", "측면 삼각근", "shoulders", 3, "shoulders", 42),
    ("rear_delt", "후면 삼각근", "shoulders", 3, "shoulders", 43),
    ("rotator_cuff", "회전근개", "shoulders", 3, "shoulders", 44),
    # ---- 팔 ----
    ("biceps", "이두", "arms", 2, None, 50),
    ("biceps_long", "이두 장두", "arms", 3, "biceps", 51),
    ("biceps_short", "이두 단두", "arms", 3, "biceps", 52),
    ("brachialis", "상완근", "arms", 3, "biceps", 53),
    ("triceps", "삼두", "arms", 2, None, 60),
    ("triceps_long", "삼두 장두", "arms", 3, "triceps", 61),
    ("triceps_lateral", "삼두 외측두", "arms", 3, "triceps", 62),
    ("triceps_medial", "삼두 내측두", "arms", 3, "triceps", 63),
    ("forearms", "전완", "arms", 2, None, 70),
    ("wrist_flexors", "손목 굴곡근", "arms", 3, "forearms", 71),
    ("wrist_extensors", "손목 신전근", "arms", 3, "forearms", 72),
    ("brachioradialis", "상완요골근", "arms", 3, "forearms", 73),
    # ---- 하체 ----
    ("quads", "대퇴사두", "legs", 2, None, 80),
    ("vastus_medialis", "내측광근", "legs", 3, "quads", 81),
    ("vastus_lateralis", "외측광근", "legs", 3, "quads", 82),
    ("rectus_femoris", "대퇴직근", "legs", 3, "quads", 83),
    ("vastus_intermedius", "중간광근", "legs", 3, "quads", 84),
    ("hamstrings", "햄스트링", "legs", 2, None, 90),
    ("biceps_femoris", "대퇴이두근", "legs", 3, "hamstrings", 91),
    ("medial_hamstrings", "내측 햄스트링", "legs", 3, "hamstrings", 92),
    ("glutes", "둔근", "legs", 2, None, 100),
    ("glute_max", "대둔근", "legs", 3, "glutes", 101),
    ("glute_med", "중둔근", "legs", 3, "glutes", 102),
    ("glute_min", "소둔근", "legs", 3, "glutes", 103),
    ("calves", "종아리", "legs", 2, None, 110),
    ("gastrocnemius", "비복근", "legs", 3, "calves", 111),
    ("soleus", "가자미근", "legs", 3, "calves", 112),
    ("tibialis_anterior", "전경골근", "legs", 3, "calves", 113),
    ("adductors", "내전근", "legs", 2, None, 120),
    ("adductor_magnus", "대내전근", "legs", 3, "adductors", 121),
    ("adductor_longus", "장내전근", "legs", 3, "adductors", 122),
    # ---- 코어 ----
    ("abs", "복근", "core", 2, None, 130),
    ("rectus_abdominis", "복직근", "core", 3, "abs", 131),
    ("obliques", "복사근", "core", 3, "abs", 132),
    ("transverse_abdominis", "복횡근", "core", 3, "abs", 133),
    ("hip_flexors", "고관절 굴곡근", "core", 2, None, 140),
    ("iliopsoas", "장요근", "core", 3, "hip_flexors", 141),
]

TARGET_CODES: frozenset[str] = frozenset(t[0] for t in TARGETS)
