"""§15 세트의 머신 — 저장·수정·표시, (종목, 머신) 범위의 PR·지난 기록, 종목의 마지막 머신,
머신 → 종목 후보. 머신은 볼륨 계산과 무관하다(R-07).
"""

import csv
import io
import uuid

from helpers import add_session, add_set, assert_keys, ex_id, machine_id, post_set, seed_exercise_id

MACHINE_EXERCISES_KEYS = {"machine", "used", "suggested"}
MACHINE_KEYS = {"id", "brand", "model", "name_ko", "target"}
MACHINE_USE_KEYS = {"exercise_id", "set_count", "last_date"}
LAST_RECORD_KEYS = {"session_id", "session_date", "machine_id", "machine_name", "sets"}


def _machines(client, q: str, n: int = 2) -> list[dict]:
    found = client.get("/api/machines", params={"q": q, "limit": n}).json()
    assert len(found) == n, f"시드 머신 부족: {q}"
    return found


def _ok(res):
    assert res.status_code in (200, 201), res.text
    return res.json()


# ---- 저장·수정·표시 ---------------------------------------------------------


def test_set_machine_create_patch_clear(auth_client):
    ex = seed_exercise_id("하이 로우")
    a, b = _machines(auth_client, "high row")
    plain = _ok(post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10))
    assert (plain["machine_id"], plain["machine_name"]) == (None, None), "미지정 = 머신 없음"

    saved = _ok(
        post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10, machine_id=a["id"])
    )
    assert (saved["machine_id"], saved["machine_name"]) == (a["id"], a["name_ko"])
    assert saved["volume_kg"] == plain["volume_kg"] == 600, "머신은 볼륨과 무관"

    res = auth_client.patch(f"/api/sets/{saved['id']}", json={"machine_id": b["id"]})
    assert _ok(res)["machine_id"] == b["id"]
    res = auth_client.patch(f"/api/sets/{saved['id']}", json={"weight_kg": 65})
    assert _ok(res)["machine_id"] == b["id"], "다른 필드 수정은 머신 유지"
    res = auth_client.patch(f"/api/sets/{saved['id']}", json={"machine_id": None})
    assert (_ok(res)["machine_id"], res.json()["machine_name"]) == (None, None), "명시적 null = 머신 없음"

    # 없는 머신은 422, 세트는 만들어지지 않는다
    bad = post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10, machine_id=999_999)
    assert bad.status_code == 422, bad.text
    assert auth_client.patch(f"/api/sets/{saved['id']}", json={"machine_id": 999_999}).status_code == 422
    detail = auth_client.get(f"/api/sessions/{saved['session_id']}").json()
    assert sum(len(g["sets"]) for g in detail["exercises"]) == 2


def test_set_machine_in_session_detail_and_idempotent_replay(auth_client):
    ex = seed_exercise_id("하이 로우")
    (a,) = _machines(auth_client, "high row", 1)
    payload = {
        "client_id": str(uuid.uuid4()), "date": "2026-07-21", "exercise_id": ex,
        "weight_kg": 70, "reps": 8, "machine_id": a["id"],
    }
    first = auth_client.post("/api/sets", json=payload)
    assert first.status_code == 201, first.text
    replay = auth_client.post("/api/sets", json={**payload, "machine_id": None})
    assert replay.status_code == 200 and replay.json()["machine_id"] == a["id"], "멱등 재전송은 저장된 값"

    post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=70, reps=8)
    detail = auth_client.get(f"/api/sessions/{first.json()['session_id']}").json()
    sets = detail["exercises"][0]["sets"]
    assert [(s["machine_id"], s["machine_name"]) for s in sets] == [(a["id"], a["name_ko"]), (None, None)]


def test_used_machine_joins_my_machines(auth_client, user_client):
    ex = seed_exercise_id("하이 로우")
    a, b = _machines(auth_client, "high row")
    assert auth_client.get("/api/me/machines").json() == []
    saved = _ok(post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10, machine_id=a["id"]))
    assert [m["id"] for m in auth_client.get("/api/me/machines").json()] == [a["id"]]
    _ok(auth_client.patch(f"/api/sets/{saved['id']}", json={"machine_id": b["id"]}))
    assert {m["id"] for m in auth_client.get("/api/me/machines").json()} == {a["id"], b["id"]}
    assert user_client.get("/api/me/machines").json() == [], "다른 사용자의 목록은 그대로"


def test_csv_machine_column_is_the_sets_machine(auth_client, db):
    row_ex = ex_id(db, "하이 로우")
    m = machine_id(db, "Torque High Row (T-HR)")
    s = add_session(db, "2026-06-01")
    add_set(db, s, row_ex, 100, 10, machine=m)
    add_set(db, s, row_ex, 100, 10)
    rows = list(csv.reader(io.StringIO(auth_client.get("/api/export/csv").content.decode("utf-8-sig"))))
    col = rows[0].index("machine")
    assert [r[col] for r in rows[1:]] == ["뉴텍 토크 하이 로우", ""]


# ---- PR 범위 = (종목, 머신) ------------------------------------------------


def _flags(res) -> tuple[bool, bool]:
    body = _ok(res)
    return body["is_weight_pr"], body["is_e1rm_pr"]


def test_pr_flags_are_scoped_per_machine(auth_client):
    ex = seed_exercise_id("하이 로우")
    a, b = (m["id"] for m in _machines(auth_client, "high row"))
    post = lambda day, w, **kw: post_set(  # noqa: E731
        auth_client, date=f"2026-07-{day:02d}", exercise_id=ex, weight_kg=w, reps=5, **kw
    )
    assert _flags(post(1, 100, machine_id=a)) == (False, False), "머신 A 첫 세션 = 베이스라인"
    # 종목 전체로는 최고 기록이지만 머신 B로는 처음 → PR 아님
    assert _flags(post(2, 120, machine_id=b)) == (False, False)
    assert _flags(post(3, 125, machine_id=b)) == (True, True), "머신 B 안에서 갱신"
    # 종목 전체 최고(125)보다 낮아도 머신 A 안에서는 갱신
    assert _flags(post(3, 105, machine_id=a)) == (True, True)
    assert _flags(post(3, 50)) == (False, False), "머신 없는 기록의 첫 세션 = 베이스라인"
    assert _flags(post(4, 55)) == (True, True), "머신 없는 기록끼리 갱신"
    assert _flags(post(4, 104, machine_id=a)) == (False, False), "A의 최고(105) 미만"


def test_pr_feed_and_records_with_machines(auth_client, db):
    ex = ex_id(db, "하이 로우")
    a = machine_id(db, "Torque High Row (T-HR)")
    for day, weight, machine in (
        ("2026-07-01", 100, a), ("2026-07-02", 120, None), ("2026-07-03", 110, a), ("2026-07-04", 130, None),
    ):
        add_set(db, add_session(db, day), ex, weight, 5, machine=machine)

    prs = auth_client.get("/api/stats/prs").json()
    feed = [(e["date"], e["kind"], e["value"], e["machine_id"], e["machine_name"]) for e in prs["feed"]]
    assert feed == [
        ("2026-07-04", "weight", 130.0, None, None),
        ("2026-07-04", "e1rm", round(130 * (1 + 5 / 30), 2), None, None),
        ("2026-07-03", "weight", 110.0, a, "뉴텍 토크 하이 로우"),
        ("2026-07-03", "e1rm", round(110 * (1 + 5 / 30), 2), a, "뉴텍 토크 하이 로우"),
    ]
    # 종목 최고 기록은 머신과 무관한 전체 최고
    record = next(r for r in prs["records"] if r["exercise_id"] == ex)
    assert (record["weight_pr"]["value"], record["weight_pr"]["date"]) == (130.0, "2026-07-04")
    stats = auth_client.get(f"/api/stats/exercises/{ex}").json()
    assert stats["weight_pr"]["value"] == 130.0
    assert auth_client.get("/api/stats/summary").json()["recent_prs"][0]["machine_id"] is None


def test_overall_best_keeps_first_achiever_across_machines(auth_client, db):
    ex = ex_id(db, "하이 로우")
    a = machine_id(db, "Torque High Row (T-HR)")
    add_set(db, add_session(db, "2026-07-01"), ex, 100, 5)  # 머신 없음 — 먼저 달성
    add_set(db, add_session(db, "2026-07-02"), ex, 100, 5, machine=a)  # 같은 값, 나중
    record = next(r for r in auth_client.get("/api/stats/prs").json()["records"] if r["exercise_id"] == ex)
    assert record["weight_pr"]["date"] == "2026-07-01"
    assert auth_client.get("/api/stats/prs").json()["feed"] == [], "두 범위 모두 첫 세션 — PR 없음"


# ---- 지난 기록·마지막 머신 --------------------------------------------------


def test_last_record_machine_scope(auth_client, db):
    ex = ex_id(db, "하이 로우")
    a = machine_id(db, "Torque High Row (T-HR)")
    s1 = add_session(db, "2026-07-01")
    add_set(db, s1, ex, 100, 8, machine=a)
    add_set(db, s1, ex, 100, 7, machine=a)
    s2 = add_session(db, "2026-07-02")
    add_set(db, s2, ex, 60, 12)
    s3 = add_session(db, "2026-07-03")
    add_set(db, s3, ex, 105, 6, machine=a)
    add_set(db, s3, ex, 62.5, 10)

    url = f"/api/exercises/{ex}/last-record"
    latest = auth_client.get(url).json()
    assert_keys(latest, LAST_RECORD_KEYS, "last-record")
    assert (latest["session_id"], latest["machine_id"]) == (s3, None), "생략 = 머신 무관, 그 세션 마지막 세트의 머신"
    assert [s["weight_kg"] for s in latest["sets"]] == [105, 62.5]

    on_a = auth_client.get(url, params={"machine": a}).json()
    assert (on_a["session_id"], on_a["machine_id"], on_a["machine_name"]) == (s3, a, "뉴텍 토크 하이 로우")
    assert [(s["weight_kg"], s["reps"]) for s in on_a["sets"]] == [(105, 6)]

    none = auth_client.get(url, params={"machine": "none"}).json()
    assert (none["session_id"], none["machine_id"]) == (s3, None)
    assert [(s["weight_kg"], s["reps"]) for s in none["sets"]] == [(62.5, 10)]

    other = machine_id(db, "Hack Squat")
    assert auth_client.get(url, params={"machine": other}).status_code == 404, "그 머신으로 한 기록 없음"
    assert auth_client.get(url, params={"machine": "abc"}).status_code == 422

    # exclude_session: 지금 기록 중인 세션(s3)을 빼면 그 전 세션이 '지난번'
    prev = auth_client.get(url, params={"exclude_session": s3}).json()
    assert (prev["session_id"], [s["weight_kg"] for s in prev["sets"]]) == (s2, [60])
    prev_a = auth_client.get(url, params={"machine": a, "exclude_session": s3}).json()
    assert (prev_a["session_id"], [s["reps"] for s in prev_a["sets"]]) == (s1, [8, 7])
    only = auth_client.get(url, params={"machine": "none", "exclude_session": s3}).json()
    assert only["session_id"] == s2
    assert auth_client.get(url, params={"machine": "none", "exclude_session": s2}).json()["session_id"] == s3


def test_exercise_last_machine_follows_latest_set_and_my_machines(auth_client, user_client, db):
    ex = ex_id(db, "하이 로우")
    a, b = (m["id"] for m in _machines(auth_client, "high row"))
    names = {m["id"]: m["name_ko"] for m in _machines(auth_client, "high row")}

    def last_machine(client=auth_client):
        row = next(e for e in client.get("/api/exercises").json() if e["id"] == ex)
        return row["last_machine_id"], row["last_machine_name"]

    assert last_machine() == (None, None)
    _ok(post_set(auth_client, date="2026-07-01", exercise_id=ex, weight_kg=100, reps=5, machine_id=a))
    assert last_machine() == (a, names[a])
    _ok(post_set(auth_client, date="2026-07-02", exercise_id=ex, weight_kg=70, reps=5, machine_id=b))
    assert last_machine() == (b, names[b]), "가장 최근 세트의 머신"
    assert last_machine(user_client) == (None, None), "다른 사용자에게는 보이지 않는다"

    # 내 머신에서 빼면 그 머신의 세트는 건너뛰고 그 전 기록의 머신이 기본값이 된다
    auth_client.delete(f"/api/me/machines/{b}")
    assert last_machine() == (a, names[a])
    # 가장 최근 세트에 머신이 없으면 기본값도 없다
    _ok(post_set(auth_client, date="2026-07-03", exercise_id=ex, weight_kg=70, reps=5))
    assert last_machine() == (None, None)


# ---- 머신 → 종목 후보 -------------------------------------------------------


def test_machine_exercises_used_and_suggested(auth_client, user_client, db):
    high_row = ex_id(db, "하이 로우")
    seated_row = ex_id(db, "시티드 로우 머신")
    m = machine_id(db, "Torque High Row (T-HR)")

    fresh = auth_client.get(f"/api/machines/{m}/exercises").json()
    assert_keys(fresh, MACHINE_EXERCISES_KEYS, "machine exercises")
    assert_keys(fresh["machine"], MACHINE_KEYS, "machine")
    assert fresh["used"] == []
    assert fresh["suggested"][0] == high_row, "모델명과 종목명이 맞는 종목이 첫 추천"
    assert seated_row in fresh["suggested"]

    s1 = add_session(db, "2026-07-01")
    add_set(db, s1, seated_row, 80, 10, machine=m)
    s2 = add_session(db, "2026-07-05")
    add_set(db, s2, high_row, 100, 8, machine=m)
    add_set(db, s2, high_row, 100, 8, machine=m)
    body = auth_client.get(f"/api/machines/{m}/exercises").json()
    for u in body["used"]:
        assert_keys(u, MACHINE_USE_KEYS, "used")
    assert [(u["exercise_id"], u["set_count"], u["last_date"]) for u in body["used"]] == [
        (high_row, 2, "2026-07-05"), (seated_row, 1, "2026-07-01"),
    ]
    assert not {high_row, seated_row} & set(body["suggested"]), "기록한 종목은 추천에서 빠진다"

    # 다른 사용자: 내 사용 이력은 used에 안 나오지만 추천 순위는 올린다
    other = user_client.get(f"/api/machines/{m}/exercises").json()
    assert other["used"] == []
    assert set(other["suggested"][:2]) == {high_row, seated_row}

    # 숨긴 종목은 기록이 있어도 후보에서 빠진다
    auth_client.patch(f"/api/exercises/{seated_row}", json={"is_archived": True})
    assert [u["exercise_id"] for u in auth_client.get(f"/api/machines/{m}/exercises").json()["used"]] == [high_row]

    assert auth_client.get("/api/machines/999999/exercises").status_code == 404


def test_machine_exercises_for_multipurpose_cable(auth_client, db):
    """참고 타겟이 없는 케이블 장비는 케이블 종목을 내가 자주 한 순으로 추천한다."""
    pulley = machine_id(db, "Dual Adjustable Pulley with Stabilization")
    curl = ex_id(db, "케이블 컬")
    s = add_session(db, "2026-07-01")
    for _ in range(5):
        add_set(db, s, curl, 20, 12)
    body = auth_client.get(f"/api/machines/{pulley}/exercises").json()
    assert body["machine"]["target"] is None
    assert body["suggested"][0] == curl
    tags = {e["id"]: e["tags"] for e in auth_client.get("/api/exercises").json()}
    assert all("케이블" in tags[i] for i in body["suggested"])
