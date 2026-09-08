import csv
import io
from datetime import timedelta

import pytest

from app.routers.stats import CSV_COLUMNS
from app.seed_data.targets import TARGETS
from helpers import add_bodyweight, add_session, add_set, effective_today, ex_id


# ---- 손계산 fixture: 2026-06 시나리오 --------------------------------------
# 2026-06-01(월) 세션1: 벤치 100x10(=1000, mid_chest), 벤치 웜업 80x5(=400 제외), 스쿼트 100x5(=500, quads)
# 2026-06-03(수) 세션2: 벤치 50x10(=500)
# 2026-06-08(월) 세션3: 벤치 60x10(=600)
@pytest.fixture()
def june_data(db):
    bench = ex_id(db, "벤치프레스")
    squat = ex_id(db, "백스쿼트")
    s1 = add_session(db, "2026-06-01")
    add_set(db, s1, bench, 100, 10)
    add_set(db, s1, bench, 80, 5, warmup=1)
    add_set(db, s1, squat, 100, 5)
    s2 = add_session(db, "2026-06-03")
    add_set(db, s2, bench, 50, 10)
    s3 = add_session(db, "2026-06-08")
    add_set(db, s3, bench, 60, 10)
    return {"bench": bench, "squat": squat}


def test_volume_weekly_with_target_attribution(auth_client, june_data):
    res = auth_client.get(
        "/api/stats/volume",
        params={"granularity": "week", "from": "2026-06-01", "to": "2026-06-14"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["granularity"] == "week"
    assert [(p["period"], p["total_volume"]) for p in body["points"]] == [
        ("2026-06-01", 2000.0),  # 1000 + 500(스쿼트) + 500(수요일 벤치), 웜업 400 제외
        ("2026-06-08", 600.0),
    ]
    pm = body["points"][0]["per_muscle"]
    # 100% 귀속: 벤치(mid_chest→chest) 1500, 스쿼트(quads) 500. 삼두·어깨는 0 (협응근 분배 없음)
    assert pm["chest"] == pytest.approx(1500.0)
    assert pm["quads"] == pytest.approx(500.0)
    assert pm["triceps"] == 0.0 and pm["shoulders"] == 0.0 and pm["hamstrings"] == 0.0
    assert set(pm) == {t[0] for t in TARGETS if t[3] == 2}  # 근육(level 2) 전부, 0 포함
    pr = body["points"][0]["per_region"]
    assert pr["chest"] == pytest.approx(1500.0)
    assert pr["legs"] == pytest.approx(500.0)
    assert pr["arms"] == 0.0 and pr["shoulders"] == 0.0 and pr["back"] == 0.0 and pr["core"] == 0.0


def test_volume_day_month_and_warmup_switch(auth_client, june_data):
    res = auth_client.get(
        "/api/stats/volume",
        params={"granularity": "day", "from": "2026-06-01", "to": "2026-06-30"},
    )
    assert [(p["period"], p["total_volume"]) for p in res.json()["points"]] == [
        ("2026-06-01", 1500.0),
        ("2026-06-03", 500.0),
        ("2026-06-08", 600.0),
    ]

    res = auth_client.get("/api/stats/volume", params={"granularity": "month"})
    assert [(p["period"], p["total_volume"]) for p in res.json()["points"]] == [
        ("2026-06", 2600.0)
    ]

    res = auth_client.get(
        "/api/stats/volume",
        params={"granularity": "week", "to": "2026-06-07", "include_warmup": "true"},
    )
    point = res.json()["points"][0]
    assert point["total_volume"] == pytest.approx(2400.0)  # 웜업 80x5=400 포함
    assert point["per_muscle"]["chest"] == pytest.approx(1900.0)


def test_muscles_volume_and_sets_all_levels(auth_client, june_data):
    res = auth_client.get(
        "/api/stats/muscles", params={"from": "2026-06-01", "to": "2026-06-30"}
    )
    assert res.status_code == 200
    by_code = {p["code"]: p for p in res.json()["points"]}
    assert len(by_code) == len(TARGETS)  # 타겟 행 전부 반환 (0 포함)
    # 벤치 워킹 3세트 총 2100 (mid_chest) → 세부 행과 근육 행 양쪽, 스쿼트 1세트 500 (quads)
    assert by_code["chest"]["volume_kg"] == pytest.approx(2100.0)
    assert by_code["chest"]["set_count"] == 3
    assert by_code["mid_chest"]["volume_kg"] == pytest.approx(2100.0)
    assert by_code["mid_chest"]["set_count"] == 3
    assert by_code["upper_chest"]["set_count"] == 0
    assert by_code["quads"]["volume_kg"] == pytest.approx(500.0)
    assert by_code["quads"]["set_count"] == 1
    assert by_code["triceps"]["volume_kg"] == 0.0
    assert by_code["chest"]["level"] == 2 and by_code["chest"]["parent_code"] is None
    assert by_code["mid_chest"]["level"] == 3 and by_code["mid_chest"]["parent_code"] == "chest"
    assert by_code["lower_back"]["region"] == "back"


def test_bodyweight_factor_and_load_multiplier(auth_client, db):
    pullup = ex_id(db, "풀업")  # bodyweight_factor 1.0, 타겟 lats → 근육 back
    db_bench = ex_id(db, "덤벨 벤치프레스")  # load_multiplier 2
    add_bodyweight(db, "2026-06-01", 70)
    add_bodyweight(db, "2026-06-03", 75)
    s1 = add_session(db, "2026-06-02")
    add_set(db, s1, pullup, 0, 10)  # (0 + 1.0*70) * 1 * 10 = 700
    add_set(db, s1, db_bench, 20, 10)  # 20 * 2 * 10 = 400
    s2 = add_session(db, "2026-06-04")
    add_set(db, s2, pullup, 0, 10)  # 최신 체중 75 → 750

    res = auth_client.get("/api/stats/volume", params={"granularity": "day"})
    points = {p["period"]: p for p in res.json()["points"]}
    assert points["2026-06-02"]["total_volume"] == pytest.approx(1100.0)
    assert points["2026-06-02"]["per_muscle"]["back"] == pytest.approx(700.0)
    assert points["2026-06-02"]["per_muscle"]["chest"] == pytest.approx(400.0)
    assert points["2026-06-04"]["total_volume"] == pytest.approx(750.0)


def test_bodyweight_is_per_user(auth_client, user_client, db):
    """체중은 사용자별 — 관리자 체중이 bob의 맨몸 볼륨에 섞이면 안 된다."""
    add_bodyweight(db, "2026-06-01", 70)  # 관리자
    pullup = ex_id(db, "풀업")
    bob_id = db.execute("SELECT id FROM user WHERE username = 'bob'").fetchone()[0]
    s = add_session(db, "2026-06-02", user_id=bob_id)
    add_set(db, s, pullup, 0, 10)  # bob은 체중 기록 없음 → 0
    res = user_client.get("/api/stats/volume", params={"granularity": "day"})
    assert [(p["period"], p["total_volume"]) for p in res.json()["points"]] == [("2026-06-02", 0.0)]


def test_exercise_stats_e1rm_and_prs(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    s1 = add_session(db, "2026-06-01")
    add_set(db, s1, bench, 90, 5, warmup=1)  # e1RM·볼륨 제외
    add_set(db, s1, bench, 100, 10)  # e1RM = 100*(1+10/30) = 133.33
    s2 = add_session(db, "2026-06-03")
    add_set(db, s2, bench, 105, 3)  # e1RM = 115.5
    add_set(db, s2, bench, 105, 15)  # reps>12 → e1RM 제외, 볼륨은 포함

    res = auth_client.get(f"/api/stats/exercises/{bench}")
    assert res.status_code == 200
    body = res.json()
    assert body["name_ko"] == "벤치프레스"
    assert [
        (p["date"], p["volume_kg"], p["top_weight_kg"], p["e1rm"]) for p in body["points"]
    ] == [
        ("2026-06-01", 1000.0, 100.0, 133.33),
        ("2026-06-03", 1890.0, 105.0, 115.5),
    ]
    assert body["weight_pr"]["value"] == 105.0
    assert body["weight_pr"]["date"] == "2026-06-03"
    assert body["weight_pr"]["reps"] == 3  # 105x3이 그날 최고 중량을 먼저 달성
    assert body["e1rm_pr"]["value"] == 133.33  # 베이스라인 유지 (105x3은 미달)
    assert (body["e1rm_pr"]["weight_kg"], body["e1rm_pr"]["reps"]) == (100.0, 10)

    assert auth_client.get("/api/stats/exercises/999999").status_code == 404


def test_prs_baseline_strictly_greater_one_per_day(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    s1 = add_session(db, "2026-06-01")
    add_set(db, s1, bench, 100, 5)  # 첫 기록 = 베이스라인, PR 아님
    s2 = add_session(db, "2026-06-03")
    add_set(db, s2, bench, 102.5, 5)
    add_set(db, s2, bench, 105, 5)  # 같은 날 연속 갱신 → 하루 최고 1건만
    s3 = add_session(db, "2026-06-05")
    add_set(db, s3, bench, 105, 5)  # 동률 — strictly greater 아님

    body = auth_client.get("/api/stats/prs").json()
    feed = body["feed"]
    assert {(r["kind"], r["value"], r["date"]) for r in feed} == {
        ("weight", 105.0, "2026-06-03"),
        ("e1rm", 122.5, "2026-06-03"),  # 105*(1+5/30)
    }
    assert all((r["weight_kg"], r["reps"]) == (105.0, 5) for r in feed)
    row = next(r for r in body["records"] if r["exercise_id"] == bench)
    assert row["weight_pr"] == {"value": 105.0, "date": "2026-06-03", "weight_kg": 105.0, "reps": 5}
    assert row["e1rm_pr"]["value"] == 122.5


def test_pr_first_session_is_baseline_not_first_day(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    s1 = add_session(db, "2026-06-01")
    add_set(db, s1, bench, 100, 5)
    s2 = add_session(db, "2026-06-01")
    add_set(db, s2, bench, 105, 5)
    feed = auth_client.get("/api/stats/prs").json()["feed"]
    assert {(r["kind"], r["value"], r["date"]) for r in feed} == {
        ("weight", 105.0, "2026-06-01"),
        ("e1rm", 122.5, "2026-06-01"),
    }


def test_prs_are_per_user(auth_client, user_client, db):
    """관리자 기록이 bob의 PR 베이스라인이 되면 안 된다 (사용자 범위 격리)."""
    bench = ex_id(db, "벤치프레스")
    s1 = add_session(db, "2026-06-01")
    add_set(db, s1, bench, 100, 5)
    bob_id = db.execute("SELECT id FROM user WHERE username = 'bob'").fetchone()[0]
    s2 = add_session(db, "2026-06-03", user_id=bob_id)
    add_set(db, s2, bench, 120, 5)  # bob의 첫 세션 → 베이스라인, PR 아님
    assert user_client.get("/api/stats/prs").json()["feed"] == []
    assert auth_client.get("/api/stats/prs").json()["feed"] == []


def test_summary_excludes_warmup_only_and_empty_sessions(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    today = effective_today()
    s1 = add_session(db, today.isoformat())
    add_set(db, s1, bench, 60, 10)
    s2 = add_session(db, (today - timedelta(days=1)).isoformat())
    add_set(db, s2, bench, 40, 5, warmup=1)  # 웜업 전용 세션
    add_session(db, (today - timedelta(days=2)).isoformat())  # 빈 세션

    body = auth_client.get("/api/stats/summary").json()
    assert body["totals"]["session_count"] == 1
    assert body["frequency"]["days_since_last"] == 0


def test_summary_hand_computed(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    today = effective_today()
    monday = today - timedelta(days=today.weekday())
    prev_monday = monday - timedelta(weeks=1)
    s_prev = add_session(db, prev_monday.isoformat())
    add_set(db, s_prev, bench, 50, 10)  # 500
    s_cur = add_session(db, today.isoformat())
    add_set(db, s_cur, bench, 100, 10)  # 1000

    body = auth_client.get("/api/stats/summary").json()
    tw = body["this_week"]
    assert tw["week_start"] == monday.isoformat()
    assert tw["volume_kg"] == 1000.0
    assert tw["prev_volume_kg"] == 500.0
    assert tw["change_pct"] == 100.0
    assert tw["in_progress"] is True
    assert (tw["session_count"], tw["set_count"], tw["pr_count"]) == (1, 1, 2)
    sparkline = body["weekly_sparkline"]
    assert len(sparkline) == 8
    assert sparkline[-1] == {"week_start": monday.isoformat(), "volume_kg": 1000.0}
    assert sparkline[-2]["volume_kg"] == 500.0

    # 이번 주 근육 세트: 벤치 1세트 → chest 1 (100% 귀속, 삼두·어깨 없음)
    assert [(m["code"], m["set_count"]) for m in body["muscle_sets_this_week"]] == [("chest", 1)]

    assert len(body["recent_prs"]) == 2
    assert {p["kind"] for p in body["recent_prs"]} == {"weight", "e1rm"}
    freq = body["frequency"]
    assert (freq["days_this_week"], freq["weekly_streak"], freq["days_since_last"]) == (1, 2, 0)
    totals = body["totals"]
    assert (totals["tonnage_kg"], totals["session_count"], totals["set_count"], totals["rep_count"]) == (
        1500.0, 2, 2, 20,
    )


def test_calendar(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    today = effective_today()
    s = add_session(db, today.isoformat())
    add_set(db, s, bench, 100, 10)
    add_set(db, s, bench, 100, 8)
    add_set(db, s, bench, 60, 5, warmup=1)
    old = add_session(db, "2024-01-01")  # 6개월 범위 밖
    add_set(db, old, bench, 100, 10)

    points = auth_client.get("/api/stats/calendar", params={"months": 6}).json()["points"]
    assert points == [{"date": today.isoformat(), "volume_kg": 1800.0, "session_count": 1}]


# ---- §3.6 계열 합산 (family) ----------------------------------------------


def test_family_aggregates_by_date(auth_client, db):
    bench = ex_id(db, "벤치프레스")            # base_movement=벤치프레스
    db_bench = ex_id(db, "덤벨 벤치프레스")     # base_movement=벤치프레스, ×2
    squat = ex_id(db, "백스쿼트")              # base_movement=스쿼트 — 미포함이어야 함

    s1 = add_session(db, "2026-06-01")
    add_set(db, s1, bench, 100, 10)            # vol 1000, e1RM 133.33
    add_set(db, s1, bench, 60, 5, warmup=1)    # 웜업 — 제외
    add_set(db, s1, db_bench, 30, 10)          # vol 30×2×10=600, e1RM 40
    add_set(db, s1, squat, 100, 5)             # 다른 계열 — 제외
    s2 = add_session(db, "2026-06-03")
    add_set(db, s2, db_bench, 32.5, 20)        # vol 1300, reps>12 → e1RM 없음

    body = auth_client.get("/api/stats/family", params={"base_movement": "벤치프레스"}).json()
    assert body["base_movement"] == "벤치프레스"
    names = {e["name_ko"] for e in body["exercises"]}
    assert {"벤치프레스", "인클라인 벤치프레스", "덤벨 벤치프레스", "인클라인 덤벨프레스", "체스트 프레스 머신"} <= names
    assert body["points"] == [
        {"date": "2026-06-01", "total_volume": 1600.0, "top_e1rm": 133.33},
        {"date": "2026-06-03", "total_volume": 1300.0, "top_e1rm": None},
    ]


def test_family_archived_excluded_from_roster_but_sets_included(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    db_bench = ex_id(db, "덤벨 벤치프레스")
    s = add_session(db, "2026-06-01")
    add_set(db, s, bench, 100, 10)
    add_set(db, s, db_bench, 30, 10)
    db.execute("UPDATE exercise SET is_archived = 1 WHERE id = ?", (db_bench,))
    db.commit()
    body = auth_client.get("/api/stats/family", params={"base_movement": "벤치프레스"}).json()
    assert all(e["id"] != db_bench for e in body["exercises"])
    assert body["points"] == [{"date": "2026-06-01", "total_volume": 1600.0, "top_e1rm": 133.33}]


def test_family_all_archived_returns_empty(auth_client, db):
    db.execute("UPDATE exercise SET is_archived = 1 WHERE base_movement = '스쿼트'")
    db.commit()
    body = auth_client.get("/api/stats/family", params={"base_movement": "스쿼트"}).json()
    assert body == {"base_movement": "스쿼트", "exercises": [], "points": []}


def test_family_unknown_base_movement_empty(auth_client):
    body = auth_client.get("/api/stats/family", params={"base_movement": "없는 계열"}).json()
    assert body == {"base_movement": "없는 계열", "exercises": [], "points": []}


def test_family_missing_param_422(auth_client):
    assert auth_client.get("/api/stats/family").status_code == 422


def test_export_csv_bom_and_columns(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    s = add_session(db, "2026-06-01")
    add_set(db, s, bench, 100, 10, note="메모")
    add_set(db, s, bench, 80, 10, target="hamstrings")  # 세트 타겟 3단계가 CSV에 나온다

    res = auth_client.get("/api/export/csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert res.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM

    rows = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
    assert rows[0] == CSV_COLUMNS
    assert rows[1] == [
        "2026-06-01", "벤치프레스", "Barbell Bench Press", "1", "100.0", "10", "0", "1000.0",
        "mid_chest", "chest", "chest", "메모", "벤치프레스", "바벨,플랫", "",
    ]
    assert rows[2][8:11] == ["hamstrings", "hamstrings", "legs"]


def test_export_csv_is_per_user(auth_client, user_client, db):
    bench = ex_id(db, "벤치프레스")
    add_set(db, add_session(db, "2026-06-01"), bench, 100, 10)
    rows = list(csv.reader(io.StringIO(user_client.get("/api/export/csv").content.decode("utf-8-sig"))))
    assert rows == [CSV_COLUMNS]


def test_export_db_snapshot_admin_only(auth_client, user_client, db):
    bench = ex_id(db, "벤치프레스")
    add_set(db, add_session(db, "2026-06-01"), bench, 100, 10)
    res = auth_client.get("/api/export/db")
    assert res.status_code == 200
    assert res.content[:16] == b"SQLite format 3\x00"
    assert "app-" in res.headers["content-disposition"]
    assert user_client.get("/api/export/db").status_code == 403


def test_stats_require_auth(client):
    for path in (
        "/api/stats/summary", "/api/stats/volume", "/api/stats/muscles",
        "/api/stats/exercises/1", "/api/stats/prs", "/api/stats/calendar",
        "/api/stats/family?base_movement=벤치프레스",
        "/api/export/db", "/api/export/csv",
    ):
        assert client.get(path).status_code == 401, path
