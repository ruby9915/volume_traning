import uuid

from helpers import post_set, seed_exercise_id


# ---------- 인증 ----------

def test_requires_auth(client):
    assert client.get("/api/sessions").status_code == 401
    assert client.post("/api/sets", json={}).status_code == 401
    assert client.get("/api/bodyweight").status_code == 401


def test_token_without_exp_rejected(client):
    import jwt as pyjwt

    from app.config import get_settings

    token = pyjwt.encode({}, get_settings().JWT_SECRET, algorithm="HS256")
    client.headers["Authorization"] = f"Bearer {token}"
    assert client.get("/api/sessions").status_code == 401


def test_retroactive_set_pr_compares_by_date(auth_client):
    # 미래 날짜 세트를 먼저 입력해도, 과거 날짜 소급 입력은 그 이전 날짜와만 비교
    ex = seed_exercise_id("벤치프레스")
    post_set(auth_client, date="2026-07-10", exercise_id=ex, weight_kg=100, reps=5)
    post_set(auth_client, date="2026-07-16", exercise_id=ex, weight_kg=120, reps=5)
    retro = post_set(auth_client, date="2026-07-12", exercise_id=ex, weight_kg=110, reps=5).json()
    assert retro["is_weight_pr"] is True  # 07-12 시점 기준 110 > 100 (07-16의 120은 미래)


# ---------- POST /api/sets: 멱등성 ----------

def test_client_id_idempotent(auth_client):
    ex = seed_exercise_id("벤치프레스")
    cid = str(uuid.uuid4())
    payload = {
        "client_id": cid,
        "date": "2026-07-19",
        "exercise_id": ex,
        "weight_kg": 60,
        "reps": 8,
    }
    first = auth_client.post("/api/sets", json=payload)
    assert first.status_code == 201, first.text
    second = auth_client.post("/api/sets", json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]

    sessions = auth_client.get("/api/sessions").json()
    assert len(sessions) == 1
    assert sessions[0]["set_count"] == 1


# ---------- POST /api/sets: lazy 세션 ----------

def test_lazy_session_reuse_and_new_session(auth_client):
    ex = seed_exercise_id("벤치프레스")
    s1 = post_set(auth_client, date="2026-07-19", exercise_id=ex, weight_kg=60, reps=8).json()
    s2 = post_set(auth_client, date="2026-07-19", exercise_id=ex, weight_kg=60, reps=8).json()
    assert s2["session_id"] == s1["session_id"]
    assert (s1["set_index"], s2["set_index"]) == (1, 2)

    s3 = post_set(
        auth_client, date="2026-07-19", exercise_id=ex, weight_kg=60, reps=8,
        new_session=True,
    ).json()
    assert s3["session_id"] != s1["session_id"]
    assert s3["set_index"] == 1

    s4 = post_set(auth_client, date="2026-07-19", exercise_id=ex, weight_kg=60, reps=8).json()
    assert s4["session_id"] == s3["session_id"]

    other = post_set(auth_client, date="2026-07-20", exercise_id=ex, weight_kg=60, reps=8).json()
    assert other["session_id"] not in (s1["session_id"], s3["session_id"])

    assert len(auth_client.get("/api/sessions").json()) == 3


def test_unknown_exercise_404(auth_client):
    res = post_set(auth_client, date="2026-07-19", exercise_id=99999, weight_kg=60, reps=8)
    assert res.status_code == 404
    assert auth_client.get("/api/sessions").json() == []


# ---------- POST /api/sets: volume_kg (set_volume VIEW) ----------

def test_volume_plain_barbell(auth_client):
    ex = seed_exercise_id("벤치프레스")
    res = post_set(auth_client, date="2026-07-19", exercise_id=ex, weight_kg=60, reps=8).json()
    assert res["volume_kg"] == 480


def test_volume_multiplier_and_bodyweight(auth_client):
    assert auth_client.post(
        "/api/bodyweight", json={"date": "2026-07-18", "weight_kg": 80}
    ).status_code == 200

    dumbbell = seed_exercise_id("덤벨 벤치프레스")  # load_multiplier=2
    res = post_set(auth_client, date="2026-07-19", exercise_id=dumbbell, weight_kg=20, reps=10).json()
    assert res["volume_kg"] == 400

    pullup = seed_exercise_id("풀업")  # bodyweight_factor=1.0
    res = post_set(auth_client, date="2026-07-19", exercise_id=pullup, weight_kg=5, reps=10).json()
    assert res["volume_kg"] == 850


# ---------- PR 플래그 ----------

def test_first_session_is_baseline_no_pr(auth_client):
    ex = seed_exercise_id("벤치프레스")
    s1 = post_set(auth_client, date="2026-07-10", exercise_id=ex, weight_kg=100, reps=5).json()
    assert (s1["is_weight_pr"], s1["is_e1rm_pr"]) == (False, False)
    s2 = post_set(auth_client, date="2026-07-10", exercise_id=ex, weight_kg=110, reps=5).json()
    assert (s2["is_weight_pr"], s2["is_e1rm_pr"]) == (False, False)


def test_pr_flags_second_session(auth_client):
    ex = seed_exercise_id("벤치프레스")
    post_set(auth_client, date="2026-07-10", exercise_id=ex, weight_kg=100, reps=5)
    # e1RM 베이스라인 = 100*(1+5/30) = 116.67

    heavier = post_set(auth_client, date="2026-07-12", exercise_id=ex, weight_kg=105, reps=5).json()
    assert heavier["is_weight_pr"] is True
    assert heavier["is_e1rm_pr"] is True  # 105*(1+5/30)=122.5 > 116.67

    # 같은 세션 연속 갱신도 세트마다 뱃지
    heavier2 = post_set(auth_client, date="2026-07-12", exercise_id=ex, weight_kg=107.5, reps=5).json()
    assert heavier2["is_weight_pr"] is True

    # 중량은 낮지만 e1RM만 갱신: 95*(1+12/30)=133 > 125.42
    e1rm_only = post_set(auth_client, date="2026-07-12", exercise_id=ex, weight_kg=95, reps=12).json()
    assert e1rm_only["is_weight_pr"] is False
    assert e1rm_only["is_e1rm_pr"] is True

    lower = post_set(auth_client, date="2026-07-12", exercise_id=ex, weight_kg=90, reps=5).json()
    assert (lower["is_weight_pr"], lower["is_e1rm_pr"]) == (False, False)


def test_tie_is_not_pr(auth_client):
    ex = seed_exercise_id("벤치프레스")
    post_set(auth_client, date="2026-07-10", exercise_id=ex, weight_kg=100, reps=5)
    tie = post_set(auth_client, date="2026-07-12", exercise_id=ex, weight_kg=100, reps=5).json()
    assert (tie["is_weight_pr"], tie["is_e1rm_pr"]) == (False, False)


def test_warmup_never_pr_and_not_baseline_max(auth_client):
    ex = seed_exercise_id("벤치프레스")
    post_set(auth_client, date="2026-07-10", exercise_id=ex, weight_kg=100, reps=5)

    warmup = post_set(
        auth_client, date="2026-07-12", exercise_id=ex, weight_kg=200, reps=5,
        is_warmup=True,
    ).json()
    assert (warmup["is_weight_pr"], warmup["is_e1rm_pr"]) == (False, False)

    # 웜업 200은 비교 기준에 안 들어감 → 105는 여전히 PR
    work = post_set(auth_client, date="2026-07-12", exercise_id=ex, weight_kg=105, reps=5).json()
    assert work["is_weight_pr"] is True


def test_weight_zero_excluded_from_pr(auth_client):
    pullup = seed_exercise_id("풀업")
    post_set(auth_client, date="2026-07-10", exercise_id=pullup, weight_kg=0, reps=5)
    s = post_set(auth_client, date="2026-07-12", exercise_id=pullup, weight_kg=0, reps=10).json()
    assert (s["is_weight_pr"], s["is_e1rm_pr"]) == (False, False)


def test_e1rm_requires_reps_le_12(auth_client):
    ex = seed_exercise_id("벤치프레스")
    post_set(auth_client, date="2026-07-10", exercise_id=ex, weight_kg=100, reps=5)
    high_rep = post_set(auth_client, date="2026-07-12", exercise_id=ex, weight_kg=99, reps=20).json()
    assert high_rep["is_e1rm_pr"] is False
    assert high_rep["is_weight_pr"] is False


def test_pr_scoped_per_exercise(auth_client):
    bench = seed_exercise_id("벤치프레스")
    squat = seed_exercise_id("백스쿼트")
    post_set(auth_client, date="2026-07-10", exercise_id=bench, weight_kg=100, reps=5)
    # 스쿼트는 첫 세션 → 벤치 기록과 무관하게 베이스라인
    s = post_set(auth_client, date="2026-07-12", exercise_id=squat, weight_kg=140, reps=5).json()
    assert (s["is_weight_pr"], s["is_e1rm_pr"]) == (False, False)


# ---------- PATCH/DELETE /api/sets ----------

def test_patch_set(auth_client):
    ex = seed_exercise_id("벤치프레스")
    created = post_set(auth_client, date="2026-07-19", exercise_id=ex, weight_kg=60, reps=8).json()
    res = auth_client.patch(f"/api/sets/{created['id']}", json={"weight_kg": 62.5, "reps": 6})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["weight_kg"] == 62.5
    assert body["reps"] == 6
    assert body["volume_kg"] == 375

    res = auth_client.patch(f"/api/sets/{created['id']}", json={"is_warmup": True})
    assert res.json()["is_warmup"] is True
    sessions = auth_client.get("/api/sessions").json()
    assert sessions[0]["total_volume"] == 0  # 웜업은 요약 볼륨 제외

    assert auth_client.patch("/api/sets/99999", json={"reps": 5}).status_code == 404
    assert auth_client.patch(
        f"/api/sets/{created['id']}", json={"weight_kg": 60.1}
    ).status_code == 422  # 0.25 배수 위반


def test_delete_set(auth_client):
    ex = seed_exercise_id("벤치프레스")
    created = post_set(auth_client, date="2026-07-19", exercise_id=ex, weight_kg=60, reps=8).json()
    assert auth_client.delete(f"/api/sets/{created['id']}").status_code == 204
    assert auth_client.delete(f"/api/sets/{created['id']}").status_code == 404
    assert auth_client.get("/api/sessions").json()[0]["set_count"] == 0


# ---------- GET /api/sessions ----------

def test_session_list_summary_and_filters(auth_client):
    bench = seed_exercise_id("벤치프레스")
    squat = seed_exercise_id("백스쿼트")
    post_set(auth_client, date="2026-07-10", exercise_id=bench, weight_kg=60, reps=10)
    post_set(auth_client, date="2026-07-10", exercise_id=squat, weight_kg=80, reps=10)
    post_set(auth_client, date="2026-07-10", exercise_id=bench, weight_kg=40, reps=10, is_warmup=True)
    post_set(auth_client, date="2026-07-15", exercise_id=bench, weight_kg=60, reps=10)

    sessions = auth_client.get("/api/sessions").json()
    assert [s["date"] for s in sessions] == ["2026-07-15", "2026-07-10"]
    first = sessions[1]
    assert first["total_volume"] == 1400  # 웜업 400 제외
    assert first["exercise_count"] == 2
    assert first["set_count"] == 3

    filtered = auth_client.get("/api/sessions", params={"from": "2026-07-11"}).json()
    assert [s["date"] for s in filtered] == ["2026-07-15"]
    filtered = auth_client.get("/api/sessions", params={"to": "2026-07-11"}).json()
    assert [s["date"] for s in filtered] == ["2026-07-10"]
    limited = auth_client.get("/api/sessions", params={"limit": 1, "offset": 1}).json()
    assert [s["date"] for s in limited] == ["2026-07-10"]


# ---------- GET /api/sessions/{id}: 종목 그룹핑 ----------

def test_session_detail_grouping_order(auth_client):
    bench = seed_exercise_id("벤치프레스")
    squat = seed_exercise_id("백스쿼트")
    post_set(auth_client, date="2026-07-19", exercise_id=bench, weight_kg=60, reps=8)
    post_set(auth_client, date="2026-07-19", exercise_id=squat, weight_kg=80, reps=8)
    last = post_set(auth_client, date="2026-07-19", exercise_id=bench, weight_kg=62.5, reps=6).json()

    detail = auth_client.get(f"/api/sessions/{last['session_id']}").json()
    assert [g["exercise_id"] for g in detail["exercises"]] == [bench, squat]
    bench_group = detail["exercises"][0]
    assert bench_group["name_ko"] == "벤치프레스"
    assert [s["set_index"] for s in bench_group["sets"]] == [1, 3]
    assert [s["set_index"] for s in detail["exercises"][1]["sets"]] == [2]
    assert detail["set_count"] == 3

    assert auth_client.get("/api/sessions/99999").status_code == 404


# ---------- PATCH/DELETE /api/sessions ----------

def test_patch_session(auth_client):
    ex = seed_exercise_id("벤치프레스")
    created = post_set(auth_client, date="2026-07-19", exercise_id=ex, weight_kg=60, reps=8).json()
    sid = created["session_id"]
    res = auth_client.patch(
        f"/api/sessions/{sid}", json={"date": "2026-07-18", "note": "오전 운동"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["date"] == "2026-07-18"
    assert res.json()["note"] == "오전 운동"
    assert auth_client.patch("/api/sessions/99999", json={"note": "x"}).status_code == 404
    assert auth_client.patch(
        f"/api/sessions/{sid}", json={"date": None}
    ).status_code == 422  # NOT NULL 컬럼에 명시적 null 금지


def test_delete_session_cascades_sets(auth_client):
    ex = seed_exercise_id("벤치프레스")
    created = post_set(auth_client, date="2026-07-19", exercise_id=ex, weight_kg=60, reps=8).json()
    sid = created["session_id"]
    assert auth_client.delete(f"/api/sessions/{sid}").status_code == 204
    assert auth_client.get(f"/api/sessions/{sid}").status_code == 404
    assert auth_client.get("/api/sessions").json() == []
    assert auth_client.patch(f"/api/sets/{created['id']}", json={"reps": 5}).status_code == 404


# ---------- Bodyweight ----------

def test_bodyweight_upsert_and_list(auth_client):
    r1 = auth_client.post("/api/bodyweight", json={"date": "2026-07-19", "weight_kg": 80})
    assert r1.status_code == 200, r1.text
    r2 = auth_client.post("/api/bodyweight", json={"date": "2026-07-19", "weight_kg": 81.5})
    assert r2.status_code == 200
    assert r2.json()["id"] == r1.json()["id"]

    auth_client.post("/api/bodyweight", json={"date": "2026-07-10", "weight_kg": 79})
    rows = auth_client.get("/api/bodyweight").json()
    assert [(r["date"], r["weight_kg"]) for r in rows] == [
        ("2026-07-19", 81.5),
        ("2026-07-10", 79),
    ]

    limited = auth_client.get("/api/bodyweight", params={"limit": 1}).json()
    assert len(limited) == 1

    assert auth_client.post(
        "/api/bodyweight", json={"date": "2026-7-19", "weight_kg": 80}
    ).status_code == 422
