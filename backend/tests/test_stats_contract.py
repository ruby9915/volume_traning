"""프론트 계약(frontend/src/api/types.ts) 회귀 테스트.

목적: stats 응답의 **키 집합**이 types.ts와 갈라지면 pytest가 즉시 잡는다.
값이 아니라 구조만 본다(값 검증은 test_stats.py). 데이터가 있는 상태와
빈 DB 상태 양쪽에서 동일한 키가 나와야 한다 — 프론트가 undefined를 읽고
TypeError로 죽는 사고를 막기 위함.
"""

from datetime import timedelta

import pytest

from app.seed_data.targets import REGIONS, TARGETS
from helpers import add_session, add_set, assert_keys, effective_today, ex_id

# ---- types.ts 정본 키 집합 -------------------------------------------------

THIS_WEEK_KEYS = {
    "week_start", "volume_kg", "prev_volume_kg", "change_pct",
    "in_progress", "session_count", "set_count", "pr_count",
}
WEEK_VOLUME_POINT_KEYS = {"week_start", "volume_kg"}
MUSCLE_SET_KEYS = {"code", "name_ko", "region", "set_count"}
PR_EVENT_KEYS = {
    "date", "exercise_id", "exercise_name_ko", "kind", "value", "weight_kg", "reps",
}
FREQUENCY_KEYS = {"days_this_week", "weekly_streak", "days_since_last"}
TOTALS_KEYS = {"tonnage_kg", "session_count", "set_count", "rep_count"}
SUMMARY_KEYS = {
    "this_week", "weekly_sparkline", "muscle_sets_this_week",
    "recent_prs", "frequency", "totals", "analytics",
}
ANALYTICS_GATE_KEYS = {"ready", "weeks_of_data", "required_weeks"}  # §11.1

VOLUME_KEYS = {"granularity", "points"}
VOLUME_POINT_KEYS = {"period", "total_volume", "per_muscle", "per_region"}

MUSCLES_KEYS = {"points"}
MUSCLE_POINT_KEYS = {"code", "name_ko", "region", "level", "parent_code", "volume_kg", "set_count"}

EXERCISE_STATS_KEYS = {"exercise_id", "name_ko", "points", "weight_pr", "e1rm_pr"}
EXERCISE_POINT_KEYS = {"date", "session_id", "volume_kg", "top_weight_kg", "e1rm"}
PR_RECORD_KEYS = {"value", "date", "weight_kg", "reps"}

PRS_KEYS = {"records", "feed"}
EXERCISE_PRS_KEYS = {"exercise_id", "name_ko", "weight_pr", "e1rm_pr"}

CALENDAR_KEYS = {"points"}
CALENDAR_POINT_KEYS = {"date", "volume_kg", "session_count"}

FAMILY_KEYS = {"base_movement", "exercises", "points"}
FAMILY_EXERCISE_KEYS = {"id", "name_ko"}
FAMILY_POINT_KEYS = {"date", "total_volume", "top_e1rm"}

TARGET_KEYS = {"code", "name_ko", "region", "level", "parent_code"}

MUSCLE_CODES = {t[0] for t in TARGETS if t[3] == 2}   # per_muscle 키 = 근육(level 2)
ALL_TARGET_CODES = {t[0] for t in TARGETS}            # /stats/muscles·/targets = 전 타겟
REGION_SET = set(REGIONS)


# ---- fixtures -------------------------------------------------------------


@pytest.fixture()
def bench_id(db):
    """PR 이벤트·여러 주·웜업이 모두 존재하는 상태 — 모든 배열이 비지 않도록."""
    bench = ex_id(db, "벤치프레스")
    squat = ex_id(db, "백스쿼트")
    today = effective_today()
    monday = today - timedelta(days=today.weekday())

    s_prev = add_session(db, (monday - timedelta(weeks=1)).isoformat())
    add_set(db, s_prev, bench, 50, 10)  # 베이스라인
    add_set(db, s_prev, squat, 60, 5)

    s_cur = add_session(db, today.isoformat())
    add_set(db, s_cur, bench, 40, 5, warmup=1)
    add_set(db, s_cur, bench, 100, 10)  # weight + e1rm PR
    add_set(db, s_cur, squat, 80, 5, target="vastus_medialis")  # 세부 타겟 (squat PR)
    return bench


# ---- 공통 단언 헬퍼 --------------------------------------------------------


def _assert_each(items, expected, label):
    for i, item in enumerate(items):
        assert_keys(item, expected, f"{label}[{i}]")


def _assert_summary_shape(body):
    assert_keys(body, SUMMARY_KEYS, "summary")
    assert_keys(body["this_week"], THIS_WEEK_KEYS, "summary.this_week")
    _assert_each(body["weekly_sparkline"], WEEK_VOLUME_POINT_KEYS, "weekly_sparkline")
    _assert_each(body["muscle_sets_this_week"], MUSCLE_SET_KEYS, "muscle_sets_this_week")
    _assert_each(body["recent_prs"], PR_EVENT_KEYS, "recent_prs")
    assert_keys(body["frequency"], FREQUENCY_KEYS, "summary.frequency")
    assert_keys(body["totals"], TOTALS_KEYS, "summary.totals")
    assert_keys(body["analytics"], ANALYTICS_GATE_KEYS, "summary.analytics")


def _assert_volume_shape(body):
    assert_keys(body, VOLUME_KEYS, "volume")
    _assert_each(body["points"], VOLUME_POINT_KEYS, "volume.points")


def _assert_muscles_shape(body):
    assert_keys(body, MUSCLES_KEYS, "muscles")
    _assert_each(body["points"], MUSCLE_POINT_KEYS, "muscles.points")


def _assert_exercise_shape(body):
    assert_keys(body, EXERCISE_STATS_KEYS, "exercise")
    _assert_each(body["points"], EXERCISE_POINT_KEYS, "exercise.points")
    for field in ("weight_pr", "e1rm_pr"):
        if body[field] is not None:
            assert_keys(body[field], PR_RECORD_KEYS, f"exercise.{field}")


def _assert_prs_shape(body):
    assert_keys(body, PRS_KEYS, "prs")
    _assert_each(body["records"], EXERCISE_PRS_KEYS, "prs.records")
    _assert_each(body["feed"], PR_EVENT_KEYS, "prs.feed")
    for i, row in enumerate(body["records"]):
        for field in ("weight_pr", "e1rm_pr"):
            if row[field] is not None:
                assert_keys(row[field], PR_RECORD_KEYS, f"prs.records[{i}].{field}")


def _assert_calendar_shape(body):
    assert_keys(body, CALENDAR_KEYS, "calendar")
    _assert_each(body["points"], CALENDAR_POINT_KEYS, "calendar.points")


def _assert_family_shape(body):
    assert_keys(body, FAMILY_KEYS, "family")
    _assert_each(body["exercises"], FAMILY_EXERCISE_KEYS, "family.exercises")
    _assert_each(body["points"], FAMILY_POINT_KEYS, "family.points")


# ---- 데이터가 있는 상태 ----------------------------------------------------


def test_summary_contract_with_data(auth_client, bench_id):
    res = auth_client.get("/api/stats/summary")
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_summary_shape(body)

    assert len(body["weekly_sparkline"]) == 8
    assert body["muscle_sets_this_week"], "이번 주 근육 세트가 비어 계약 검증이 무의미"
    assert body["recent_prs"], "PR 이벤트가 비어 계약 검증이 무의미"
    assert len(body["recent_prs"]) <= 3

    tw = body["this_week"]
    assert isinstance(tw["in_progress"], bool) and tw["in_progress"] is True
    assert isinstance(tw["session_count"], int)
    assert isinstance(tw["set_count"], int)
    assert isinstance(tw["pr_count"], int)
    assert tw["change_pct"] is None or isinstance(tw["change_pct"], (int, float))

    for m in body["muscle_sets_this_week"]:
        assert m["code"] in MUSCLE_CODES  # 근육 단위로 합산 (세부 코드 아님)
        assert m["region"] in REGION_SET
        assert isinstance(m["set_count"], int)
    for pr in body["recent_prs"]:
        assert pr["kind"] in ("weight", "e1rm")
        assert isinstance(pr["reps"], int)
    freq = body["frequency"]
    assert freq["days_since_last"] is None or isinstance(freq["days_since_last"], int)


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_volume_contract_with_data(auth_client, bench_id, granularity):
    res = auth_client.get("/api/stats/volume", params={"granularity": granularity})
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_volume_shape(body)
    assert body["granularity"] == granularity
    assert body["points"], "볼륨 포인트가 비어 계약 검증이 무의미"
    for p in body["points"]:
        assert set(p["per_muscle"]) == MUSCLE_CODES
        assert set(p["per_region"]) == REGION_SET


def test_muscles_contract_with_data(auth_client, bench_id):
    res = auth_client.get("/api/stats/muscles")
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_muscles_shape(body)
    assert {p["code"] for p in body["points"]} == ALL_TARGET_CODES
    for p in body["points"]:
        assert p["region"] in REGION_SET
        assert p["level"] in (2, 3)
        assert (p["parent_code"] is None) == (p["level"] == 2)
        assert isinstance(p["set_count"], int)


def test_targets_contract(auth_client):
    res = auth_client.get("/api/targets")
    assert res.status_code == 200, res.text
    body = res.json()
    for i, t in enumerate(body):
        assert_keys(t, TARGET_KEYS, f"targets[{i}]")
    assert {t["code"] for t in body} == ALL_TARGET_CODES
    codes = {t["code"] for t in body}
    for t in body:
        assert t["parent_code"] is None or t["parent_code"] in codes


def test_exercise_contract_with_data(auth_client, bench_id):
    res = auth_client.get(f"/api/stats/exercises/{bench_id}")
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_exercise_shape(body)
    assert body["points"], "종목 포인트가 비어 계약 검증이 무의미"
    assert body["weight_pr"] is not None and body["e1rm_pr"] is not None


def test_prs_contract_with_data(auth_client, bench_id):
    res = auth_client.get("/api/stats/prs")
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_prs_shape(body)
    assert body["records"] and body["feed"]
    assert any(r["weight_pr"] is not None for r in body["records"])


def test_calendar_contract_with_data(auth_client, bench_id):
    res = auth_client.get("/api/stats/calendar")
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_calendar_shape(body)
    assert body["points"]
    for p in body["points"]:
        assert isinstance(p["session_count"], int)


def test_family_contract_with_data(auth_client, db, bench_id):
    res = auth_client.get("/api/stats/family", params={"base_movement": "벤치프레스"})
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_family_shape(body)
    assert body["base_movement"] == "벤치프레스"
    assert body["exercises"] and body["points"]
    for p in body["points"]:
        assert p["top_e1rm"] is None or isinstance(p["top_e1rm"], (int, float))


# ---- 빈 DB 상태 (프론트 백지 사고가 났던 경로) -----------------------------


def test_summary_contract_empty_db(auth_client):
    body = auth_client.get("/api/stats/summary").json()
    _assert_summary_shape(body)
    tw = body["this_week"]
    assert tw["volume_kg"] == 0.0 and tw["prev_volume_kg"] == 0.0
    assert tw["change_pct"] is None
    assert tw["in_progress"] is True
    assert (tw["session_count"], tw["set_count"], tw["pr_count"]) == (0, 0, 0)
    assert len(body["weekly_sparkline"]) == 8
    assert body["muscle_sets_this_week"] == []
    assert body["recent_prs"] == []
    assert body["frequency"]["days_since_last"] is None
    assert body["totals"] == {"tonnage_kg": 0.0, "session_count": 0, "set_count": 0, "rep_count": 0}


def test_volume_contract_empty_db(auth_client):
    body = auth_client.get("/api/stats/volume", params={"granularity": "week"}).json()
    _assert_volume_shape(body)
    assert body["points"] == []


def test_muscles_contract_empty_db(auth_client):
    body = auth_client.get("/api/stats/muscles").json()
    _assert_muscles_shape(body)
    assert {p["code"] for p in body["points"]} == ALL_TARGET_CODES
    assert all(p["volume_kg"] == 0.0 and p["set_count"] == 0 for p in body["points"])


def test_exercise_contract_empty_db(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    body = auth_client.get(f"/api/stats/exercises/{bench}").json()
    _assert_exercise_shape(body)
    assert body["points"] == [] and body["weight_pr"] is None and body["e1rm_pr"] is None


def test_prs_contract_empty_db(auth_client):
    body = auth_client.get("/api/stats/prs").json()
    _assert_prs_shape(body)
    assert body["records"] == [] and body["feed"] == []


def test_calendar_contract_empty_db(auth_client):
    body = auth_client.get("/api/stats/calendar").json()
    _assert_calendar_shape(body)
    assert body["points"] == []


def test_family_contract_empty_db(auth_client):
    body = auth_client.get("/api/stats/family", params={"base_movement": "벤치프레스"}).json()
    _assert_family_shape(body)
    assert len(body["exercises"]) >= 5
    assert body["points"] == []
