"""§11 고급 분석 — 데이터 준비도 게이트 + 6개 엔드포인트 (값·계약·불변식).

게이트: 훈련 주(웜업 아닌 세트가 있는 ISO 주) < 4 → 403 {code: insufficient_data}. 사용자별.
불변식: 간접 볼륨은 보조 데이터 — /stats/volume 총볼륨·/stats/muscles 직접 세트 수는 그대로.
"""

from datetime import timedelta

import pytest

from app.routers.analytics import (
    ACWR_WARN,
    INDIRECT_WEIGHT_DEFAULT,
    NEGLECT_DAYS,
    REP_MAX_RANGE,
)
from app.routers.stats import ADVANCED_MIN_WEEKS
from helpers import add_session, add_set, assert_keys, effective_today, ex_id

ADV = "/api/stats/advanced"

# ---- types.ts 정본 키 집합 -------------------------------------------------
FREQ_KEYS = {"weeks", "neglect_days", "regions", "muscles"}
FREQ_ROW_KEYS = {"code", "name_ko", "region", "per_week", "avg_per_week", "days_since_last", "neglected"}
TREND_KEYS = {"first_week", "acwr_warn", "points"}
TREND_POINT_KEYS = {"week_start", "volume_kg", "set_count", "ma4_kg", "acwr", "in_progress"}
REP_MAX_KEYS = {"exercise_id", "name_ko", "cells", "rep_prs"}
REP_MAX_CELL_KEYS = {"reps", "best_weight_kg", "best_date", "implied_weight_kg"}
REP_PR_KEYS = {"date", "weight_kg", "reps", "prev_reps"}
FATIGUE_KEYS = {"exercise_id", "name_ko", "sessions_used", "points", "rep_ranges"}
FATIGUE_POINT_KEYS = {"ordinal", "sessions", "avg_reps", "avg_weight_kg", "rel_reps"}
BUCKET_KEYS = {"bucket", "sets", "share"}
INTENSITY_KEYS = {"sets_total", "avg_intensity_pct", "zones", "rep_ranges"}
ATTR_KEYS = {"indirect_weight", "points"}
ATTR_POINT_KEYS = {
    "code", "name_ko", "region", "direct_sets", "indirect_sets", "fractional_sets",
    "direct_volume_kg", "indirect_volume_kg", "fractional_volume_kg",
}


def _monday(weeks_ago: int):
    today = effective_today()
    return today - timedelta(days=today.weekday()) - timedelta(weeks=weeks_ago)


def _week_sessions(db, n_weeks: int, user_id=None) -> list[int]:
    """최근 n주(이번 주 포함) 각 월요일에 세션 하나씩 — 오래된 순 session_id."""
    return [
        add_session(db, _monday(n_weeks - 1 - i).isoformat(), user_id=user_id)
        for i in range(n_weeks)
    ]


# ---- 게이트 ----------------------------------------------------------------


def test_gate_locked_on_fresh_account(auth_client):
    body = auth_client.get("/api/stats/summary").json()["analytics"]
    assert body == {"ready": False, "weeks_of_data": 0, "required_weeks": ADVANCED_MIN_WEEKS}
    res = auth_client.get(f"{ADV}/frequency")
    assert res.status_code == 403, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "insufficient_data"
    assert detail["weeks_of_data"] == 0 and detail["required_weeks"] == ADVANCED_MIN_WEEKS


def test_gate_counts_training_weeks_not_sessions_or_calendar(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    # 같은 주에 세션 3개 = 훈련 주 1
    for _ in range(3):
        add_set(db, add_session(db, _monday(0).isoformat()), bench, 60, 8)
    assert auth_client.get("/api/stats/summary").json()["analytics"]["weeks_of_data"] == 1
    assert auth_client.get(f"{ADV}/trend").status_code == 403

    # 10주 전 한 번 + 웜업만 있는 주 → 여전히 2 (웜업 전용 주는 훈련 주가 아니다)
    add_set(db, add_session(db, _monday(10).isoformat()), bench, 60, 8)
    add_set(db, add_session(db, _monday(5).isoformat()), bench, 40, 8, warmup=1)
    gate = auth_client.get("/api/stats/summary").json()["analytics"]
    assert gate["weeks_of_data"] == 2 and gate["ready"] is False
    assert auth_client.get(f"{ADV}/attribution").status_code == 403


@pytest.mark.parametrize("path", ["frequency", "trend", "rep-max?exercise_id=1", "fatigue?exercise_id=1", "intensity", "attribution"])
def test_gate_opens_at_required_weeks(auth_client, db, path):
    bench = ex_id(db, "벤치프레스")
    sessions = _week_sessions(db, ADVANCED_MIN_WEEKS - 1)
    for sid in sessions:
        add_set(db, sid, bench, 60, 8)
    assert auth_client.get(f"{ADV}/{path}").status_code == 403

    add_set(db, add_session(db, _monday(ADVANCED_MIN_WEEKS - 1).isoformat()), bench, 60, 8)
    gate = auth_client.get("/api/stats/summary").json()["analytics"]
    assert gate == {"ready": True, "weeks_of_data": ADVANCED_MIN_WEEKS, "required_weeks": ADVANCED_MIN_WEEKS}
    res = auth_client.get(f"{ADV}/{path}")
    assert res.status_code == 200, res.text


def test_gate_is_per_user(auth_client, user_client, db):
    bench = ex_id(db, "벤치프레스")
    for sid in _week_sessions(db, ADVANCED_MIN_WEEKS):
        add_set(db, sid, bench, 60, 8)
    assert auth_client.get(f"{ADV}/frequency").status_code == 200
    assert user_client.get(f"{ADV}/frequency").status_code == 403
    assert user_client.get("/api/stats/summary").json()["analytics"]["ready"] is False


def test_gate_requires_auth(client):
    assert client.get(f"{ADV}/frequency").status_code == 401


# ---- 공통 fixture: 4주 데이터 ----------------------------------------------


@pytest.fixture()
def four_weeks(db):
    """4주 × 벤치프레스 3세트(10·8·6회) + 첫 주에만 랫풀다운 1세트. 반환: (bench, lat, sessions)."""
    bench, lat = ex_id(db, "벤치프레스"), ex_id(db, "랫풀다운")
    sessions = _week_sessions(db, 4)
    for sid in sessions:
        add_set(db, sid, bench, 100, 10)
        add_set(db, sid, bench, 100, 8)
        add_set(db, sid, bench, 100, 6)
    add_set(db, sessions[0], lat, 50, 10)
    return bench, lat, sessions


# ---- 1. 분할 실행 점검 ------------------------------------------------------


def test_frequency_values_and_neglect(auth_client, four_weeks):
    res = auth_client.get(f"{ADV}/frequency?weeks=4")
    assert res.status_code == 200, res.text
    body = res.json()
    assert_keys(body, FREQ_KEYS, "frequency")
    assert body["weeks"] == [_monday(3 - i).isoformat() for i in range(4)]
    assert body["neglect_days"] == NEGLECT_DAYS
    for row in body["muscles"] + body["regions"]:
        assert_keys(row, FREQ_ROW_KEYS, row["code"])
        assert len(row["per_week"]) == 4

    muscles = {m["code"]: m for m in body["muscles"]}
    assert muscles["chest"]["per_week"] == [1, 1, 1, 1]
    assert muscles["chest"]["avg_per_week"] == 1.0  # 이번 주 제외 3주 평균
    assert muscles["chest"]["neglected"] is False
    assert muscles["back"]["per_week"] == [1, 0, 0, 0]  # 랫풀다운(lats → back)
    assert muscles["back"]["days_since_last"] >= 21
    assert muscles["back"]["neglected"] is True
    assert muscles["quads"]["days_since_last"] is None and muscles["quads"]["neglected"] is False

    regions = {r["code"]: r for r in body["regions"]}
    assert regions["chest"]["per_week"] == [1, 1, 1, 1]
    assert regions["back"]["neglected"] is True
    assert regions["legs"]["per_week"] == [0, 0, 0, 0]


# ---- 2. 볼륨 추세 ------------------------------------------------------------


def test_trend_moving_average_and_acwr(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    sessions = _week_sessions(db, 8)
    for i, sid in enumerate(sessions):
        add_set(db, sid, bench, 100, 10)  # 1000 kg/주
    add_set(db, sessions[-1], bench, 100, 10)  # 이번 주만 2000

    res = auth_client.get(f"{ADV}/trend?weeks=6")
    assert res.status_code == 200, res.text
    body = res.json()
    assert_keys(body, TREND_KEYS, "trend")
    assert body["first_week"] == _monday(7).isoformat()
    assert body["acwr_warn"] == ACWR_WARN
    pts = body["points"]
    assert len(pts) == 6
    for p in pts:
        assert_keys(p, TREND_POINT_KEYS, p["week_start"])
    assert [p["in_progress"] for p in pts] == [False] * 5 + [True]
    # 첫 훈련 주(7주 전)부터 4주가 찬 시점(4주 전)부터 ma4 존재
    assert pts[0]["week_start"] == _monday(5).isoformat() and pts[0]["ma4_kg"] is None
    assert pts[1]["ma4_kg"] == 1000.0  # 4주 전: 7·6·5·4주 전 평균
    assert pts[1]["acwr"] is None  # 직전 4주(8~5주 전)가 첫 주 이전에 걸침
    assert pts[2]["acwr"] == 1.0  # 3주 전: 1000 / mean(7~4주 전 = 1000)
    assert pts[-1]["volume_kg"] == 2000.0 and pts[-1]["set_count"] == 2
    assert pts[-1]["ma4_kg"] == 1250.0 and pts[-1]["acwr"] == 2.0


def test_trend_weeks_without_training_are_zero_not_null(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    for w in (6, 4, 2, 0):
        add_set(db, add_session(db, _monday(w).isoformat()), bench, 100, 10)
    pts = auth_client.get(f"{ADV}/trend?weeks=4").json()["points"]
    assert [p["volume_kg"] for p in pts] == [0.0, 1000.0, 0.0, 1000.0]
    assert pts[-1]["ma4_kg"] == 500.0  # 쉰 주는 0으로 평균에 들어간다
    assert pts[-1]["acwr"] == 2.0  # 1000 / mean(4주 전 1000, 3주 전 0, 2주 전 1000, 1주 전 0)


# ---- 3. rep-max 매트릭스 + Rep PR ----------------------------------------------


def test_rep_max_matrix_and_rep_prs(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    s1, s2, s3, s4 = _week_sessions(db, 4)
    add_set(db, s1, bench, 100, 5)  # 100kg 베이스라인
    add_set(db, s2, bench, 100, 8)  # Rep PR (5 → 8)
    add_set(db, s3, bench, 110, 3)  # 110kg 베이스라인
    add_set(db, s3, bench, 100, 8)  # 동률 — PR 아님
    add_set(db, s4, bench, 100, 8)
    add_set(db, s4, bench, 100, 9)  # 같은 세션 두 세트 → 세션당 1건 (8 → 9)
    add_set(db, s4, bench, 120, 2, warmup=1)  # 웜업 제외

    res = auth_client.get(f"{ADV}/rep-max?exercise_id={bench}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert_keys(body, REP_MAX_KEYS, "rep-max")
    assert body["exercise_id"] == bench and body["name_ko"] == "벤치프레스"
    cells = {c["reps"]: c for c in body["cells"]}
    assert set(cells) == set(REP_MAX_RANGE)
    for c in body["cells"]:
        assert_keys(c, REP_MAX_CELL_KEYS, f"cell {c['reps']}")
    assert cells[5] == {"reps": 5, "best_weight_kg": 100.0, "best_date": _monday(3).isoformat(), "implied_weight_kg": 100.0}
    assert cells[3]["best_weight_kg"] == 110.0 and cells[1]["best_weight_kg"] is None
    assert [cells[r]["implied_weight_kg"] for r in (1, 2, 3, 4, 8, 9, 10)] == [110, 110, 110, 100, 100, 100, None]
    assert cells[9]["best_weight_kg"] == 100.0

    prs = body["rep_prs"]
    for p in prs:
        assert_keys(p, REP_PR_KEYS, "rep_pr")
    assert prs == [
        {"date": _monday(0).isoformat(), "weight_kg": 100.0, "reps": 9, "prev_reps": 8},
        {"date": _monday(2).isoformat(), "weight_kg": 100.0, "reps": 8, "prev_reps": 5},
    ]


def test_rep_max_unknown_or_foreign_exercise_404(auth_client, user_client, db):
    bench = ex_id(db, "벤치프레스")
    for sid in _week_sessions(db, 4):
        add_set(db, sid, bench, 60, 8)
    assert auth_client.get(f"{ADV}/rep-max?exercise_id=999999").status_code == 404
    custom = user_client.post(
        "/api/exercises", json={"name_ko": "밥의 종목", "default_target": "chest"}
    ).json()["id"]
    assert auth_client.get(f"{ADV}/rep-max?exercise_id={custom}").status_code == 404


# ---- 4. 피로 곡선 ------------------------------------------------------------


def test_fatigue_curve_and_rep_ranges(auth_client, four_weeks):
    bench, _lat, _sessions = four_weeks
    res = auth_client.get(f"{ADV}/fatigue?exercise_id={bench}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert_keys(body, FATIGUE_KEYS, "fatigue")
    assert body["sessions_used"] == 4
    pts = body["points"]
    for p in pts:
        assert_keys(p, FATIGUE_POINT_KEYS, f"ordinal {p['ordinal']}")
    assert [(p["ordinal"], p["sessions"], p["avg_reps"], p["avg_weight_kg"], p["rel_reps"]) for p in pts] == [
        (1, 4, 10.0, 100.0, 1.0),
        (2, 4, 8.0, 100.0, 0.8),
        (3, 4, 6.0, 100.0, 0.6),
    ]
    ranges = {b["bucket"]: b for b in body["rep_ranges"]}
    assert set(ranges) == {"1-5", "6-12", "13-20", "21+"}
    assert ranges["6-12"] == {"bucket": "6-12", "sets": 12, "share": 1.0}
    assert ranges["1-5"]["sets"] == 0 and ranges["1-5"]["share"] == 0.0

    # 기간 필터: 이번 주만
    body = auth_client.get(f"{ADV}/fatigue?exercise_id={bench}&from={_monday(0).isoformat()}").json()
    assert body["sessions_used"] == 1 and body["rep_ranges"][1]["sets"] == 3


# ---- 5. 강도 존 ---------------------------------------------------------------


def test_intensity_zones_use_running_e1rm(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    s1, s2, s3, s4 = _week_sessions(db, 4)
    add_set(db, s1, bench, 100, 10)  # e1RM 133.33 → 75.0% (70-80)
    add_set(db, s2, bench, 120, 3)  # e1RM 132 < 133.33 → 90.0% (90%+)
    add_set(db, s3, bench, 60, 20)  # reps>12: e1RM 없음, 강도 45% (<60)
    add_set(db, s4, bench, 0, 15)  # weight 0: 강도 대상 아님, rep range에는 포함
    add_set(db, s4, bench, 50, 10, warmup=1)  # 웜업 제외

    res = auth_client.get(f"{ADV}/intensity")
    assert res.status_code == 200, res.text
    body = res.json()
    assert_keys(body, INTENSITY_KEYS, "intensity")
    assert body["sets_total"] == 3
    assert body["avg_intensity_pct"] == 70.0
    zones = {z["bucket"]: z["sets"] for z in body["zones"]}
    assert zones == {"<60%": 1, "60-70%": 0, "70-80%": 1, "80-90%": 0, "90%+": 1}
    for z in body["zones"]:
        assert_keys(z, BUCKET_KEYS, z["bucket"])
    ranges = {b["bucket"]: b["sets"] for b in body["rep_ranges"]}
    assert ranges == {"1-5": 1, "6-12": 1, "13-20": 2, "21+": 0}

    # 기간 필터는 집계에만 — 러닝 e1RM은 전체 이력에서 (3주 전 세트는 첫 주 133.33 기준 45%)
    body = auth_client.get(f"{ADV}/intensity?from={_monday(1).isoformat()}").json()
    assert body["sets_total"] == 1 and body["zones"][0]["sets"] == 1
    assert auth_client.get(f"{ADV}/intensity?exercise_id=999999").status_code == 404


# ---- 6. 직접/간접 이중 집계 ---------------------------------------------------


def _muscle_of(db, code: str) -> str:
    return db.execute("SELECT muscle_code FROM target_path WHERE code = ?", (code,)).fetchone()[0]


def test_attribution_rules_and_invariants(auth_client, db):
    """벤치프레스: 기본 mid_chest(→chest), 보조 triceps·front_delt(→shoulders).
    - 기본 타겟 세트: chest 직접, triceps·shoulders 간접
    - 타겟을 triceps로 바꾼 세트: triceps 직접, chest(기본)·shoulders 간접 — triceps는 간접 아님
    - 타겟을 upper_chest로 바꾼 세트: chest 직접, chest 간접 없음(같은 근육), triceps·shoulders 간접
    - 총볼륨·직접 세트 수는 /stats/volume·/stats/muscles와 같다 (간접은 더하지 않는다)"""
    bench, curl = ex_id(db, "벤치프레스"), ex_id(db, "레그 익스텐션")
    assert _muscle_of(db, "front_delt") == "shoulders"
    s1, s2, s3, s4 = _week_sessions(db, 4)
    add_set(db, s1, bench, 100, 10)
    add_set(db, s2, bench, 100, 10, target="triceps")
    add_set(db, s3, bench, 100, 10, target="upper_chest")
    add_set(db, s4, curl, 50, 10)  # 보조 근육 없는 고립 종목 → 간접 0
    add_set(db, s4, bench, 40, 10, warmup=1)  # 기본은 웜업 제외

    res = auth_client.get(f"{ADV}/attribution")
    assert res.status_code == 200, res.text
    body = res.json()
    assert_keys(body, ATTR_KEYS, "attribution")
    assert body["indirect_weight"] == INDIRECT_WEIGHT_DEFAULT
    pts = {p["code"]: p for p in body["points"]}
    for p in body["points"]:
        assert_keys(p, ATTR_POINT_KEYS, p["code"])
    assert len(pts) == 14  # level 2 전부

    assert (pts["chest"]["direct_sets"], pts["chest"]["indirect_sets"]) == (2, 1)
    assert (pts["triceps"]["direct_sets"], pts["triceps"]["indirect_sets"]) == (1, 2)
    assert (pts["shoulders"]["direct_sets"], pts["shoulders"]["indirect_sets"]) == (0, 3)
    assert (pts["quads"]["direct_sets"], pts["quads"]["indirect_sets"]) == (1, 0)
    assert pts["chest"]["fractional_sets"] == 2.5 and pts["shoulders"]["fractional_sets"] == 1.5
    assert pts["chest"]["direct_volume_kg"] == 2000.0 and pts["chest"]["indirect_volume_kg"] == 1000.0
    assert pts["chest"]["fractional_volume_kg"] == 2500.0
    assert pts["shoulders"]["direct_volume_kg"] == 0.0 and pts["shoulders"]["fractional_volume_kg"] == 1500.0

    # 불변식: 직접 합 = 정본 집계, 총볼륨 불변
    muscles = auth_client.get("/api/stats/muscles").json()["points"]
    direct_sets = {m["code"]: m["set_count"] for m in muscles if m["level"] == 2}
    assert {c: p["direct_sets"] for c, p in pts.items()} == direct_sets
    total = sum(p["total_volume"] for p in auth_client.get("/api/stats/volume?granularity=month").json()["points"])
    assert total == 3500.0 == sum(p["direct_volume_kg"] for p in pts.values())
    assert sum(p["fractional_volume_kg"] for p in pts.values()) > total  # 간접은 별도 축

    # 가중치 파라미터 + 웜업 포함
    body = auth_client.get(f"{ADV}/attribution?indirect_weight=0.33&include_warmup=true").json()
    pts = {p["code"]: p for p in body["points"]}
    assert body["indirect_weight"] == 0.33
    assert pts["chest"]["direct_sets"] == 3 and pts["triceps"]["indirect_sets"] == 3
    assert pts["triceps"]["fractional_sets"] == round(1 + 0.33 * 3, 2)
    assert auth_client.get(f"{ADV}/attribution?indirect_weight=1.5").status_code == 422


def test_attribution_uses_custom_exercise_secondaries(auth_client, db):
    """커스텀 종목의 보조 근육(API로 지정)도 간접 후보. 보조가 없으면 기본 타겟 override만 간접."""
    lat = ex_id(db, "랫풀다운")
    for sid in _week_sessions(db, 4):
        add_set(db, sid, lat, 50, 10)
    res = auth_client.post(
        "/api/exercises",
        json={"name_ko": "내 로우", "default_target": "back", "secondary_targets": ["biceps", "rear_delt"]},
    )
    assert res.status_code == 201, res.text
    mine = res.json()
    assert mine["secondary_targets"] == ["biceps", "rear_delt"] or set(mine["secondary_targets"]) == {"biceps", "rear_delt"}
    add_set(db, add_session(db, _monday(0).isoformat()), mine["id"], 60, 10)

    pts = {p["code"]: p for p in auth_client.get(f"{ADV}/attribution").json()["points"]}
    assert pts["back"]["direct_sets"] == 5
    assert pts["biceps"]["indirect_sets"] == 5  # 랫풀다운 4(시드 biceps) + 내 로우 1
    assert pts["shoulders"]["indirect_sets"] == 1  # rear_delt → shoulders


# ---- 종목 API: 보조 근육 필드 -------------------------------------------------


def test_exercise_secondary_targets_crud(auth_client, user_client):
    bench = next(e for e in auth_client.get("/api/exercises").json() if e["name_ko"] == "벤치프레스")
    assert set(bench["secondary_targets"]) == {"triceps", "front_delt"}
    assert set(bench["secondary_targets_ko"]) == {"삼두", "전면 삼각근"} or len(bench["secondary_targets_ko"]) == 2

    # 기본 타겟과 같은 코드 → 422, 상한 초과 → 422, 모르는 코드 → 422
    bad = {"name_ko": "x", "default_target": "chest", "secondary_targets": ["chest"]}
    assert user_client.post("/api/exercises", json=bad).status_code == 422
    bad["secondary_targets"] = ["biceps", "triceps", "forearms", "quads", "glutes", "calves"]
    assert user_client.post("/api/exercises", json=bad).status_code == 422
    bad["secondary_targets"] = ["nope"]
    assert user_client.post("/api/exercises", json=bad).status_code == 422

    res = user_client.post(
        "/api/exercises",
        json={"name_ko": "밥 프레스", "default_target": "chest", "secondary_targets": ["triceps", "triceps", "front_delt"]},
    )
    assert res.status_code == 201, res.text
    ex = res.json()
    assert ex["secondary_targets"] == ["front_delt", "triceps"] or set(ex["secondary_targets"]) == {"front_delt", "triceps"}
    assert len(ex["secondary_targets"]) == 2  # 중복 제거

    # 교체·해제
    res = user_client.patch(f"/api/exercises/{ex['id']}", json={"secondary_targets": ["biceps"]})
    assert res.status_code == 200 and res.json()["secondary_targets"] == ["biceps"]
    res = user_client.patch(f"/api/exercises/{ex['id']}", json={"secondary_targets": []})
    assert res.status_code == 200 and res.json()["secondary_targets"] == []
    assert user_client.patch(f"/api/exercises/{ex['id']}", json={"secondary_targets": None}).status_code == 422

    # 기본 타겟을 보조 근육 중 하나로 바꾸면 그 보조 근육은 빠진다 (겹침 불변식)
    user_client.patch(f"/api/exercises/{ex['id']}", json={"secondary_targets": ["triceps", "front_delt"]})
    res = user_client.patch(f"/api/exercises/{ex['id']}", json={"default_target": "triceps"})
    assert res.status_code == 200, res.text
    assert res.json()["default_target"] == "triceps" and res.json()["secondary_targets"] == ["front_delt"]
    # 같은 요청에서 기본 타겟과 보조가 겹치면 422
    res = user_client.patch(
        f"/api/exercises/{ex['id']}", json={"default_target": "chest", "secondary_targets": ["chest"]}
    )
    assert res.status_code == 422

    # 내장 종목의 보조 근육은 관리자만 (일반 사용자 403)
    assert user_client.patch(f"/api/exercises/{bench['id']}", json={"secondary_targets": []}).status_code == 403
    res = auth_client.patch(f"/api/exercises/{bench['id']}", json={"secondary_targets": ["triceps"]})
    assert res.status_code == 200 and res.json()["secondary_targets"] == ["triceps"]
