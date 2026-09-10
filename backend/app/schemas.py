from datetime import date as _date
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def _check_quarter_step(v: float) -> float:
    if (v * 4) % 1 != 0:
        raise ValueError("weight_kg는 0.25 kg 배수여야 합니다")
    return v


def _check_iso_date(v: str) -> str:
    _date.fromisoformat(v)
    return v


Weight = Annotated[float, Field(ge=0, le=500), AfterValidator(_check_quarter_step)]
Reps = Annotated[int, Field(ge=1, le=100)]
# 'YYYY-MM-DD' — body 필드(DateStr)와 stats의 from/to 쿼리 파라미터가 같은 패턴을 쓴다
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
DateStr = Annotated[
    str,
    StringConstraints(pattern=DATE_PATTERN),
    AfterValidator(_check_iso_date),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
# §10.3 계열(base_movement) — 자유 텍스트, 빈 문자열 대신 null
AttrValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
# 쉼표 구분 별칭 목록이라 더 길게 허용
AliasesValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# §10.2 타겟 코드 — 유효성은 DB(muscle_group.code)로 검증 (Literal 아님: 분류가 데이터)
TargetCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
# §10.1 계정
Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$"),
]
Password = Annotated[str, StringConstraints(min_length=4, max_length=128)]

MAX_TAGS = 20
MAX_TAG_LEN = 30
# §11.2 종목당 보조 근육 상한 — 관례상 2~3개, 여유 있게
MAX_SECONDARY = 5


def _clean_secondary(codes: list[str]) -> list[str]:
    out: list[str] = []
    for c in codes:
        c = c.strip()
        if c and c not in out:
            out.append(c)
    if len(out) > MAX_SECONDARY:
        raise ValueError(f"보조 근육은 {MAX_SECONDARY}개 이하여야 합니다")
    return out


def _clean_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for t in tags:
        t = t.strip()
        if not t:
            continue
        if len(t) > MAX_TAG_LEN:
            raise ValueError(f"태그는 {MAX_TAG_LEN}자 이하여야 합니다")
        if t not in out:
            out.append(t)
    if len(out) > MAX_TAGS:
        raise ValueError(f"태그는 {MAX_TAGS}개 이하여야 합니다")
    return out


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- Auth (§10.1) ----------

class RegisterRequest(StrictModel):
    username: Username
    password: Password
    display_name: Name | None = None


class LoginRequest(StrictModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PasswordChangeRequest(StrictModel):
    current_password: str
    new_password: Password


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    is_admin: bool
    created_at: str


# ---------- Targets / Machines (§10.2, §10.4) ----------

class TargetOut(BaseModel):
    code: str
    name_ko: str
    region: str
    level: int
    parent_code: str | None = None


class MachineCreate(StrictModel):
    brand: Name
    model: Name
    name_ko: Name | None = None
    target: TargetCode | None = None


class MachineOut(BaseModel):
    id: int
    brand: str
    model: str
    name_ko: str
    target: str | None = None


# ---------- Exercises (§10.3) ----------

class ExerciseCreate(StrictModel):
    name_ko: Name
    name_en: Name | None = None
    base_movement: AttrValue | None = None
    tags: list[str] = []
    default_target: TargetCode
    # §11.2 보조(협응) 근육 — 간접 볼륨 후보. 기본 타겟과 같은 코드는 422
    secondary_targets: list[TargetCode] = []
    machine_id: int | None = None
    bodyweight_factor: float = Field(default=0, ge=0, le=1)
    load_multiplier: float = Field(default=1, gt=0)
    note: str | None = None
    aliases: AliasesValue | None = None

    @field_validator("tags")
    @classmethod
    def tags_clean(cls, v: list[str]) -> list[str]:
        return _clean_tags(v)

    @field_validator("secondary_targets")
    @classmethod
    def secondary_clean(cls, v: list[str]) -> list[str]:
        return _clean_secondary(v)


class ExerciseUpdate(StrictModel):
    name_ko: Name | None = None
    name_en: Name | None = None
    base_movement: AttrValue | None = None
    tags: list[str] | None = None
    default_target: TargetCode | None = None
    secondary_targets: list[TargetCode] | None = None  # 빈 배열 = 전부 해제
    machine_id: int | None = None  # 명시적 null = 머신 해제
    bodyweight_factor: float | None = Field(default=None, ge=0, le=1)
    load_multiplier: float | None = Field(default=None, gt=0)
    note: str | None = None
    aliases: AliasesValue | None = None
    is_archived: bool | None = None

    @field_validator("tags")
    @classmethod
    def tags_clean(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean_tags(v)

    @field_validator("secondary_targets")
    @classmethod
    def secondary_clean(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean_secondary(v)


class ExerciseOut(BaseModel):
    id: int
    name_ko: str
    name_en: str | None = None
    base_movement: str | None = None
    tags: list[str]
    default_target: str
    default_target_ko: str
    secondary_targets: list[str]  # §11.2 보조 근육 코드 (정렬: 타겟 sort_order)
    secondary_targets_ko: list[str]
    machine_id: int | None = None
    machine_name: str | None = None
    bodyweight_factor: float
    load_multiplier: float
    is_builtin: bool
    is_archived: bool
    is_own: bool  # 내 커스텀 종목 (수정·삭제 가능). 내장은 관리자만
    note: str | None = None
    aliases: str | None = None


class LastRecordSet(BaseModel):
    weight_kg: float
    reps: int
    is_warmup: bool


class LastRecordOut(BaseModel):
    session_id: int
    session_date: str
    sets: list[LastRecordSet]


class FavoritesOut(BaseModel):
    exercise_ids: list[int]


class FavoritesReplace(StrictModel):
    exercise_ids: list[int]


# ---------- Sets ----------

class SetCreate(StrictModel):
    client_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    date: DateStr
    exercise_id: int
    weight_kg: Weight = 0
    reps: Reps
    is_warmup: bool = False
    new_session: bool = False
    # §10.2 세트 타겟 — 미지정/null = 종목 기본 타겟 (유효 code만, 위반 422)
    target: TargetCode | None = None
    # §3.7-B 세션 직접 귀속 — 지정 시 lazy 생성 생략, 세션 date와 body date
    # 불일치·세션 부재는 422
    session_id: int | None = None

    @model_validator(mode="after")
    def session_target_consistent(self) -> "SetCreate":
        if self.session_id is not None and self.new_session:
            raise ValueError("session_id와 new_session=true는 함께 쓸 수 없습니다")
        return self


class SetUpdate(StrictModel):
    weight_kg: Weight | None = None
    reps: Reps | None = None
    is_warmup: bool | None = None
    # §10.2 — 명시적 null = 종목 기본 타겟으로 되돌리기
    target: TargetCode | None = None


class SetOut(BaseModel):
    id: int
    client_id: str | None = None
    session_id: int
    exercise_id: int
    set_index: int
    weight_kg: float
    reps: int
    is_warmup: bool
    note: str | None = None
    created_at: str
    volume_kg: float
    is_weight_pr: bool = False
    is_e1rm_pr: bool = False
    # §10.2 세트 타겟 (항상 존재)
    target: str
    target_ko: str


# ---------- Sessions ----------

class SessionSummary(BaseModel):
    id: int
    date: str
    note: str | None = None
    total_volume: float
    exercise_count: int
    set_count: int
    # §10.2 부위 라벨: 세트 타겟을 부위(region)로 합산해 1위(+2위가 25% 이상이면 함께).
    # main_region = 1위 코드, region_label = "하체·등" 형태. 유효 세트가 없으면 전부 null
    main_region: str | None = None
    main_region_ko: str | None = None
    region_label: str | None = None


class SessionSetOut(BaseModel):
    id: int
    client_id: str | None = None
    set_index: int
    weight_kg: float
    reps: int
    is_warmup: bool
    volume_kg: float
    note: str | None = None
    created_at: str
    target: str
    target_ko: str


class SessionExerciseGroup(BaseModel):
    exercise_id: int
    name_ko: str
    default_target: str
    sets: list[SessionSetOut]


class SessionDetail(SessionSummary):
    created_at: str
    exercises: list[SessionExerciseGroup]


class SessionUpdate(StrictModel):
    date: DateStr | None = None
    note: str | None = None

    @field_validator("date")
    @classmethod
    def date_not_null(cls, v: str | None) -> str:
        if v is None:  # NOT NULL 컬럼 — 명시적 null은 422 (§4.3)
            raise ValueError("date는 null일 수 없습니다")
        return v


# ---------- Bodyweight ----------

class BodyWeightUpsert(StrictModel):
    date: DateStr
    weight_kg: float = Field(gt=0, le=500)


class BodyWeightOut(BaseModel):
    id: int
    date: str
    weight_kg: float


# ---------- Stats ----------

class WeekVolumePoint(BaseModel):
    week_start: str
    volume_kg: float


class ThisWeekCard(BaseModel):
    week_start: str
    volume_kg: float
    prev_volume_kg: float
    change_pct: float | None = None
    in_progress: bool
    session_count: int
    set_count: int
    pr_count: int


class MuscleSetCount(BaseModel):
    """근육(level 2) 단위 세트 수 — 세부 타겟은 근육으로 합산."""

    code: str
    name_ko: str
    region: str
    set_count: int


class PrEvent(BaseModel):
    date: str
    exercise_id: int
    exercise_name_ko: str
    kind: Literal["weight", "e1rm"]
    value: float
    weight_kg: float
    reps: int


class FrequencyStats(BaseModel):
    days_this_week: int
    weekly_streak: int
    days_since_last: int | None = None


class TotalStats(BaseModel):
    tonnage_kg: float
    session_count: int
    set_count: int
    rep_count: int


class AnalyticsGate(BaseModel):
    """§11.1 고급 분석 데이터 준비도 — 훈련 주(웜업 아닌 세트가 있는 ISO 주) 수 기준."""

    ready: bool
    weeks_of_data: int
    required_weeks: int


class StatsSummaryOut(BaseModel):
    this_week: ThisWeekCard
    weekly_sparkline: list[WeekVolumePoint]
    muscle_sets_this_week: list[MuscleSetCount]
    recent_prs: list[PrEvent]
    frequency: FrequencyStats
    totals: TotalStats
    analytics: AnalyticsGate


class VolumePoint(BaseModel):
    period: str
    total_volume: float
    per_muscle: dict[str, float]  # 근육(level 2) 코드 → 볼륨 (세부는 근육으로 합산)
    per_region: dict[str, float]


class StatsVolumeOut(BaseModel):
    granularity: Literal["day", "week", "month"]
    points: list[VolumePoint]


class MusclePoint(BaseModel):
    """타겟 행 전부(level 2·3). level 2 값은 자기 + 세부 합산, level 3은 자기만."""

    code: str
    name_ko: str
    region: str
    level: int
    parent_code: str | None = None
    volume_kg: float
    set_count: int


class StatsMusclesOut(BaseModel):
    points: list[MusclePoint]


class ExercisePoint(BaseModel):
    date: str
    session_id: int
    volume_kg: float
    top_weight_kg: float
    e1rm: float | None = None


class PrRecord(BaseModel):
    value: float
    date: str
    weight_kg: float
    reps: int


class StatsExerciseOut(BaseModel):
    exercise_id: int
    name_ko: str
    points: list[ExercisePoint]
    weight_pr: PrRecord | None = None
    e1rm_pr: PrRecord | None = None


class ExercisePrRow(BaseModel):
    exercise_id: int
    name_ko: str
    weight_pr: PrRecord | None = None
    e1rm_pr: PrRecord | None = None


class StatsPrsOut(BaseModel):
    records: list[ExercisePrRow]
    feed: list[PrEvent]


class FamilyExercise(BaseModel):
    id: int
    name_ko: str


class FamilyPoint(BaseModel):
    date: str
    total_volume: float
    top_e1rm: float | None = None


class StatsFamilyOut(BaseModel):
    base_movement: str
    exercises: list[FamilyExercise]
    points: list[FamilyPoint]


class CalendarPoint(BaseModel):
    date: str
    volume_kg: float
    session_count: int


class StatsCalendarOut(BaseModel):
    points: list[CalendarPoint]


# ---------- Advanced analytics (§11) ----------

class MuscleWeekFrequency(BaseModel):
    """근육(level 2) 또는 부위의 주별 세션 수 + 마지막 자극 경과일."""

    code: str
    name_ko: str
    region: str
    per_week: list[int]  # weeks 순서(오래된 → 이번 주)와 같은 길이
    avg_per_week: float  # 이번 주(진행 중) 제외 평균
    days_since_last: int | None = None  # 한 번도 없으면 null
    neglected: bool  # 자극한 적 있고 NEGLECT_DAYS 이상 지남


class FrequencyOut(BaseModel):
    weeks: list[str]  # week_start (월요일) 오래된 → 이번 주
    neglect_days: int
    regions: list[MuscleWeekFrequency]
    muscles: list[MuscleWeekFrequency]


class TrendPoint(BaseModel):
    week_start: str
    volume_kg: float
    set_count: int
    ma4_kg: float | None = None  # 이번 주 포함 4주 이동평균 (첫 훈련 주부터 4주 미만이면 null)
    acwr: float | None = None  # 이번 주 / 직전 4주 평균 (직전 4주가 없거나 0이면 null)
    in_progress: bool


class TrendOut(BaseModel):
    first_week: str | None = None
    acwr_warn: float
    points: list[TrendPoint]


class RepMaxCell(BaseModel):
    reps: int
    best_weight_kg: float | None = None  # 정확히 그 횟수로 든 최고 중량
    best_date: str | None = None
    implied_weight_kg: float | None = None  # 그 횟수 이상으로 든 최고 중량 (단조 감소)


class RepPrEvent(BaseModel):
    date: str
    weight_kg: float
    reps: int
    prev_reps: int


class RepMaxOut(BaseModel):
    exercise_id: int
    name_ko: str
    cells: list[RepMaxCell]
    rep_prs: list[RepPrEvent]  # 최신순


class FatiguePoint(BaseModel):
    ordinal: int  # 세션 내 그 종목의 n번째 워킹 세트
    sessions: int  # 이 서수까지 간 세션 수
    avg_reps: float
    avg_weight_kg: float
    rel_reps: float | None = None  # 1세트 대비 횟수 비율 평균 (1세트는 1.0)


class BucketShare(BaseModel):
    bucket: str
    sets: int
    share: float  # 0~1


class FatigueOut(BaseModel):
    exercise_id: int
    name_ko: str
    sessions_used: int
    points: list[FatiguePoint]
    rep_ranges: list[BucketShare]


class IntensityOut(BaseModel):
    sets_total: int  # 강도 계산 대상 세트 (weight>0, 웜업 제외, 러닝 e1RM 존재)
    avg_intensity_pct: float | None = None
    zones: list[BucketShare]
    rep_ranges: list[BucketShare]  # 워킹 세트 전체(weight 0 포함)


class AttributionPoint(BaseModel):
    code: str
    name_ko: str
    region: str
    direct_sets: int
    indirect_sets: int  # 가중 전 세트 수
    fractional_sets: float  # direct + weight × indirect
    direct_volume_kg: float
    indirect_volume_kg: float  # 가중 전
    fractional_volume_kg: float


class AttributionOut(BaseModel):
    indirect_weight: float
    points: list[AttributionPoint]


# ---------- Admin (§10.5) ----------

class AdminUserOut(BaseModel):
    id: int
    username: str
    display_name: str
    is_admin: bool
    created_at: str
    session_count: int
    set_count: int
    last_date: str | None = None
