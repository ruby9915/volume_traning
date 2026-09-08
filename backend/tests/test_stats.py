import csv
import io
from datetime import timedelta

import pytest

from helpers import add_bodyweight, add_session, add_set, effective_today, ex_id


# ---- 손계산 fixture: 2026-06 시나리오 --------------------------------------
# 2026-06-01(월) 세션1: 벤치 100x10(=1000), 벤치 웜업 80x5(=400 제외), 스쿼트 100x5(=500)
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


def test_volume_weekly_with_muscle_weighting(auth_client, june_data):
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
    # 벤치 1500: chest primary 1.0 / triceps·shoulders secondary 0.5
    # 스쿼트 500: quads·glutes primary 1.0 / hamstrings·lower_back 0.5
    assert pm["chest"] == pytest.approx(1500.0)
    assert pm["triceps"] == pytest.approx(750.0)
    assert pm["shoulders"] == pytest.approx(750.0)
    assert pm["quads"] == pytest.approx(500.0)
    assert pm["glutes"] == pytest.approx(500.0)
    assert pm["hamstrings"] == pytest.approx(250.0)
    assert pm["lower_back"] == pytest.approx(250.0)
    assert pm["biceps"] == 0.0
    pr = body["points"][0]["per_region"]
    assert pr["chest"] == pytest.approx(1500.0)
    assert pr["arms"] == pytest.approx(750.0)
    assert pr["shoulders"] == pytest.approx(750.0)
    assert pr["legs"] == pytest.approx(1250.0)  # 500+500+250
    assert pr["back"] == pytest.approx(250.0)  # lower_back 롤업
    assert pr["core"] == 0.0


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


def test_muscles_weighted_volume_and_sets(auth_client, june_data):
    res = auth_client.get(
        "/api/stats/muscles", params={"from": "2026-06-01", "to": "2026-06-30"}
    )
    assert res.status_code == 200
    by_code = {p["code"]: p for p in res.json()["points"]}
    assert len(by_code) == 12  # 12분류 전부 반환 (0 포함)
    # 벤치 워킹 3세트 총 2100, 스쿼트 1세트 500
    assert by_code["chest"]["volume_kg"] == pytest.approx(2100.0)
    assert by_code["chest"]["set_count"] == pytest.approx(3.0)
    assert by_code["triceps"]["volume_kg"] == pytest.approx(1050.0)
    assert by_code["triceps"]["set_count"] == pytest.approx(1.5)
    assert by_code["quads"]["set_count"] == pytest.approx(1.0)
    assert by_code["hamstrings"]["volume_kg"] == pytest.approx(250.0)
    assert by_code["hamstrings"]["set_count"] == pytest.approx(0.5)
    assert by_code["calves"]["volume_kg"] == 0.0
    assert by_code["chest"]["region"] == "chest"
    assert by_code["lower_back"]["region"] == "back"


def test_bodyweight_factor_and_load_multiplier(auth_client, db):
    pullup = ex_id(db, "풀업")  # bodyweight_factor 1.0
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
    assert body["weight_pr"]["weight_kg"] == 105.0
    assert body["weight_pr"]["reps"] == 3  # 105x3이 그날 최고 중량을 먼저 달성
    assert body["e1rm_pr"]["value"] == 133.33  # 베이스라인 유지 (105x3은 미달)
    assert body["e1rm_pr"]["date"] == "2026-06-01"
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

    res = auth_client.get("/api/stats/prs")
    assert res.status_code == 200
    body = res.json()
    feed = body["feed"]
    assert len(feed) == 2  # weight 1건 + e1rm 1건, 전부 06-03
    assert {(r["kind"], r["value"], r["date"]) for r in feed} == {
        ("weight", 105.0, "2026-06-03"),
        ("e1rm", 122.5, "2026-06-03"),  # 105*(1+5/30)
    }
    assert all(
        (r["weight_kg"], r["reps"]) == (105.0, 5) for r in feed
    )  # PR을 만든 세트의 실제 값
    assert all(r["exercise_name_ko"] == "벤치프레스" for r in feed)
    row = next(r for r in body["records"] if r["exercise_id"] == bench)
    assert row["weight_pr"] == {
        "value": 105.0, "date": "2026-06-03", "weight_kg": 105.0, "reps": 5,
    }
    assert row["e1rm_pr"]["value"] == 122.5


def test_pr_first_session_is_baseline_not_first_day(auth_client, db):
    # §6.3: 첫 '세션'만 베이스라인 — 같은 날 두 번째 세션의 갱신은 PR
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


def test_summary_excludes_warmup_only_and_empty_sessions(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    today = effective_today()
    s1 = add_session(db, today.isoformat())
    add_set(db, s1, bench, 60, 10)
    s2 = add_session(db, (today - timedelta(days=1)).isoformat())
    add_set(db, s2, bench, 40, 5, warmup=1)  # 웜업 전용 세션
    add_session(db, (today - timedelta(days=2)).isoformat())  # 빈 세션

    body = auth_client.get("/api/stats/summary").json()
    assert body["totals"]["session_count"] == 1  # §6.1 is_warmup=0 기준
    assert body["frequency"]["days_since_last"] == 0  # 웜업 전용일은 운동일 아님


def test_summary_hand_computed(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    today = effective_today()
    monday = today - timedelta(days=today.weekday())
    prev_monday = monday - timedelta(weeks=1)
    s_prev = add_session(db, prev_monday.isoformat())
    add_set(db, s_prev, bench, 50, 10)  # 500
    s_cur = add_session(db, today.isoformat())
    add_set(db, s_cur, bench, 100, 10)  # 1000

    res = auth_client.get("/api/stats/summary")
    assert res.status_code == 200, res.text
    body = res.json()

    tw = body["this_week"]
    assert tw["week_start"] == monday.isoformat()
    assert tw["volume_kg"] == 1000.0
    assert tw["prev_volume_kg"] == 500.0
    assert tw["change_pct"] == 100.0
    assert tw["in_progress"] is True
    assert tw["session_count"] == 1
    assert tw["set_count"] == 1
    assert tw["pr_count"] == 2  # 오늘 weight + e1rm
    sparkline = body["weekly_sparkline"]
    assert len(sparkline) == 8
    assert sparkline[-1] == {"week_start": monday.isoformat(), "volume_kg": 1000.0}
    assert sparkline[-2]["volume_kg"] == 500.0
    assert sparkline[0]["volume_kg"] == 0.0

    ms = {m["code"]: m["weighted_sets"] for m in body["muscle_sets_this_week"]}
    assert ms == {"chest": 1.0, "triceps": 0.5, "shoulders": 0.5}  # 이번 주만

    # 전주 50x10 베이스라인 → 오늘 100x10이 weight+e1rm PR
    assert len(body["recent_prs"]) == 2
    assert {p["kind"] for p in body["recent_prs"]} == {"weight", "e1rm"}
    assert all(p["date"] == today.isoformat() for p in body["recent_prs"])
    assert all(
        (p["weight_kg"], p["reps"]) == (100.0, 10) for p in body["recent_prs"]
    )

    freq = body["frequency"]
    assert freq["days_this_week"] == 1
    assert freq["weekly_streak"] == 2
    assert freq["days_since_last"] == 0

    totals = body["totals"]
    assert totals["tonnage_kg"] == 1500.0
    assert totals["session_count"] == 2
    assert totals["set_count"] == 2
    assert totals["rep_count"] == 20


def test_calendar(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    today = effective_today()
    s = add_session(db, today.isoformat())
    add_set(db, s, bench, 100, 10)
    add_set(db, s, bench, 100, 8)
    add_set(db, s, bench, 60, 5, warmup=1)
    old = add_session(db, "2024-01-01")  # 6개월 범위 밖
    add_set(db, old, bench, 100, 10)

    res = auth_client.get("/api/stats/calendar", params={"months": 6})
    assert res.status_code == 200
    points = res.json()["points"]
    # 워킹 2세트지만 세션은 1개 — session_count는 DISTINCT session_id
    assert points == [
        {"date": today.isoformat(), "volume_kg": 1800.0, "session_count": 1}
    ]


# ---- §3.6 계열 합산 (family) ----------------------------------------------


def test_family_aggregates_by_date(auth_client, db):
    bench = ex_id(db, "벤치프레스")            # base_movement=벤치프레스 (시드 백필)
    db_bench = ex_id(db, "덤벨 벤치프레스")     # base_movement=벤치프레스, ×2
    squat = ex_id(db, "백스쿼트")              # base_movement=스쿼트 — 미포함이어야 함

    s1 = add_session(db, "2026-06-01")
    add_set(db, s1, bench, 100, 10)            # vol 1000, e1RM 133.33
    add_set(db, s1, bench, 60, 5, warmup=1)    # 웜업 — 제외
    add_set(db, s1, db_bench, 30, 10)          # vol 30×2×10=600, e1RM 40 (입력값 기준)
    add_set(db, s1, squat, 100, 5)             # 다른 계열 — 제외
    s2 = add_session(db, "2026-06-03")
    add_set(db, s2, db_bench, 32.5, 20)        # vol 1300, reps>12 → e1RM 없음

    res = auth_client.get("/api/stats/family", params={"base_movement": "벤치프레스"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["base_movement"] == "벤치프레스"
    # 활성 벤치프레스 계열 5종 전부 (세트 유무 무관 — 참여 종목 목록은 계열 명부)
    names = {e["name_ko"] for e in body["exercises"]}
    assert names == {
        "벤치프레스", "인클라인 벤치프레스", "덤벨 벤치프레스",
        "인클라인 덤벨프레스", "체스트 프레스 머신",
    }
    assert body["points"] == [
        {"date": "2026-06-01", "total_volume": 1600.0, "top_e1rm": 133.33},
        {"date": "2026-06-03", "total_volume": 1300.0, "top_e1rm": None},
    ]


def test_family_archived_excluded_from_roster_but_sets_included(auth_client, db):
    """아카이브 종목: 명부(exercises)에서는 제외, 과거 세트는 합산(points)에 포함.

    분해 후 옛 통합 종목을 아카이브해도 계열 차트에서 과거 볼륨이 사라지지
    않아야 한다(§3.6 — 분해로 갈라진 기록을 합쳐 보는 창구). 다른 stats와
    동일하게 set_volume 기반으로 아카이브 종목의 기록을 포함한다.
    """
    bench = ex_id(db, "벤치프레스")
    db_bench = ex_id(db, "덤벨 벤치프레스")
    s = add_session(db, "2026-06-01")
    add_set(db, s, bench, 100, 10)               # vol 1000, e1RM 133.33
    add_set(db, s, db_bench, 30, 10)             # vol 30×2×10=600
    db.execute("UPDATE exercise SET is_archived = 1 WHERE id = ?", (db_bench,))
    db.commit()

    body = auth_client.get(
        "/api/stats/family", params={"base_movement": "벤치프레스"}
    ).json()
    assert all(e["id"] != db_bench for e in body["exercises"])
    assert body["points"] == [
        {"date": "2026-06-01", "total_volume": 1600.0, "top_e1rm": 133.33}
    ]


def test_family_all_archived_returns_empty(auth_client, db):
    """계열 전체가 아카이브면 빈 결과 — 활성 종목 없는 계열은 노출 대상 아님."""
    db.execute(
        "UPDATE exercise SET is_archived = 1 WHERE base_movement = '스쿼트'"
    )
    db.commit()
    body = auth_client.get(
        "/api/stats/family", params={"base_movement": "스쿼트"}
    ).json()
    assert body == {"base_movement": "스쿼트", "exercises": [], "points": []}


def test_family_unknown_base_movement_empty(auth_client):
    body = auth_client.get(
        "/api/stats/family", params={"base_movement": "없는 계열"}
    ).json()
    assert body == {"base_movement": "없는 계열", "exercises": [], "points": []}


def test_family_missing_param_422(auth_client):
    assert auth_client.get("/api/stats/family").status_code == 422


def test_export_csv_bom_and_columns(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    s = add_session(db, "2026-06-01")
    add_set(db, s, bench, 100, 10, note="메모")
    # §3.7 intent 지정 세트 — CSV 마지막 컬럼에 code로 나온다
    add_set(db, s, bench, 80, 10)
    hamstrings = db.execute(
        "SELECT id FROM muscle_group WHERE code = 'hamstrings'"
    ).fetchone()["id"]
    db.execute(
        "UPDATE workout_set SET intent_muscle_group_id = ? WHERE set_index = 2",
        (hamstrings,),
    )
    db.commit()

    res = auth_client.get("/api/export/csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert res.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM

    reader = csv.reader(io.StringIO(res.content.decode("utf-8-sig")))
    rows = list(reader)
    assert rows[0] == [
        "date", "exercise_name_ko", "name_en", "set_index", "weight_kg",
        "reps", "is_warmup", "volume_kg", "primary_muscles", "note",
        "base_movement", "equipment", "support", "grip", "angle",
        "intent_muscle",
    ]
    # 벤치프레스는 시드 백필로 base_movement/equipment가 채워져 있다 (§3.6)
    assert rows[1] == [
        "2026-06-01", "벤치프레스", "Barbell Bench Press", "1", "100.0",
        "10", "0", "1000.0", "chest", "메모",
        "벤치프레스", "바벨", "", "", "", "",
    ]
    assert rows[2][-1] == "hamstrings"


def test_export_db_snapshot(auth_client, db):
    bench = ex_id(db, "벤치프레스")
    s = add_session(db, "2026-06-01")
    add_set(db, s, bench, 100, 10)

    res = auth_client.get("/api/export/db")
    assert res.status_code == 200
    assert res.content[:16] == b"SQLite format 3\x00"
    assert "app-" in res.headers["content-disposition"]


def test_stats_require_auth(client):
    for path in (
        "/api/stats/summary", "/api/stats/volume", "/api/stats/muscles",
        "/api/stats/exercises/1", "/api/stats/prs", "/api/stats/calendar",
        "/api/stats/family?base_movement=벤치프레스",
        "/api/export/db", "/api/export/csv",
    ):
        assert client.get(path).status_code == 401, path
