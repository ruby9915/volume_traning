"""프론트 계약(frontend/src/api/types.ts) 회귀 테스트 — sessions.

목적: GET /api/sessions(목록)·GET /api/sessions/{id}(상세) 응답의 **키 집합**이
types.ts(SessionSummary·SessionDetail·SessionSetRecord)와 갈라지면 pytest가
즉시 잡는다 (프론트 백지 사고 방지 — test_stats_contract.py와 같은 패턴).

주부위(main_region) 판정 규칙 (§3.4 region 6분류 기준):
- 그 세션 세트들의 가중 볼륨(primary 1.0 / secondary 0.5, 웜업 제외)을
  region별 합산해 최대 region.
- 동률이면 region 내 최대 단일 종목 가중 볼륨이 큰 쪽, 그래도 같으면
  고정 region 순서(chest→back→shoulders→arms→legs→core) — 항상 결정적.
- 유효 세트가 없으면 main_region·main_region_ko 둘 다 null.
"""

from helpers import assert_keys, post_set, seed_exercise_id

# ---- types.ts 정본 키 집합 -------------------------------------------------

SESSION_SUMMARY_KEYS = {
    "id", "date", "note", "total_volume", "exercise_count", "set_count",
    "main_region", "main_region_ko",
}
SESSION_DETAIL_KEYS = SESSION_SUMMARY_KEYS | {"created_at", "exercises"}
EXERCISE_GROUP_KEYS = {"exercise_id", "name_ko", "sets"}
SESSION_SET_KEYS = {
    "id", "client_id", "set_index", "weight_kg", "reps", "is_warmup",
    "volume_kg", "note", "created_at",
    "intent_muscle", "intent_muscle_ko",  # §3.7
}
# types.ts WorkoutSet — POST /api/sets(201·멱등 200)·PATCH /api/sets/{id} 응답
WORKOUT_SET_KEYS = {
    "id", "client_id", "session_id", "exercise_id", "set_index", "weight_kg",
    "reps", "is_warmup", "note", "created_at", "volume_kg",
    "is_weight_pr", "is_e1rm_pr",
    "intent_muscle", "intent_muscle_ko",  # §3.7
}
REGIONS = {"chest", "back", "shoulders", "arms", "legs", "core"}
REGION_NAMES_KO = {
    "chest": "가슴", "back": "등", "shoulders": "어깨",
    "arms": "팔", "legs": "하체", "core": "코어",
}


# ---- helpers ---------------------------------------------------------------


def _post_set(client, **kwargs):
    """post_set + 201 단언 + json 반환 (이 모듈의 세트 생성은 전부 성공 경로)."""
    res = post_set(client, **kwargs)
    assert res.status_code == 201, res.text
    return res.json()


def _assert_region_fields(obj, label):
    assert obj["main_region"] is None or obj["main_region"] in REGIONS, label
    if obj["main_region"] is None:
        assert obj["main_region_ko"] is None, label
    else:
        assert obj["main_region_ko"] == REGION_NAMES_KO[obj["main_region"]], label


# ---- 응답 키 계약 ----------------------------------------------------------


def test_session_list_contract(auth_client):
    ex = seed_exercise_id("벤치프레스")
    _post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10)
    _post_set(
        auth_client, date="2026-07-21", exercise_id=ex, weight_kg=40, reps=10,
        is_warmup=True,
    )

    sessions = auth_client.get("/api/sessions").json()
    assert sessions, "세션이 비어 계약 검증이 무의미"
    for i, s in enumerate(sessions):
        assert_keys(s, SESSION_SUMMARY_KEYS, f"sessions[{i}]")
        _assert_region_fields(s, f"sessions[{i}]")


def test_session_detail_contract(auth_client):
    ex = seed_exercise_id("벤치프레스")
    created = _post_set(
        auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10
    )
    detail = auth_client.get(f"/api/sessions/{created['session_id']}").json()
    assert_keys(detail, SESSION_DETAIL_KEYS, "detail")
    _assert_region_fields(detail, "detail")
    for i, g in enumerate(detail["exercises"]):
        assert_keys(g, EXERCISE_GROUP_KEYS, f"detail.exercises[{i}]")
        for j, st in enumerate(g["sets"]):
            assert_keys(st, SESSION_SET_KEYS, f"detail.exercises[{i}].sets[{j}]")
    # 목록 요약과 상세의 주부위는 같은 판정
    listed = auth_client.get("/api/sessions").json()[0]
    assert (listed["main_region"], listed["main_region_ko"]) == (
        detail["main_region"], detail["main_region_ko"],
    )


def test_set_save_and_patch_contract(auth_client):
    """POST(201)·멱등 재전송(200)·PATCH 응답의 키 집합이 전부 동일해야 한다."""
    import uuid as _uuid

    ex = seed_exercise_id("데드리프트")
    payload = {
        "client_id": str(_uuid.uuid4()),
        "date": "2026-07-21",
        "exercise_id": ex,
        "weight_kg": 100,
        "reps": 5,
        "intent_muscle": "hamstrings",
    }
    first = auth_client.post("/api/sets", json=payload)
    assert first.status_code == 201, first.text
    assert_keys(first.json(), WORKOUT_SET_KEYS, "post")
    assert first.json()["intent_muscle"] == "hamstrings"
    assert first.json()["intent_muscle_ko"] == "햄스트링"

    replay = auth_client.post("/api/sets", json=payload)
    assert replay.status_code == 200, replay.text
    assert_keys(replay.json(), WORKOUT_SET_KEYS, "replay")
    assert replay.json()["intent_muscle"] == "hamstrings"

    patched = auth_client.patch(f"/api/sets/{first.json()['id']}", json={"reps": 6})
    assert patched.status_code == 200, patched.text
    assert_keys(patched.json(), WORKOUT_SET_KEYS, "patch")

    # intent 미지정 세트는 두 필드 다 null
    plain = _post_set(
        auth_client, date="2026-07-21", exercise_id=ex, weight_kg=100, reps=5
    )
    assert (plain["intent_muscle"], plain["intent_muscle_ko"]) == (None, None)


def test_session_patch_contract(auth_client):
    ex = seed_exercise_id("벤치프레스")
    created = _post_set(
        auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10
    )
    res = auth_client.patch(
        f"/api/sessions/{created['session_id']}", json={"note": "오전"}
    )
    assert res.status_code == 200, res.text
    assert_keys(res.json(), SESSION_SUMMARY_KEYS, "patched")


# ---- 주부위 판정 로직 ------------------------------------------------------


def test_main_region_bench_session_is_chest(auth_client):
    # 벤치프레스: primary chest(1.0), secondary triceps·shoulders(각 0.5)
    # → chest 1.0 > arms 0.5 = shoulders 0.5
    ex = seed_exercise_id("벤치프레스")
    created = _post_set(
        auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10
    )
    _post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=80, reps=8)

    listed = auth_client.get("/api/sessions").json()[0]
    assert listed["main_region"] == "chest"
    assert listed["main_region_ko"] == "가슴"
    detail = auth_client.get(f"/api/sessions/{created['session_id']}").json()
    assert (detail["main_region"], detail["main_region_ko"]) == ("chest", "가슴")


def test_main_region_uses_weighted_volume_across_regions(auth_client):
    # 벤치프레스 60×10=600 → chest 600, triceps(secondary)로 arms에 300
    # 바벨 컬 50×10=500: primary biceps + secondary forearms(0.5), 둘 다 arms → 750
    # → arms 1050 > chest 600 → 주부위 arms
    bench = seed_exercise_id("벤치프레스")
    curl = seed_exercise_id("바벨 컬")
    _post_set(auth_client, date="2026-07-21", exercise_id=bench, weight_kg=60, reps=10)
    _post_set(auth_client, date="2026-07-21", exercise_id=curl, weight_kg=50, reps=10)

    listed = auth_client.get("/api/sessions").json()[0]
    assert listed["main_region"] == "arms"
    assert listed["main_region_ko"] == "팔"


def test_main_region_excludes_warmup(auth_client):
    # 웜업 스쿼트 200×10은 제외 → 유효 세트는 벤치뿐 → chest
    bench = seed_exercise_id("벤치프레스")
    squat = seed_exercise_id("백스쿼트")
    _post_set(
        auth_client, date="2026-07-21", exercise_id=squat, weight_kg=200, reps=10,
        is_warmup=True,
    )
    _post_set(auth_client, date="2026-07-21", exercise_id=bench, weight_kg=60, reps=10)

    listed = auth_client.get("/api/sessions").json()[0]
    assert listed["main_region"] == "chest"


def test_main_region_tie_prefers_bigger_single_exercise(auth_client):
    # 케이블 크로스오버(chest만) 100×10 → chest 1000
    # 레그 컬 50×10 + 레그 익스텐션 50×10 (각각 단일 primary) → legs 1000
    # region 동률 → 최대 단일 종목 볼륨 큰 chest(1000 > 500)
    crossover = seed_exercise_id("케이블 크로스오버")
    leg_curl = seed_exercise_id("레그 컬")
    leg_ext = seed_exercise_id("레그 익스텐션")
    _post_set(
        auth_client, date="2026-07-21", exercise_id=crossover, weight_kg=100, reps=10
    )
    _post_set(
        auth_client, date="2026-07-21", exercise_id=leg_curl, weight_kg=50, reps=10
    )
    _post_set(
        auth_client, date="2026-07-21", exercise_id=leg_ext, weight_kg=50, reps=10
    )

    listed = auth_client.get("/api/sessions").json()[0]
    assert listed["main_region"] == "chest"


def test_main_region_null_when_no_working_sets(auth_client):
    # 웜업만 있는 세션 → 유효 세트 없음 → null
    bench = seed_exercise_id("벤치프레스")
    created = _post_set(
        auth_client, date="2026-07-21", exercise_id=bench, weight_kg=40, reps=10,
        is_warmup=True,
    )
    listed = auth_client.get("/api/sessions").json()[0]
    assert (listed["main_region"], listed["main_region_ko"]) == (None, None)
    detail = auth_client.get(f"/api/sessions/{created['session_id']}").json()
    assert (detail["main_region"], detail["main_region_ko"]) == (None, None)

    # 세트를 전부 지운 빈 세션도 null
    assert auth_client.delete(f"/api/sets/{created['id']}").status_code == 204
    listed = auth_client.get("/api/sessions").json()[0]
    assert (listed["main_region"], listed["main_region_ko"]) == (None, None)
