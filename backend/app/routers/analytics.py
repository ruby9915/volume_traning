"""§11 고급 분석 — 데이터 준비도 게이트 뒤의 6개 엔드포인트.

전부 read-only SQL 온디맨드 (§6.1 원칙: 사전 집계·캐시 없음). 게이트(require_analytics_ready)는
라우터 수준 의존성이라 빠뜨릴 수 없다: 훈련 주 < ADVANCED_MIN_WEEKS 면
403 + detail.code = "insufficient_data" (프론트가 잠금 카드로 바꿔 보여 준다).

이것은 역할 권한(관리자/일반)이 아니라 사용자별 데이터 준비도 게이트다 — 관리자도 자기 데이터
기준으로 같은 규칙을 받는다. 4주 미만 데이터로는 이동평균·ACWR·빈도 평균이 잡음이라 막는다.
"""

import sqlite3
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CurrentUser, subject_user
from ..db import E1RM_EXPR, get_db
from ..schemas import (
    DATE_PATTERN,
    AttributionOut,
    AttributionPoint,
    BucketShare,
    FatigueOut,
    FatiguePoint,
    FrequencyOut,
    IntensityOut,
    MuscleWeekFrequency,
    RepMaxCell,
    RepMaxOut,
    RepPrEvent,
    TrendOut,
    TrendPoint,
)
from ..seed_data.targets import REGION_NAMES_KO
from .stats import (
    ADVANCED_MIN_WEEKS,
    TARGET_JOIN,
    WEEK_EXPR,
    _effective_today,
    _filters,
    training_weeks,
)

# §6.2-B v2 "방치 부위 감지(14일 무자극)"
NEGLECT_DAYS = 14
# §6.2-A v2 급성:만성 볼륨 비율 경고 임계
ACWR_WARN = 1.5
# §11.2 간접 세트 기본 가중치 (Baz-Valle 2021 fractional 방식의 0.5). 조회 파라미터로 바꿀 수 있다.
INDIRECT_WEIGHT_DEFAULT = 0.5
# rep-max 매트릭스 범위 — e1RM 유효 범위(§6.1 1≤reps≤12)와 같다
REP_MAX_RANGE = range(1, 13)
# 피로 곡선 최대 서수 — 그 이상은 세션 수가 적어 평균이 잡음
FATIGUE_MAX_ORDINAL = 10
REP_RANGE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("1-5", 1, 5), ("6-12", 6, 12), ("13-20", 13, 20), ("21+", 21, float("inf")),
)
INTENSITY_ZONES: tuple[tuple[str, float, float], ...] = (
    ("<60%", 0, 60), ("60-70%", 60, 70), ("70-80%", 70, 80), ("80-90%", 80, 90),
    ("90%+", 90, float("inf")),
)


def require_analytics_ready(
    user: CurrentUser = Depends(subject_user), db: sqlite3.Connection = Depends(get_db)
) -> CurrentUser:
    weeks = training_weeks(db, user.id)
    if weeks < ADVANCED_MIN_WEEKS:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_data",
                "weeks_of_data": weeks,
                "required_weeks": ADVANCED_MIN_WEEKS,
            },
        )
    return user


router = APIRouter(
    prefix="/api/stats/advanced",
    tags=["analytics"],
    dependencies=[Depends(require_analytics_ready)],
)


def _week_starts(weeks: int) -> tuple[date, date, list[date]]:
    """(오늘, 이번 주 월요일, 오래된 → 이번 주 순 week_start 목록)."""
    today = _effective_today()
    cur_ws = today - timedelta(days=today.weekday())
    return today, cur_ws, [cur_ws - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]


def _exercise_or_404(db: sqlite3.Connection, user: CurrentUser, exercise_id: int) -> sqlite3.Row:
    row = db.execute(
        "SELECT id, name_ko FROM exercise WHERE id = ? AND (user_id IS NULL OR user_id = ?)",
        (exercise_id, user.id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    return row


def _bucket_shares(
    values: list[float], buckets: tuple[tuple[str, float, float], ...], inclusive_hi: bool
) -> list[BucketShare]:
    """값 목록을 구간별 (개수, 비율)로. rep range는 양끝 포함(1-5·6-12), 강도 존은 [lo, hi)."""
    total = len(values)
    out = []
    for label, lo, hi in buckets:
        n = sum(1 for v in values if lo <= v and (v <= hi if inclusive_hi else v < hi))
        out.append(BucketShare(bucket=label, sets=n, share=round(n / total, 3) if total else 0.0))
    return out


# ---------- 1. 분할 실행 점검 — 부위·근육별 주간 세션 빈도 + 방치 부위 ----------

@router.get("/frequency", response_model=FrequencyOut)
def frequency(
    weeks: int = Query(default=8, ge=1, le=26),
    user: CurrentUser = Depends(subject_user),
    db: sqlite3.Connection = Depends(get_db),
) -> FrequencyOut:
    """근육(level 2)·부위마다 주별 '그 부위를 자극한 세션 수' (웜업 제외).
    분할표 없이(§10.0) 실제로 각 부위가 주 몇 회 자극됐는지를 보여 준다."""
    today, _cur_ws, starts = _week_starts(weeks)
    week_keys = [d.isoformat() for d in starts]
    since = week_keys[0]

    def counts(group: str) -> dict[tuple[str, str], int]:
        rows = db.execute(
            f"""
            SELECT {WEEK_EXPR} AS ws, {group} AS code, COUNT(DISTINCT sv.session_id) AS n
            FROM {TARGET_JOIN}
            WHERE sv.user_id = ? AND sv.is_warmup = 0 AND sv.date >= ?
            GROUP BY ws, code
            """,
            (user.id, since),
        ).fetchall()
        return {(r["ws"], r["code"]): r["n"] for r in rows}

    def last_dates(group: str) -> dict[str, str]:
        rows = db.execute(
            f"""
            SELECT {group} AS code, MAX(sv.date) AS d FROM {TARGET_JOIN}
            WHERE sv.user_id = ? AND sv.is_warmup = 0 GROUP BY code
            """,
            (user.id,),
        ).fetchall()
        return {r["code"]: r["d"] for r in rows}

    def build(code: str, name_ko: str, region: str, by_week: dict, last: dict) -> MuscleWeekFrequency:
        per_week = [by_week.get((ws, code), 0) for ws in week_keys]
        completed = per_week[:-1]  # 이번 주는 진행 중 — 평균에서 제외
        avg = round(sum(completed) / len(completed), 2) if completed else 0.0
        last_d = last.get(code)
        since_last = (today - date.fromisoformat(last_d)).days if last_d else None
        return MuscleWeekFrequency(
            code=code,
            name_ko=name_ko,
            region=region,
            per_week=per_week,
            avg_per_week=avg,
            days_since_last=since_last,
            neglected=since_last is not None and since_last >= NEGLECT_DAYS,
        )

    muscle_counts, muscle_last = counts("tp.muscle_code"), last_dates("tp.muscle_code")
    region_counts, region_last = counts("tp.region"), last_dates("tp.region")
    muscles = db.execute(
        "SELECT code, name_ko, region FROM muscle_group WHERE level = 2 ORDER BY sort_order, id"
    ).fetchall()
    return FrequencyOut(
        weeks=week_keys,
        neglect_days=NEGLECT_DAYS,
        regions=[
            build(r, REGION_NAMES_KO[r], r, region_counts, region_last) for r in REGION_NAMES_KO
        ],
        muscles=[
            build(m["code"], m["name_ko"], m["region"], muscle_counts, muscle_last) for m in muscles
        ],
    )


# ---------- 2. 볼륨 추세 — 주간 볼륨 + 4주 이동평균 + ACWR ----------

@router.get("/trend", response_model=TrendOut)
def trend(
    weeks: int = Query(default=16, ge=4, le=52),
    user: CurrentUser = Depends(subject_user),
    db: sqlite3.Connection = Depends(get_db),
) -> TrendOut:
    """ma4 = 이번 주 포함 4주 평균, acwr = 이번 주 / 직전 4주 평균 (§6.2-A v2).
    첫 훈련 주 이전은 0이 아니라 '데이터 없음'이라 그 구간이 걸리는 값은 null.
    진행 중인 이번 주의 acwr은 과소평가라 in_progress로 표시만 한다 (경고 판정은 프론트가 완료 주만)."""
    _today, cur_ws, shown = _week_starts(weeks)
    first_needed = shown[0] - timedelta(weeks=4)
    rows = db.execute(
        f"""
        SELECT {WEEK_EXPR} AS ws, SUM(sv.volume_kg) AS vol, COUNT(*) AS sets
        FROM set_volume sv
        WHERE sv.user_id = ? AND sv.is_warmup = 0 AND sv.date >= ?
        GROUP BY ws
        """,
        (user.id, first_needed.isoformat()),
    ).fetchall()
    by_week = {r["ws"]: (r["vol"], r["sets"]) for r in rows}
    first_key = db.execute(
        f"SELECT MIN({WEEK_EXPR}) FROM set_volume sv WHERE sv.user_id = ? AND sv.is_warmup = 0",
        (user.id,),
    ).fetchone()[0]
    first_week = date.fromisoformat(first_key) if first_key else None

    def vol(ws: date) -> float:
        return by_week.get(ws.isoformat(), (0.0, 0))[0]

    points = []
    for ws in shown:
        v, n = by_week.get(ws.isoformat(), (0.0, 0))
        ma4 = acwr = None
        if first_week is not None:
            if ws - timedelta(weeks=3) >= first_week:
                ma4 = round(sum(vol(ws - timedelta(weeks=i)) for i in range(4)) / 4, 2)
            if ws - timedelta(weeks=4) >= first_week:
                chronic = sum(vol(ws - timedelta(weeks=i)) for i in range(1, 5)) / 4
                if chronic > 0:
                    acwr = round(v / chronic, 2)
        points.append(
            TrendPoint(
                week_start=ws.isoformat(),
                volume_kg=round(v, 2),
                set_count=n,
                ma4_kg=ma4,
                acwr=acwr,
                in_progress=ws == cur_ws,
            )
        )
    return TrendOut(first_week=first_key, acwr_warn=ACWR_WARN, points=points)


# ---------- 3. rep-max 매트릭스 + Rep PR ----------

@router.get("/rep-max", response_model=RepMaxOut)
def rep_max(
    exercise_id: int = Query(),
    user: CurrentUser = Depends(subject_user),
    db: sqlite3.Connection = Depends(get_db),
) -> RepMaxOut:
    """횟수별 최고 중량 (정확히 그 횟수 / 그 횟수 이상), Rep PR = 같은 중량으로 이전 세션보다
    많은 횟수 (§6.2-D v2). PR 규칙은 §6.3 그대로: 그 중량의 첫 세션은 베이스라인, strictly greater,
    세션(날짜×종목×중량)당 1건. 웜업·weight 0 제외."""
    ex = _exercise_or_404(db, user, exercise_id)
    rows = db.execute(
        """
        SELECT sv.date AS date, sv.session_id AS session_id, sv.weight_kg AS weight_kg, sv.reps AS reps
        FROM set_volume sv
        WHERE sv.user_id = ? AND sv.exercise_id = ? AND sv.is_warmup = 0 AND sv.weight_kg > 0
        ORDER BY sv.date, sv.session_id, sv.set_id
        """,
        (user.id, exercise_id),
    ).fetchall()

    exact: dict[int, tuple[float, str]] = {}
    for r in rows:
        if r["reps"] in REP_MAX_RANGE:
            best = exact.get(r["reps"])
            if best is None or r["weight_kg"] > best[0]:
                exact[r["reps"]] = (r["weight_kg"], r["date"])
    cells = []
    for reps in REP_MAX_RANGE:
        at_least = [r["weight_kg"] for r in rows if r["reps"] >= reps]
        best = exact.get(reps)
        cells.append(
            RepMaxCell(
                reps=reps,
                best_weight_kg=best[0] if best else None,
                best_date=best[1] if best else None,
                implied_weight_kg=max(at_least) if at_least else None,
            )
        )

    # Rep PR — 세션 단위로 '중량별 최다 횟수'를 만든 뒤 이전 세션들의 최고와 비교
    sessions: dict[int, tuple[str, dict[float, int]]] = {}
    order: list[int] = []
    for r in rows:
        if r["session_id"] not in sessions:
            sessions[r["session_id"]] = (r["date"], {})
            order.append(r["session_id"])
        best_reps = sessions[r["session_id"]][1]
        best_reps[r["weight_kg"]] = max(best_reps.get(r["weight_kg"], 0), r["reps"])
    bests: dict[float, int] = {}
    events: list[RepPrEvent] = []
    for sid in order:
        day, session_best = sessions[sid]
        for w, reps in session_best.items():
            prev = bests.get(w)
            if prev is not None and reps > prev:
                events.append(RepPrEvent(date=day, weight_kg=w, reps=reps, prev_reps=prev))
            bests[w] = max(prev or 0, reps)
    events.sort(key=lambda e: (e.date, e.weight_kg), reverse=True)
    return RepMaxOut(exercise_id=ex["id"], name_ko=ex["name_ko"], cells=cells, rep_prs=events[:20])


# ---------- 4. 세트 내 피로 곡선 + rep range 분포 (종목별) ----------

@router.get("/fatigue", response_model=FatigueOut)
def fatigue(
    exercise_id: int = Query(),
    from_: str | None = Query(default=None, alias="from", pattern=DATE_PATTERN),
    to: str | None = Query(default=None, pattern=DATE_PATTERN),
    user: CurrentUser = Depends(subject_user),
    db: sqlite3.Connection = Depends(get_db),
) -> FatigueOut:
    """세션 안에서 그 종목의 n번째 워킹 세트가 평균 몇 회였는지 (1세트 대비 비율 포함).
    서수는 세션×종목 안에서 set_index 순으로 다시 매긴다 (set_index는 세션 전체 번호)."""
    ex = _exercise_or_404(db, user, exercise_id)
    where, params = _filters(user.id, from_, to, include_warmup=False)
    rows = db.execute(
        f"""
        SELECT sv.session_id AS session_id, sv.reps AS reps, sv.weight_kg AS weight_kg
        FROM set_volume sv JOIN workout_set ws ON ws.id = sv.set_id
        WHERE sv.exercise_id = ? AND {where}
        ORDER BY sv.session_id, ws.set_index
        """,
        [exercise_id, *params],
    ).fetchall()
    by_session: dict[int, list[sqlite3.Row]] = {}
    for r in rows:
        by_session.setdefault(r["session_id"], []).append(r)

    acc: dict[int, dict[str, float]] = {}
    for sets in by_session.values():
        first_reps = sets[0]["reps"]
        for ordinal, r in enumerate(sets[:FATIGUE_MAX_ORDINAL], start=1):
            a = acc.setdefault(ordinal, {"reps": 0.0, "weight": 0.0, "rel": 0.0, "n": 0})
            a["reps"] += r["reps"]
            a["weight"] += r["weight_kg"]
            a["rel"] += r["reps"] / first_reps
            a["n"] += 1
    points = [
        FatiguePoint(
            ordinal=o,
            sessions=int(a["n"]),
            avg_reps=round(a["reps"] / a["n"], 1),
            avg_weight_kg=round(a["weight"] / a["n"], 1),
            rel_reps=round(a["rel"] / a["n"], 2),
        )
        for o, a in sorted(acc.items())
    ]
    return FatigueOut(
        exercise_id=ex["id"],
        name_ko=ex["name_ko"],
        sessions_used=len(by_session),
        points=points,
        rep_ranges=_bucket_shares([r["reps"] for r in rows], REP_RANGE_BUCKETS, inclusive_hi=True),
    )


# ---------- 5. 강도 존 분포 (%e1RM) + rep range 분포 (전체·종목 선택) ----------

@router.get("/intensity", response_model=IntensityOut)
def intensity(
    exercise_id: int | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from", pattern=DATE_PATTERN),
    to: str | None = Query(default=None, pattern=DATE_PATTERN),
    user: CurrentUser = Depends(subject_user),
    db: sqlite3.Connection = Depends(get_db),
) -> IntensityOut:
    """세트 강도 = weight ÷ (그 시점까지 그 종목의 최고 e1RM) × 100. 러닝 최고치라 과거 세트를 지금
    실력으로 재평가하지 않는다. 그 세트 자신도 러닝 최고치에 먼저 반영 → 100% 초과 없음.
    e1RM 유효 세트가 아직 없는 종목의 세트(첫 세트가 reps>12 등)는 강도 대상에서 빠진다."""
    if exercise_id is not None:
        _exercise_or_404(db, user, exercise_id)
    ex_clause = "" if exercise_id is None else " AND sv.exercise_id = ?"
    params: list = [user.id] + ([] if exercise_id is None else [exercise_id])
    rows = db.execute(
        f"""
        SELECT sv.exercise_id AS exercise_id, sv.date AS date, sv.weight_kg AS weight_kg,
               sv.reps AS reps, {E1RM_EXPR} AS e1rm
        FROM set_volume sv
        WHERE sv.user_id = ? AND sv.is_warmup = 0{ex_clause}
        ORDER BY sv.exercise_id, sv.date, sv.session_id, sv.set_id
        """,
        params,
    ).fetchall()
    running: dict[int, float] = {}
    pcts: list[float] = []
    reps_in_range: list[float] = []
    for r in rows:
        in_range = (from_ is None or r["date"] >= from_) and (to is None or r["date"] <= to)
        if in_range:
            reps_in_range.append(r["reps"])
        if r["e1rm"] is not None:
            running[r["exercise_id"]] = max(running.get(r["exercise_id"], 0.0), r["e1rm"])
        top = running.get(r["exercise_id"])
        if in_range and r["weight_kg"] > 0 and top:
            pcts.append(r["weight_kg"] / top * 100)
    return IntensityOut(
        sets_total=len(pcts),
        avg_intensity_pct=round(sum(pcts) / len(pcts), 1) if pcts else None,
        zones=_bucket_shares(pcts, INTENSITY_ZONES, inclusive_hi=False),
        rep_ranges=_bucket_shares(reps_in_range, REP_RANGE_BUCKETS, inclusive_hi=True),
    )


# ---------- 6. 직접/간접 이중 집계 (fractional set counting) ----------

@router.get("/attribution", response_model=AttributionOut)
def attribution(
    from_: str | None = Query(default=None, alias="from", pattern=DATE_PATTERN),
    to: str | None = Query(default=None, pattern=DATE_PATTERN),
    include_warmup: bool = False,
    indirect_weight: float = Query(default=INDIRECT_WEIGHT_DEFAULT, ge=0, le=1),
    user: CurrentUser = Depends(subject_user),
    db: sqlite3.Connection = Depends(get_db),
) -> AttributionOut:
    """근육(level 2)별 직접 세트/볼륨(§10.2 정본, /stats/muscles와 동일) + 간접 세트/볼륨(set_indirect).
    fractional = direct + weight × indirect. 간접은 보조 데이터 — 총볼륨·PR에는 더하지 않는다."""
    where, params = _filters(user.id, from_, to, include_warmup)
    direct = {
        r["code"]: r
        for r in db.execute(
            f"""
            SELECT tp.muscle_code AS code, COUNT(*) AS sets, SUM(sv.volume_kg) AS vol
            FROM {TARGET_JOIN} WHERE {where} GROUP BY tp.muscle_code
            """,
            params,
        ).fetchall()
    }
    where_i, params_i = _filters(user.id, from_, to, include_warmup, alias="si")
    indirect = {
        r["code"]: r
        for r in db.execute(
            f"""
            SELECT si.muscle_code AS code, COUNT(*) AS sets, SUM(si.volume_kg) AS vol
            FROM set_indirect si WHERE {where_i} GROUP BY si.muscle_code
            """,
            params_i,
        ).fetchall()
    }
    muscles = db.execute(
        "SELECT code, name_ko, region FROM muscle_group WHERE level = 2 ORDER BY sort_order, id"
    ).fetchall()
    points = []
    for m in muscles:
        d, i = direct.get(m["code"]), indirect.get(m["code"])
        d_sets, d_vol = (d["sets"], d["vol"]) if d else (0, 0.0)
        i_sets, i_vol = (i["sets"], i["vol"]) if i else (0, 0.0)
        points.append(
            AttributionPoint(
                code=m["code"],
                name_ko=m["name_ko"],
                region=m["region"],
                direct_sets=d_sets,
                indirect_sets=i_sets,
                fractional_sets=round(d_sets + indirect_weight * i_sets, 2),
                direct_volume_kg=round(d_vol, 2),
                indirect_volume_kg=round(i_vol, 2),
                fractional_volume_kg=round(d_vol + indirect_weight * i_vol, 2),
            )
        )
    return AttributionOut(indirect_weight=indirect_weight, points=points)
