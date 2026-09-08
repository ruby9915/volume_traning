import csv
import io
import os
import shutil
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

from ..db import E1RM_EXPR, get_db
from ..schemas import (
    DATE_PATTERN,
    CalendarPoint,
    ExercisePoint,
    ExercisePrRow,
    FamilyExercise,
    FamilyPoint,
    FrequencyStats,
    MusclePoint,
    MuscleSetCount,
    PrEvent,
    PrRecord,
    StatsCalendarOut,
    StatsExerciseOut,
    StatsFamilyOut,
    StatsMusclesOut,
    StatsPrsOut,
    StatsSummaryOut,
    StatsVolumeOut,
    ThisWeekCard,
    TotalStats,
    VolumePoint,
    WeekVolumePoint,
)
from ..seed_exercises import REGIONS

router = APIRouter(prefix="/api", tags=["stats"])

# §6.1 ISO 월요일 시작 주 — 집계 키는 그 주 월요일 날짜
WEEK_EXPR = (
    "DATE(sv.date, '-' || ((CAST(STRFTIME('%w', sv.date) AS INTEGER) + 6) % 7)"
    " || ' days')"
)
# §3.7 부위 귀속 (§6.1의 확장, 단일 규칙) — 세트×근육 전개 파생 테이블.
# intent NULL 세트: 종목 매핑 primary 1.0 / secondary 0.5 (기존 규칙 그대로).
# intent 지정 세트: intent 근육 1.0 + 그 종목 매핑의 나머지 근육 전부
#   (원래 primary 포함, intent 제외) 0.5. intent가 매핑에 없는 근육이어도 허용.
# 별칭을 sv로 유지해 기존 _filters(sv.date/sv.is_warmup)·WEEK_EXPR과 그대로 호환.
MUSCLE_ATTRIB = """(
    SELECT sv.date AS date, sv.is_warmup AS is_warmup,
           sv.volume_kg AS volume_kg,
           em.muscle_group_id AS muscle_group_id,
           CASE WHEN sv.intent_muscle_group_id IS NULL
                THEN CASE em.role WHEN 'primary' THEN 1.0 ELSE 0.5 END
                ELSE 0.5 END AS w
    FROM set_volume sv
    JOIN exercise_muscle em ON em.exercise_id = sv.exercise_id
    WHERE sv.intent_muscle_group_id IS NULL
       OR em.muscle_group_id != sv.intent_muscle_group_id
    UNION ALL
    SELECT sv.date, sv.is_warmup, sv.volume_kg, sv.intent_muscle_group_id, 1.0
    FROM set_volume sv
    WHERE sv.intent_muscle_group_id IS NOT NULL
)"""


def _effective_today() -> date:
    # 하루 경계 03:00 (§5.3·§6.1)
    return (datetime.now() - timedelta(hours=3)).date()


def _filters(
    from_: str | None, to: str | None, include_warmup: bool
) -> tuple[str, list]:
    clauses, params = [], []
    if not include_warmup:
        clauses.append("sv.is_warmup = 0")
    if from_:
        clauses.append("sv.date >= ?")
        params.append(from_)
    if to:
        clauses.append("sv.date <= ?")
        params.append(to)
    return " AND ".join(clauses) or "1=1", params


def _muscle_meta(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT code, name_ko, region FROM muscle_group ORDER BY sort_order"
    ).fetchall()


def _best_set(sets: list[sqlite3.Row], column: str) -> sqlite3.Row | None:
    """그 세션에서 해당 지표를 처음 달성한 세트 (동률이면 기록 순 앞선 것).
    집계 MAX와 동일한 행 집합·동일 식이므로 값은 SQL 결과와 정확히 일치한다."""
    best = None
    for row in sets:
        value = row[column]
        if value is None:
            continue
        if best is None or value > best[column]:
            best = row
    return best


def _pr_events(
    db: sqlite3.Connection, exercise_id: int | None = None
) -> tuple[list[dict], dict[int, dict]]:
    """§6.3: on-the-fly, strictly greater, 종목의 첫 세션은 베이스라인,
    PR 히스토리는 하루×종목×종류당 최고 1건. weight=0·웜업 세트 제외."""
    where = "sv.is_warmup = 0 AND sv.weight_kg > 0"
    params: list = []
    if exercise_id is not None:
        where += " AND sv.exercise_id = ?"
        params.append(exercise_id)
    rows = db.execute(
        f"""
        SELECT sv.exercise_id AS exercise_id, e.name_ko AS name_ko,
               sv.date AS date, sv.session_id AS session_id,
               MAX(sv.weight_kg) AS best_weight,
               MAX({E1RM_EXPR}) AS best_e1rm
        FROM set_volume sv
        JOIN exercise e ON e.id = sv.exercise_id
        WHERE {where}
        GROUP BY sv.exercise_id, sv.session_id
        ORDER BY sv.exercise_id, sv.date, sv.session_id
        """,
        params,
    ).fetchall()

    # PR을 만든 세트의 실제 중량·횟수를 함께 싣기 위한 세트 단위 조회 (집계는 위 쿼리 그대로)
    detail_rows = db.execute(
        f"""
        SELECT sv.exercise_id AS exercise_id, sv.session_id AS session_id,
               sv.weight_kg AS weight_kg, sv.reps AS reps,
               {E1RM_EXPR} AS e1rm
        FROM set_volume sv
        WHERE {where}
        ORDER BY sv.set_id
        """,
        params,
    ).fetchall()
    sets_by_session: dict[tuple[int, int], list[sqlite3.Row]] = {}
    for row in detail_rows:
        sets_by_session.setdefault(
            (row["exercise_id"], row["session_id"]), []
        ).append(row)

    # 세션 순으로 갱신 판정 후 하루×종목×종류 1건으로 축약 (값은 단조 증가 → 뒤가 그날 최고)
    by_day: dict[tuple[int, str, str], dict] = {}
    bests: dict[int, dict] = {}
    for row in rows:
        ex = bests.setdefault(
            row["exercise_id"],
            {"name_ko": row["name_ko"], "weight": None, "e1rm": None},
        )
        sets = sets_by_session.get((row["exercise_id"], row["session_id"]), [])
        for kind, value, column in (
            ("weight", row["best_weight"], "weight_kg"),
            ("e1rm", row["best_e1rm"], "e1rm"),
        ):
            if value is None:
                continue
            src = _best_set(sets, column)
            detail = (src["weight_kg"], src["reps"]) if src is not None else (value, 0)
            best = ex[kind]
            if best is None:
                # 첫 세션 = 베이스라인 — PR 아님
                ex[kind] = (value, row["date"], *detail)
            elif value > best[0]:
                ex[kind] = (value, row["date"], *detail)
                by_day[(row["exercise_id"], row["date"], kind)] = {
                    "exercise_id": row["exercise_id"],
                    "name_ko": row["name_ko"],
                    "kind": kind,
                    "value": value,
                    "date": row["date"],
                    "weight_kg": detail[0],
                    "reps": detail[1],
                }
    return list(by_day.values()), bests


def _pr_record(best: tuple | None) -> PrRecord | None:
    if best is None:
        return None
    value, pr_date, weight_kg, reps = best
    return PrRecord(
        value=round(value, 2), date=pr_date, weight_kg=weight_kg, reps=reps
    )


def _feed(events: list[dict], limit: int) -> list[PrEvent]:
    ordered = sorted(
        events, key=lambda e: (e["date"], e["exercise_id"], e["kind"]), reverse=True
    )
    return [
        PrEvent(
            date=e["date"],
            exercise_id=e["exercise_id"],
            exercise_name_ko=e["name_ko"],
            kind=e["kind"],
            value=round(e["value"], 2),
            weight_kg=e["weight_kg"],
            reps=e["reps"],
        )
        for e in ordered[:limit]
    ]


def _week_volumes(
    db: sqlite3.Connection, cur_ws: date
) -> tuple[float, float, list[WeekVolumePoint]]:
    """(이번 주 볼륨, 전주 볼륨, 최근 8주 스파크라인) — 웜업 제외."""
    weeks = [cur_ws - timedelta(weeks=i) for i in range(7, -1, -1)]
    rows = db.execute(
        f"""
        SELECT {WEEK_EXPR} AS ws, SUM(sv.volume_kg) AS vol
        FROM set_volume sv
        WHERE sv.is_warmup = 0 AND sv.date >= ?
        GROUP BY ws
        """,
        (weeks[0].isoformat(),),
    ).fetchall()
    by_week = {r["ws"]: r["vol"] for r in rows}
    sparkline = [
        WeekVolumePoint(
            week_start=w.isoformat(),
            volume_kg=round(by_week.get(w.isoformat(), 0.0), 2),
        )
        for w in weeks
    ]
    cur_vol = by_week.get(cur_ws.isoformat(), 0.0)
    prev_vol = by_week.get((cur_ws - timedelta(weeks=1)).isoformat(), 0.0)
    return cur_vol, prev_vol, sparkline


def _muscle_sets_since(db: sqlite3.Connection, since: str) -> list[MuscleSetCount]:
    """부위별 가중 세트 수 (§3.7 MUSCLE_ATTRIB 단일 규칙, 웜업 제외), 많은 순."""
    rows = db.execute(
        f"""
        SELECT mg.code AS code, mg.name_ko AS name_ko, mg.region AS region,
               SUM(sv.w) AS weighted_sets
        FROM {MUSCLE_ATTRIB} sv
        JOIN muscle_group mg ON mg.id = sv.muscle_group_id
        WHERE sv.is_warmup = 0 AND sv.date >= ?
        GROUP BY mg.code
        ORDER BY weighted_sets DESC
        """,
        (since,),
    ).fetchall()
    return [
        MuscleSetCount(
            code=r["code"], name_ko=r["name_ko"], region=r["region"],
            weighted_sets=round(r["weighted_sets"], 1),
        )
        for r in rows
    ]


def _frequency(db: sqlite3.Connection, today: date, cur_ws: date) -> FrequencyStats:
    """주 운동일수·weekly streak·마지막 운동 후 경과일 (§6.2-E).
    운동일 = 웜업 아닌 세트가 있는 날 — 웜업 전용일은 운동일이 아니다."""
    dates = [
        r["d"]
        for r in db.execute(
            "SELECT DISTINCT sv.date AS d FROM set_volume sv WHERE sv.is_warmup = 0"
        ).fetchall()
    ]
    days_this_week = sum(1 for d in dates if d >= cur_ws.isoformat())
    week_set = {
        (date.fromisoformat(d) - timedelta(days=date.fromisoformat(d).weekday())).isoformat()
        for d in dates
    }
    # 이번 주에 아직 운동이 없어도 streak는 끊기지 않는다 — 전주부터 거꾸로 센다
    streak = 0
    cursor = cur_ws if cur_ws.isoformat() in week_set else cur_ws - timedelta(weeks=1)
    while cursor.isoformat() in week_set:
        streak += 1
        cursor -= timedelta(weeks=1)
    days_since_last = (today - date.fromisoformat(max(dates))).days if dates else None
    return FrequencyStats(
        days_this_week=days_this_week,
        weekly_streak=streak,
        days_since_last=days_since_last,
    )


def _totals(db: sqlite3.Connection) -> TotalStats:
    """누적 tonnage·세션·세트·reps — §6.1 기본 집계 대상(웜업 제외)과 동일 기준이라
    웜업 전용 세션·빈 세션은 세션 수에서 빠진다."""
    row = db.execute(
        """
        SELECT COALESCE(SUM(sv.volume_kg), 0) AS tonnage,
               COUNT(DISTINCT sv.session_id) AS sessions,
               COUNT(*) AS sets, COALESCE(SUM(sv.reps), 0) AS reps
        FROM set_volume sv WHERE sv.is_warmup = 0
        """
    ).fetchone()
    return TotalStats(
        tonnage_kg=round(row["tonnage"], 2),
        session_count=row["sessions"],
        set_count=row["sets"],
        rep_count=row["reps"],
    )


@router.get("/stats/summary", response_model=StatsSummaryOut)
def stats_summary(db: sqlite3.Connection = Depends(get_db)) -> StatsSummaryOut:
    today = _effective_today()
    cur_ws = today - timedelta(days=today.weekday())
    week_start = cur_ws.isoformat()

    cur_vol, prev_vol, sparkline = _week_volumes(db, cur_ws)
    change_pct = round((cur_vol - prev_vol) / prev_vol * 100, 1) if prev_vol > 0 else None

    events, _ = _pr_events(db)

    # 이번 주 세션·세트 수 — muscle_sets·days_this_week와 같은 기준(웜업 제외, 주 시작 이후)
    week_row = db.execute(
        """
        SELECT COUNT(DISTINCT sv.session_id) AS sessions, COUNT(*) AS sets
        FROM set_volume sv WHERE sv.is_warmup = 0 AND sv.date >= ?
        """,
        (week_start,),
    ).fetchone()

    return StatsSummaryOut(
        this_week=ThisWeekCard(
            week_start=week_start,
            volume_kg=round(cur_vol, 2),
            prev_volume_kg=round(prev_vol, 2),
            change_pct=change_pct,
            in_progress=True,  # 현재 주는 항상 진행 중
            session_count=week_row["sessions"],
            set_count=week_row["sets"],
            pr_count=sum(1 for e in events if e["date"] >= week_start),
        ),
        weekly_sparkline=sparkline,
        muscle_sets_this_week=_muscle_sets_since(db, week_start),
        recent_prs=_feed(events, 3),
        frequency=_frequency(db, today, cur_ws),
        totals=_totals(db),
    )


@router.get("/stats/volume", response_model=StatsVolumeOut)
def stats_volume(
    granularity: Literal["day", "week", "month"] = "week",
    from_: str | None = Query(default=None, alias="from", pattern=DATE_PATTERN),
    to: str | None = Query(default=None, pattern=DATE_PATTERN),
    include_warmup: bool = False,
    db: sqlite3.Connection = Depends(get_db),
) -> StatsVolumeOut:
    period_expr = {
        "day": "sv.date",
        "week": WEEK_EXPR,
        "month": "STRFTIME('%Y-%m', sv.date)",
    }[granularity]
    where, params = _filters(from_, to, include_warmup)

    total_rows = db.execute(
        f"""
        SELECT {period_expr} AS period, SUM(sv.volume_kg) AS vol
        FROM set_volume sv WHERE {where}
        GROUP BY period ORDER BY period
        """,
        params,
    ).fetchall()
    muscle_rows = db.execute(
        f"""
        SELECT {period_expr} AS period, mg.code AS code, mg.region AS region,
               SUM(sv.volume_kg * sv.w) AS vol
        FROM {MUSCLE_ATTRIB} sv
        JOIN muscle_group mg ON mg.id = sv.muscle_group_id
        WHERE {where}
        GROUP BY period, mg.code
        """,
        params,
    ).fetchall()

    meta = _muscle_meta(db)
    points: dict[str, VolumePoint] = {}
    for r in total_rows:
        points[r["period"]] = VolumePoint(
            period=r["period"],
            total_volume=round(r["vol"], 2),
            per_muscle={m["code"]: 0.0 for m in meta},
            per_region={region: 0.0 for region in REGIONS},
        )
    for r in muscle_rows:
        point = points.get(r["period"])
        if point is None:
            continue
        vol = round(r["vol"], 2)
        point.per_muscle[r["code"]] = vol
        point.per_region[r["region"]] = round(point.per_region[r["region"]] + vol, 2)

    return StatsVolumeOut(granularity=granularity, points=list(points.values()))


@router.get("/stats/muscles", response_model=StatsMusclesOut)
def stats_muscles(
    from_: str | None = Query(default=None, alias="from", pattern=DATE_PATTERN),
    to: str | None = Query(default=None, pattern=DATE_PATTERN),
    include_warmup: bool = False,
    db: sqlite3.Connection = Depends(get_db),
) -> StatsMusclesOut:
    where, params = _filters(from_, to, include_warmup)
    rows = db.execute(
        f"""
        SELECT mg.code AS code,
               SUM(sv.volume_kg * sv.w) AS vol,
               SUM(sv.w) AS sets
        FROM {MUSCLE_ATTRIB} sv
        JOIN muscle_group mg ON mg.id = sv.muscle_group_id
        WHERE {where}
        GROUP BY mg.code
        """,
        params,
    ).fetchall()
    by_code = {r["code"]: r for r in rows}
    points = [
        MusclePoint(
            code=m["code"],
            name_ko=m["name_ko"],
            region=m["region"],
            volume_kg=round(by_code[m["code"]]["vol"], 2) if m["code"] in by_code else 0.0,
            set_count=round(by_code[m["code"]]["sets"], 1) if m["code"] in by_code else 0.0,
        )
        for m in _muscle_meta(db)
    ]
    return StatsMusclesOut(points=points)


@router.get("/stats/exercises/{exercise_id}", response_model=StatsExerciseOut)
def stats_exercise(
    exercise_id: int,
    from_: str | None = Query(default=None, alias="from", pattern=DATE_PATTERN),
    to: str | None = Query(default=None, pattern=DATE_PATTERN),
    include_warmup: bool = False,
    db: sqlite3.Connection = Depends(get_db),
) -> StatsExerciseOut:
    exercise = db.execute(
        "SELECT id, name_ko FROM exercise WHERE id = ?", (exercise_id,)
    ).fetchone()
    if exercise is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    where, params = _filters(from_, to, include_warmup)
    rows = db.execute(
        f"""
        SELECT sv.session_id AS session_id, MIN(sv.date) AS date,
               SUM(sv.volume_kg) AS vol,
               MAX(sv.weight_kg) AS top_weight,
               MAX({E1RM_EXPR}) AS e1rm
        FROM set_volume sv
        WHERE sv.exercise_id = ? AND {where}
        GROUP BY sv.session_id
        ORDER BY date, sv.session_id
        """,
        [exercise_id, *params],
    ).fetchall()
    points = [
        ExercisePoint(
            date=r["date"],
            session_id=r["session_id"],
            volume_kg=round(r["vol"], 2),
            top_weight_kg=r["top_weight"],
            e1rm=round(r["e1rm"], 2) if r["e1rm"] is not None else None,
        )
        for r in rows
    ]

    _, bests = _pr_events(db, exercise_id=exercise_id)
    best = bests.get(exercise_id) or {}

    return StatsExerciseOut(
        exercise_id=exercise_id,
        name_ko=exercise["name_ko"],
        points=points,
        weight_pr=_pr_record(best.get("weight")),
        e1rm_pr=_pr_record(best.get("e1rm")),
    )


@router.get("/stats/family", response_model=StatsFamilyOut)
def stats_family(
    base_movement: str = Query(min_length=1, max_length=50),
    db: sqlite3.Connection = Depends(get_db),
) -> StatsFamilyOut:
    """§3.6 계열 합산 — 같은 base_movement 종목들의 날짜별 합산 볼륨 + 최고 e1RM.

    분해로 갈라진 기록을 합쳐 보는 창구. PR·정체성은 여전히 exercise_id 기준이며,
    이 응답은 집계 뷰일 뿐이다. 웜업 제외, e1RM 규칙은 §6.1 그대로.

    참여 종목 명부(exercises)는 활성만, 볼륨 합산(points)은 아카이브 종목의
    과거 세트도 포함한다 — 분해 후 옛 통합 종목을 아카이브하는 전형적 경로에서
    그 과거 볼륨이 계열 차트에서 사라지면 이 기능의 목적(§3.6)과 상충하고,
    다른 stats(전부 set_volume 기반, 아카이브 포함)와도 불일치하기 때문.
    """
    exercises = db.execute(
        "SELECT id, name_ko FROM exercise"
        " WHERE base_movement = ? AND is_archived = 0 ORDER BY id",
        (base_movement,),
    ).fetchall()
    if not exercises:
        # 해당 계열 활성 종목 없음 — 404 대신 빈 결과 (계약 형태 고정)
        return StatsFamilyOut(base_movement=base_movement, exercises=[], points=[])

    rows = db.execute(
        f"""
        SELECT sv.date AS date, SUM(sv.volume_kg) AS vol,
               MAX({E1RM_EXPR}) AS top_e1rm
        FROM set_volume sv
        JOIN exercise e ON e.id = sv.exercise_id
        WHERE sv.is_warmup = 0 AND e.base_movement = ?
        GROUP BY sv.date ORDER BY sv.date
        """,
        (base_movement,),
    ).fetchall()
    return StatsFamilyOut(
        base_movement=base_movement,
        exercises=[FamilyExercise(id=r["id"], name_ko=r["name_ko"]) for r in exercises],
        points=[
            FamilyPoint(
                date=r["date"],
                total_volume=round(r["vol"], 2),
                top_e1rm=round(r["top_e1rm"], 2) if r["top_e1rm"] is not None else None,
            )
            for r in rows
        ],
    )


@router.get("/stats/prs", response_model=StatsPrsOut)
def stats_prs(db: sqlite3.Connection = Depends(get_db)) -> StatsPrsOut:
    events, bests = _pr_events(db)
    records = [
        ExercisePrRow(
            exercise_id=ex_id,
            name_ko=bests[ex_id]["name_ko"],
            weight_pr=_pr_record(bests[ex_id]["weight"]),
            e1rm_pr=_pr_record(bests[ex_id]["e1rm"]),
        )
        for ex_id in sorted(bests, key=lambda i: bests[i]["name_ko"])
    ]
    return StatsPrsOut(records=records, feed=_feed(events, 20))


@router.get("/stats/calendar", response_model=StatsCalendarOut)
def stats_calendar(
    months: int = Query(default=6, ge=1, le=60),
    db: sqlite3.Connection = Depends(get_db),
) -> StatsCalendarOut:
    today = _effective_today()
    rows = db.execute(
        """
        SELECT sv.date AS date, SUM(sv.volume_kg) AS vol,
               COUNT(DISTINCT sv.session_id) AS session_count
        FROM set_volume sv
        WHERE sv.is_warmup = 0 AND sv.date >= DATE(?, ?)
        GROUP BY sv.date ORDER BY sv.date
        """,
        (today.isoformat(), f"-{months} months"),
    ).fetchall()
    return StatsCalendarOut(
        points=[
            CalendarPoint(
                date=r["date"],
                volume_kg=round(r["vol"], 2),
                session_count=r["session_count"],
            )
            for r in rows
        ]
    )


@router.get("/export/db")
def export_db(db: sqlite3.Connection = Depends(get_db)) -> FileResponse:
    tmp_dir = tempfile.mkdtemp(prefix="volume-app-export-")
    filename = f"app-{_effective_today():%Y%m%d}.db"
    snapshot_path = os.path.join(tmp_dir, filename)
    db.execute("VACUUM INTO ?", (snapshot_path,))
    return FileResponse(
        snapshot_path,
        filename=filename,
        media_type="application/octet-stream",
        background=BackgroundTask(shutil.rmtree, tmp_dir, ignore_errors=True),
    )


@router.get("/export/csv")
def export_csv(db: sqlite3.Connection = Depends(get_db)) -> Response:
    rows = db.execute(
        """
        SELECT sv.date AS date, e.name_ko AS name_ko, e.name_en AS name_en,
               ws.set_index AS set_index, ws.weight_kg AS weight_kg,
               ws.reps AS reps, ws.is_warmup AS is_warmup,
               sv.volume_kg AS volume_kg, ws.note AS note,
               e.base_movement AS base_movement, e.equipment AS equipment,
               e.support AS support, e.grip AS grip, e.angle AS angle,
               img.code AS intent_muscle,
               (SELECT GROUP_CONCAT(mg.code, ',')
                FROM exercise_muscle em
                JOIN muscle_group mg ON mg.id = em.muscle_group_id
                WHERE em.exercise_id = sv.exercise_id AND em.role = 'primary'
               ) AS primary_muscles
        FROM set_volume sv
        JOIN workout_set ws ON ws.id = sv.set_id
        JOIN exercise e ON e.id = sv.exercise_id
        LEFT JOIN muscle_group img ON img.id = sv.intent_muscle_group_id
        ORDER BY sv.date, sv.session_id, ws.set_index
        """
    ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "date", "exercise_name_ko", "name_en", "set_index", "weight_kg",
            "reps", "is_warmup", "volume_kg", "primary_muscles", "note",
            # §3.6 속성 5종 (aliases 제외)
            "base_movement", "equipment", "support", "grip", "angle",
            # §3.7 기록 의도 주동근 — 끝에 추가
            "intent_muscle",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["date"], r["name_ko"], r["name_en"] or "", r["set_index"],
                r["weight_kg"], r["reps"], r["is_warmup"],
                round(r["volume_kg"], 2), r["primary_muscles"] or "", r["note"] or "",
                r["base_movement"] or "", r["equipment"] or "", r["support"] or "",
                r["grip"] or "", r["angle"] or "",
                r["intent_muscle"] or "",
            ]
        )
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="workout-export.csv"'
        },
    )
