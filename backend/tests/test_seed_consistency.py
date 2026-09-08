"""시드 마스터 데이터(seed_exercises)와 API 스키마(schemas.MuscleCode)·region 상수의 정합성.

근육 code 목록이 Literal(422 검증)과 시드 INSERT 두 곳에 독립적으로 적혀 있어,
한쪽만 고치면 "유효한 code인데 DB에 없음"(intent 422 방어 코드 경로) 같은 불일치가 생긴다.
"""

from typing import get_args

from app.schemas import MuscleCode
from app.seed_exercises import (
    ATTR_BACKFILL,
    EXERCISES,
    MUSCLE_GROUPS,
    REGION_NAMES_KO,
    REGIONS,
)

SEED_CODES = {code for code, _, _, _ in MUSCLE_GROUPS}


def test_muscle_code_literal_matches_seed():
    assert set(get_args(MuscleCode)) == SEED_CODES


def test_regions_match_seed_and_are_ordered():
    assert {region for _, _, region, _ in MUSCLE_GROUPS} == set(REGIONS)
    assert list(REGION_NAMES_KO) == REGIONS  # tie-break 순서 = 이름표 순서


def test_seed_exercises_reference_valid_codes():
    names = [e[0] for e in EXERCISES]
    assert len(names) == len(set(names)) == 45  # §3.5 내장 45종, 동명 없음
    for name_ko, _, primary, secondary, bw, mult in EXERCISES:
        assert primary, name_ko  # primary 1개 이상 (§3.1)
        assert set(primary) <= SEED_CODES and set(secondary) <= SEED_CODES, name_ko
        assert not set(primary) & set(secondary), name_ko
        assert 0 <= bw <= 1 and mult > 0, name_ko


def test_attr_backfill_targets_exist_in_seed():
    assert set(ATTR_BACKFILL) <= {e[0] for e in EXERCISES}
