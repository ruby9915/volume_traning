"""§15.4 머신 → 종목 추천(app.machine_match) — DB 없이 시드 데이터만으로 순위를 확인한다.

추천은 후보 제시라 순위 전체를 고정하지 않는다. "누가 봐도 맞는 종목이 맨 위·상위에 있다"와
"엉뚱한 장비의 종목이 섞이지 않는다"만 단언한다.
"""

from app.machine_match import MIN_SCORE, ExerciseInfo, MachineInfo, score, suggest
from app.seed_data.exercises import EXERCISES
from app.seed_data.machines import MACHINES
from app.seed_data.targets import TARGETS

_TARGET = {t[0]: t for t in TARGETS}  # code → (code, name_ko, region, level, parent_code, sort)


def _muscle(code: str) -> str:
    return _TARGET[code][4] or code


LIBRARY = [
    ExerciseInfo(
        id=i,
        name_ko=name_ko,
        name_en=name_en,
        target=target,
        muscle=_muscle(target),
        region=_TARGET[target][2],
        tags=frozenset(tags),
        aliases=tuple(a.strip() for a in (aliases or "").split(",") if a.strip()),
    )
    for i, (name_ko, name_en, _base, tags, target, _bw, _mult, aliases) in enumerate(EXERCISES, start=1)
]
BY_ID = {e.id: e for e in LIBRARY}
_MACHINE = {(brand, model): (name_ko, target) for brand, model, name_ko, target in MACHINES}


def _machine(brand: str, model: str) -> MachineInfo:
    name_ko, target = _MACHINE[(brand, model)]
    return MachineInfo(
        brand=brand, model=model, name_ko=name_ko, target=target,
        muscle=_muscle(target) if target else None,
        region=_TARGET[target][2] if target else None,
    )


def _names(machine: MachineInfo, **kw) -> list[str]:
    return [BY_ID[i].name_ko for i in suggest(machine, LIBRARY, **kw)]


def test_single_purpose_machine_top_suggestion_matches_model_name():
    assert _names(_machine("Hammer Strength", "MTS Iso-Lateral Row"))[0] == "아이소 래터럴 로우"
    assert _names(_machine("뉴텍", "Torque High Row (T-HR)"))[0] == "하이 로우"
    assert _names(_machine("Nautilus", "Hack Squat"))[0] == "핵 스쿼트"
    assert _names(_machine("Nautilus", "Nitro Prone Leg Curl"))[0] == "레그 컬"
    assert _names(_machine("뉴텍", "Hammer Incline Bench Press (NT-03F)"))[0] == "인클라인 프레스 머신"


def test_spacing_and_model_code_do_not_break_matching():
    # "Lat Pulldown"(붙여 씀) ↔ 종목 "Lat Pulldown", 괄호 안 모델 코드 "(T-HR)"는 무시
    names = _names(_machine("Life Fitness", "Circuit Series Lat Pulldown"))
    assert {"랫풀다운", "머신 풀다운"} <= set(names[:2])
    assert "티바 로우" not in _names(_machine("뉴텍", "Torque High Row (T-HR)"))


def test_free_weight_and_bodyweight_variants_are_not_suggested_for_a_machine():
    names = _names(_machine("Nautilus", "Hack Squat"))
    assert names and not {"맨몸 스쿼트", "백스쿼트", "고블릿 스쿼트"} & set(names)
    # 다른 부위의 종목은 이름이 겹쳐도 나오지 않는다
    assert "레그 프레스 카프 레이즈" not in _names(_machine("Life Fitness", "Insignia Series Arc Leg Press"))


def test_multipurpose_equipment_suggests_by_equipment_tag():
    pulley = _machine("Life Fitness", "Dual Adjustable Pulley with Stabilization")
    assert pulley.target is None
    cable = suggest(pulley, LIBRARY)
    assert len(cable) == 8 and all("케이블" in BY_ID[i].tags for i in cable)

    smith = suggest(_machine("Panatta", "Freeweight HP Power Smith Machine Dual System Upper"), LIBRARY)
    assert smith and all("스미스머신" in BY_ID[i].tags for i in smith)

    rack = suggest(_machine("Arsenal Strength", "Alpha-11 Double Half Rack"), LIBRARY)
    assert rack and all("바벨" in BY_ID[i].tags for i in rack)


def test_usage_reorders_suggestions():
    pulley = _machine("Life Fitness", "Dual Adjustable Pulley with Stabilization")
    curl = next(e for e in LIBRARY if e.name_ko == "케이블 컬")
    boosted = [ExerciseInfo(**{**e.__dict__, "my_sets": 12}) if e.id == curl.id else e for e in LIBRARY]
    assert suggest(pulley, boosted)[0] == curl.id, "내가 자주 한 종목이 위로"

    row = _machine("Hammer Strength", "MTS Iso-Lateral Row")
    seated = next(e for e in LIBRARY if e.name_ko == "시티드 로우 머신")
    used = [ExerciseInfo(**{**e.__dict__, "others_used": True}) if e.id == seated.id else e for e in LIBRARY]
    assert suggest(row, used)[0] == seated.id, "누군가 이 머신으로 기록한 종목이 위로"


def test_suggest_is_deterministic_and_bounded():
    machine = _machine("Hammer Strength", "MTS Iso-Lateral Row")
    first = suggest(machine, LIBRARY)
    assert first == suggest(machine, list(reversed(LIBRARY))), "입력 순서와 무관"
    assert len(suggest(machine, LIBRARY, limit=3)) == 3
    assert all(score(machine, BY_ID[i]) >= MIN_SCORE for i in first)
    assert suggest(machine, []) == []


def test_most_catalog_machines_get_a_suggestion():
    """카탈로그 대부분에 추천이 붙는다 — 규칙을 고치다 통째로 망가뜨리면 여기서 잡힌다."""
    empty = [m for m in MACHINES if not suggest(_machine(m[0], m[1]), LIBRARY, limit=1)]
    assert len(empty) < len(MACHINES) * 0.05, f"추천 없는 머신 {len(empty)}/{len(MACHINES)}"
