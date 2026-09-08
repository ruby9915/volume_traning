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

MuscleCode = Literal[
    "chest", "back", "lower_back", "shoulders", "biceps", "triceps",
    "forearms", "quads", "hamstrings", "glutes", "calves", "abs",
]
MuscleRole = Literal["primary", "secondary"]


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
# §3.6 속성값 — 자유 텍스트 (enum 없음), 빈 문자열 대신 null 사용
AttrValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
# 쉼표 구분 별칭 목록이라 더 길게 허용
AliasesValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- Auth ----------

class LoginRequest(StrictModel):
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------- Exercises ----------

class MuscleAssignment(StrictModel):
    code: MuscleCode
    role: MuscleRole


def _validate_muscles(muscles: list[MuscleAssignment]) -> list[MuscleAssignment]:
    codes = [m.code for m in muscles]
    if len(codes) != len(set(codes)):
        raise ValueError("같은 부위를 primary/secondary에 중복 지정할 수 없습니다")
    if not any(m.role == "primary" for m in muscles):
        raise ValueError("주동근(primary)을 1개 이상 지정해야 합니다")
    return muscles


class ExerciseAttrFields(StrictModel):
    """§3.6 속성 6필드 — 생성·수정 요청 공통. 전부 선택 사항이며 PATCH에서 null = 값 비우기."""

    base_movement: AttrValue | None = None
    equipment: AttrValue | None = None
    support: AttrValue | None = None
    grip: AttrValue | None = None
    angle: AttrValue | None = None
    aliases: AliasesValue | None = None


class ExerciseCreate(ExerciseAttrFields):
    name_ko: Name
    name_en: Name | None = None
    muscles: list[MuscleAssignment]
    bodyweight_factor: float = Field(default=0, ge=0, le=1)
    load_multiplier: float = Field(default=1, gt=0)
    note: str | None = None

    @field_validator("muscles")
    @classmethod
    def muscles_valid(cls, v: list[MuscleAssignment]) -> list[MuscleAssignment]:
        return _validate_muscles(v)


class ExerciseUpdate(ExerciseAttrFields):
    name_ko: Name | None = None
    name_en: Name | None = None
    muscles: list[MuscleAssignment] | None = None
    bodyweight_factor: float | None = Field(default=None, ge=0, le=1)
    load_multiplier: float | None = Field(default=None, gt=0)
    note: str | None = None
    is_archived: bool | None = None

    @field_validator("muscles")
    @classmethod
    def muscles_valid(cls, v: list[MuscleAssignment] | None) -> list[MuscleAssignment] | None:
        if v is None:
            return v
        return _validate_muscles(v)


class MuscleOut(BaseModel):
    code: str
    role: str


class ExerciseOut(BaseModel):
    id: int
    name_ko: str
    name_en: str | None = None
    bodyweight_factor: float
    load_multiplier: float
    is_builtin: bool
    is_archived: bool
    note: str | None = None
    muscles: list[MuscleOut]
    # §3.6 속성 — 속성은 분류용 메타데이터, 정체성은 행(exercise_id)
    base_movement: str | None = None
    equipment: str | None = None
    support: str | None = None
    grip: str | None = None
    angle: str | None = None
    aliases: str | None = None


class LastRecordSet(BaseModel):
    weight_kg: float
    reps: int
    is_warmup: bool


class LastRecordOut(BaseModel):
    session_id: int
    session_date: str
    sets: list[LastRecordSet]


# ---------- Sets ----------

class SetCreate(StrictModel):
    client_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    date: DateStr
    exercise_id: int
    weight_kg: Weight = 0
    reps: Reps
    is_warmup: bool = False
    new_session: bool = False
    # §3.7 기록 의도 주동근 — null = 종목 기본 매핑 (유효 code만 허용, 위반 422)
    intent_muscle: MuscleCode | None = None
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
    # §3.7 — 명시적 null = intent 해제 (종목 기본 매핑으로 복귀)
    intent_muscle: MuscleCode | None = None


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
    # §3.7 기록 의도 주동근 (null 가능)
    intent_muscle: str | None = None
    intent_muscle_ko: str | None = None


# ---------- Sessions ----------

class SessionSummary(BaseModel):
    id: int
    date: str
    note: str | None = None
    total_volume: float
    exercise_count: int
    set_count: int
    # 주부위: 가중 볼륨(primary 1.0 / secondary 0.5, 웜업 제외) 최대 region.
    # 유효 세트가 없으면 둘 다 null
    main_region: str | None = None
    main_region_ko: str | None = None


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
    # §3.7 기록 의도 주동근 (null 가능) — 세트 저장 응답(SetOut)과 동일 필드
    intent_muscle: str | None = None
    intent_muscle_ko: str | None = None


class SessionExerciseGroup(BaseModel):
    exercise_id: int
    name_ko: str
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
    code: str
    name_ko: str
    region: str
    weighted_sets: float


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


class StatsSummaryOut(BaseModel):
    this_week: ThisWeekCard
    weekly_sparkline: list[WeekVolumePoint]
    muscle_sets_this_week: list[MuscleSetCount]
    recent_prs: list[PrEvent]
    frequency: FrequencyStats
    totals: TotalStats


class VolumePoint(BaseModel):
    period: str
    total_volume: float
    per_muscle: dict[str, float]
    per_region: dict[str, float]


class StatsVolumeOut(BaseModel):
    granularity: Literal["day", "week", "month"]
    points: list[VolumePoint]


class MusclePoint(BaseModel):
    code: str
    name_ko: str
    region: str
    volume_kg: float
    set_count: float


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
