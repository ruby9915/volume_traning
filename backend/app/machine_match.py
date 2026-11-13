"""§15.4 머신 → 종목 추천. 처음 쓰는 머신을 골랐을 때 "이 머신으로 할 종목" 후보를 순위로 준다.

추천은 **후보 제시**일 뿐이다 — 사용자가 하나를 고르고, 고른 결과(세트의 머신)가 쌓이면
그 사용 이력이 추천보다 먼저 나온다(routers/catalog.machine_exercises의 `used`).
타겟·계수를 유도하지 않으므로 §3.6의 "속성 → 부위 자동 유도 금지"와 무관하다.

점수 = 이름 일치(영문 모델명 ↔ 종목 영문명이 주, 한글 별칭이 보조) + 참고 타겟 일치
     + 장비 종류 일치(머신·케이블·스미스·랙·벤치) + 사용 이력. 순수 함수라 DB 없이 테스트한다.
가중치는 2026-11-13 운영 카탈로그 1,735대에 돌려 보고 정했다(추천 없음 30대 — 리그·넥·그리퍼 등).
"""

import re
from dataclasses import dataclass

SUGGEST_LIMIT = 8
MIN_SCORE = 0.5
# 한 가지 동작용 머신: 1위 점수의 이 비율에 못 미치는 후보는 버린다.
# 이름이 잘 맞는 종목이 있으면 "같은 근육의 아무 머신 종목"을 숨기기 위해서다.
RELATIVE_CUT = 0.6

_EN_STOP = {"machine", "the", "and", "with", "of", "for"}
_KO_STOP = {"머신"}
# 여러 종목에 쓰는 장비: 이름의 키워드 → 그 장비로 하는 종목의 태그. 위에서부터 먼저 맞는 것 하나.
# (키워드, 종목 태그, 참고 타겟이 없는 머신에만 적용하는가)
_EQUIPMENT_CLASSES: tuple[tuple[tuple[str, ...], frozenset[str], bool], ...] = (
    (("smith", "스미스"), frozenset({"스미스머신"}), False),
    (
        ("pulley", "cable", "crossover", "cross over", "functional trainer", "풀리", "케이블", "크로스오버"),
        frozenset({"케이블"}),
        False,
    ),
    (
        ("jungle", "multi gym", "multi-gym", "multigym", "home gym", "multi-station", "multi station",
         "trainer", "정글", "멀티짐", "홈짐", "멀티스테이션", "트레이너"),
        frozenset({"케이블"}),
        True,
    ),
    (("rack", "cage", "랙", "케이지"), frozenset({"바벨"}), True),
    (("bench", "벤치"), frozenset({"바벨", "덤벨"}), True),
)
# 맨몸·프리웨이트를 올려 쓰는 기구(딥·친업 스테이션, 올림픽 벤치)는 프리웨이트 종목을 깎지 않는다
_STATION_WORDS = (
    "station", "스테이션", "dip", "딥", "chin", "친업", "pull up", "pull-up", "pullup", "풀업", "bench", "벤치",
)
_FREE_TAGS = frozenset({"덤벨", "바벨", "케틀벨", "밴드", "TRX", "EZ바", "트랩바", "스미스머신", "플레이트", "맨몸"})


@dataclass(frozen=True)
class MachineInfo:
    brand: str
    model: str
    name_ko: str
    target: str | None = None  # 참고 타겟 코드
    muscle: str | None = None  # 그 타겟의 근육(level 2) 코드
    region: str | None = None


@dataclass(frozen=True)
class ExerciseInfo:
    id: int
    name_ko: str
    name_en: str | None
    target: str
    muscle: str
    region: str
    tags: frozenset[str] = frozenset()
    aliases: tuple[str, ...] = ()
    my_sets: int = 0  # 내가 이 종목으로 기록한 세트 수 (동점 정리용)
    others_used: bool = False  # 누군가 이 머신으로 이 종목을 기록한 적이 있다


def _en_tokens(text: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", " ", text.lower())  # 괄호 안 모델 코드 "(T-HR)" 제거
    out = []
    for tok in re.split(r"[^a-z0-9]+", text):
        if len(tok) < 2 or tok.isdigit() or tok in _EN_STOP:
            continue
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]  # dips → dip, triceps → tricep (양쪽에 같은 규칙)
        out.append(tok)
    return out


def _ko_tokens(text: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", " ", text.lower())
    return [t for t in re.split(r"[^0-9a-z가-힣]+", text) if t and t not in _KO_STOP]


def _with_pairs(tokens: list[str]) -> set[str]:
    """토큰 + 이웃한 두 토큰을 붙인 것 — 띄어쓰기 차이("레그 컬"/"레그컬", "pull down"/"pulldown") 흡수."""
    return set(tokens) | {a + b for a, b in zip(tokens, tokens[1:])}


def _coverage(needle: list[str], hay: set[str]) -> tuple[float, int]:
    """needle 토큰 중 hay에 있는 비율과 개수. 이웃 토큰을 붙인 형태로 있어도 둘 다 맞은 것으로 센다."""
    if not needle:
        return 0.0, 0
    hit = [tok in hay for tok in needle]
    for i, (a, b) in enumerate(zip(needle, needle[1:])):
        if a + b in hay:
            hit[i] = hit[i + 1] = True
    n = sum(hit)
    return n / len(needle), n


class _Scorer:
    """머신 쪽 준비(토큰·장비 종류)를 한 번만 하고 종목마다 점수를 매긴다."""

    def __init__(self, machine: MachineInfo) -> None:
        self.machine = machine
        self.en = _with_pairs(_en_tokens(machine.model))
        self.ko = _with_pairs(_ko_tokens(machine.name_ko))
        haystack = f"{machine.model} {machine.name_ko}".lower()
        self.equipment = next(
            (
                tags
                for words, tags, targetless_only in _EQUIPMENT_CLASSES
                if any(w in haystack for w in words) and not (targetless_only and machine.target is not None)
            ),
            None,
        )
        self.station = any(w in haystack for w in _STATION_WORDS)

    def _text(self, ex: ExerciseInfo) -> tuple[float, int]:
        ko, ko_hits = max(
            (_coverage(_ko_tokens(name), self.ko) for name in (ex.name_ko, *ex.aliases)),
            key=lambda c: c[0],
        )
        ex_en = _en_tokens(ex.name_en or "")
        if ex_en and self.en:
            en, en_hits = _coverage(ex_en, self.en)
            return 0.7 * en + 0.3 * ko, en_hits
        return ko, ko_hits

    def score(self, ex: ExerciseInfo) -> float:
        machine = self.machine
        text, hits = self._text(ex)
        total = text + min(0.16, 0.04 * hits)  # 같은 비율이면 더 구체적인(긴) 이름이 위

        if machine.target is not None:
            if ex.target == machine.target:
                total += 0.35
            elif ex.muscle == machine.muscle:
                total += 0.3
            elif ex.region == machine.region:
                total += 0.1
            else:
                total -= 0.5

        if self.equipment is not None:
            total += 0.5 if ex.tags & self.equipment else -0.2
        elif machine.target is not None:  # 한 가지 동작용 머신
            if "머신" in ex.tags:
                total += 0.2
            elif ex.tags & _FREE_TAGS and not self.station:
                total -= 0.4

        if ex.others_used:
            total += 0.6
        return total + min(0.15, 0.01 * ex.my_sets)


def score(machine: MachineInfo, ex: ExerciseInfo) -> float:
    return _Scorer(machine).score(ex)


def suggest(machine: MachineInfo, exercises: list[ExerciseInfo], limit: int = SUGGEST_LIMIT) -> list[int]:
    """추천 종목 id — 점수 내림차순(동점은 이름순, 결정적).

    MIN_SCORE 미만은 버린다. 참고 타겟이 있는(한 가지 동작용) 머신은 1위의 RELATIVE_CUT 미만도 버린다 —
    여러 종목에 쓰는 장비(케이블·랙)는 이름이 맞는 종목이 드물어 내가 자주 한 종목 순으로 그대로 보여 준다.
    """
    scorer = _Scorer(machine)
    scored = sorted(((scorer.score(ex), ex) for ex in exercises), key=lambda p: (-p[0], p[1].name_ko))
    if not scored:
        return []
    cut = MIN_SCORE if machine.target is None else max(MIN_SCORE, scored[0][0] * RELATIVE_CUT)
    return [ex.id for s, ex in scored[:limit] if s >= cut]
