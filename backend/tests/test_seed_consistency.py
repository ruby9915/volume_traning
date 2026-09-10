"""시드 마스터 데이터(seed_data) 정합성 — 타겟 트리, 종목 라이브러리, 머신 카탈로그.

분류·라이브러리는 데이터이지만 코드처럼 서로를 참조하므로(종목 → 타겟 코드, 세부 → 근육),
한쪽만 고치면 기동 시 seed()가 ValueError로 죽거나 API가 500을 낸다. 여기서 먼저 잡는다.
"""

from app.seed_data.exercises import EXERCISES
from app.seed_data.machines import MACHINES
from app.seed_data.secondary import SECONDARY
from app.seed_data.targets import REGION_NAMES_KO, REGIONS, TARGET_CODES, TARGETS

# v1 내장 45종 — 실사용 DB에 이미 있어 이름이 바뀌면 시드가 중복 행을 만든다
LEGACY_45 = [
    "벤치프레스", "인클라인 벤치프레스", "덤벨 벤치프레스", "인클라인 덤벨프레스", "체스트 프레스 머신",
    "딥스", "푸시업", "케이블 크로스오버", "펙덱 플라이", "데드리프트", "바벨 로우", "풀업", "친업",
    "랫풀다운", "시티드 케이블 로우", "원암 덤벨 로우", "티바 로우", "슈러그", "백 익스텐션",
    "오버헤드 프레스", "덤벨 숄더프레스", "사이드 레터럴 레이즈", "프론트 레이즈", "리어델트 플라이",
    "페이스풀", "바벨 컬", "덤벨 컬", "해머 컬", "케이블 푸시다운", "라잉 트라이셉스 익스텐션",
    "오버헤드 트라이셉스 익스텐션", "리스트 컬", "백스쿼트", "프론트 스쿼트", "레그 프레스", "런지",
    "불가리안 스플릿 스쿼트", "루마니안 데드리프트", "레그 컬", "레그 익스텐션", "힙 쓰러스트",
    "스탠딩 카프 레이즈", "크런치", "행잉 레그 레이즈", "케이블 크런치",
]


def test_target_tree_is_consistent():
    by_code = {t[0]: t for t in TARGETS}
    assert len(by_code) == len(TARGETS)  # 코드 유일
    assert list(REGION_NAMES_KO) == REGIONS
    for code, name_ko, region, level, parent, sort_order in TARGETS:
        assert name_ko and region in REGIONS, code
        assert level in (2, 3), code
        if level == 2:
            assert parent is None, code
        else:
            assert parent in by_code and by_code[parent][3] == 2, code
            assert by_code[parent][2] == region, f"{code}: 부위가 부모와 다름"
    # 근육(level 2)마다 세부가 0개 이상 — 세부 없는 근육도 허용
    assert len([t for t in TARGETS if t[3] == 2]) >= 12


def test_exercise_library_is_consistent():
    names = [e[0] for e in EXERCISES]
    assert len(names) == len(set(names)), "종목 이름 중복"
    for name_ko, name_en, base, tags, target, bw, mult, aliases in EXERCISES:
        assert name_ko.strip() == name_ko and 1 <= len(name_ko) <= 50, name_ko
        assert name_en, name_ko
        assert base and base.strip() == base, f"{name_ko}: base_movement 필수"
        assert isinstance(tags, tuple) and all(t.strip() and len(t) <= 30 for t in tags), name_ko
        assert len(tags) == len(set(tags)) <= 20, name_ko
        assert target in TARGET_CODES, f"{name_ko}: unknown target {target}"
        assert 0 <= bw <= 1 and mult > 0, name_ko
        assert aliases is None or (aliases.strip() and len(aliases) <= 200), name_ko
    missing = [n for n in LEGACY_45 if n not in names]
    assert not missing, f"v1 내장 종목 누락: {missing}"


def test_secondary_targets_are_consistent():
    """§11.2 보조 근육 초안: 라이브러리 전 종목에 항목, 코드 유효, 기본 타겟(및 같은 근육) 제외, ≤3."""
    parent = {t[0]: (t[4] or t[0]) for t in TARGETS}
    names = {e[0] for e in EXERCISES}
    assert set(SECONDARY) == names, f"불일치: {set(SECONDARY) ^ names}"
    for name_ko, *_rest in EXERCISES:
        target = _rest[3]
        codes = SECONDARY[name_ko]
        assert isinstance(codes, tuple) and len(codes) <= 3, name_ko
        assert len(codes) == len(set(codes)), f"{name_ko}: 중복"
        for c in codes:
            assert c in TARGET_CODES, f"{name_ko}: unknown secondary {c}"
            assert parent[c] != parent[target], f"{name_ko}: 보조 {c}가 기본 타겟 {target}과 같은 근육"


def test_machine_catalog_is_consistent():
    keys = [(m[0], m[1]) for m in MACHINES]
    assert len(keys) == len(set(keys)), "(brand, model) 중복"
    for brand, model, name_ko, target in MACHINES:
        assert brand and model and name_ko, (brand, model)
        assert target is None or target in TARGET_CODES, (brand, model, target)
