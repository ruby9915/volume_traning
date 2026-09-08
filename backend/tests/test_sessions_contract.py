"""프론트 계약(frontend/src/api/types.ts) 회귀 테스트 — sessions.

목적: GET /api/sessions(목록)·GET /api/sessions/{id}(상세) 응답의 **키 집합**이
types.ts(SessionSummary·SessionDetail·SessionSetRecord)와 갈라지면 pytest가
즉시 잡는다 (프론트 백지 사고 방지 — test_stats_contract.py와 같은 패턴).

부위 라벨 판정 규칙 (§10.2):
- 세트 타겟을 부위(region)로 합산(웜업 제외, 100% 귀속). 볼륨 1위 부위가 main_region.
- 2위가 세션 볼륨의 25% 이상이면 region_label에 "1위·2위"로 함께 표시.
- 동률은 고정 부위 순서(chest→back→shoulders→arms→legs→core) — 항상 결정적.
- 유효 세트가 없으면 셋 다 null.
"""

from app.seed_data.targets import REGION_NAMES_KO
from helpers import assert_keys, post_set, seed_exercise_id

# ---- types.ts 정본 키 집합 -------------------------------------------------

SESSION_SUMMARY_KEYS = {
    "id", "date", "note", "total_volume", "exercise_count", "set_count",
    "main_region", "main_region_ko", "region_label",
}
SESSION_DETAIL_KEYS = SESSION_SUMMARY_KEYS | {"created_at", "exercises"}
EXERCISE_GROUP_KEYS = {"exercise_id", "name_ko", "default_target", "sets"}
SESSION_SET_KEYS = {
    "id", "client_id", "set_index", "weight_kg", "reps", "is_warmup",
    "volume_kg", "note", "created_at", "target", "target_ko",
}
# types.ts WorkoutSet — POST /api/sets(201·멱등 200)·PATCH /api/sets/{id} 응답
WORKOUT_SET_KEYS = {
    "id", "client_id", "session_id", "exercise_id", "set_index", "weight_kg",
    "reps", "is_warmup", "note", "created_at", "volume_kg",
    "is_weight_pr", "is_e1rm_pr", "target", "target_ko",
}
REGIONS = set(REGION_NAMES_KO)


def _post_set(client, **kwargs):
    res = post_set(client, **kwargs)
    assert res.status_code == 201, res.text
    return res.json()


def _assert_region_fields(obj, label):
    assert obj["main_region"] is None or obj["main_region"] in REGIONS, label
    if obj["main_region"] is None:
        assert obj["main_region_ko"] is None and obj["region_label"] is None, label
    else:
        assert obj["main_region_ko"] == REGION_NAMES_KO[obj["main_region"]], label
        assert obj["region_label"].startswith(obj["main_region_ko"]), label


# ---- 응답 키 계약 ----------------------------------------------------------


def test_session_list_contract(auth_client):
    ex = seed_exercise_id("벤치프레스")
    _post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10)
    _post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=40, reps=10, is_warmup=True)
    sessions = auth_client.get("/api/sessions").json()
    assert sessions
    for i, s in enumerate(sessions):
        assert_keys(s, SESSION_SUMMARY_KEYS, f"sessions[{i}]")
        _assert_region_fields(s, f"sessions[{i}]")


def test_session_detail_contract(auth_client):
    ex = seed_exercise_id("벤치프레스")
    created = _post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10)
    detail = auth_client.get(f"/api/sessions/{created['session_id']}").json()
    assert_keys(detail, SESSION_DETAIL_KEYS, "detail")
    _assert_region_fields(detail, "detail")
    for i, g in enumerate(detail["exercises"]):
        assert_keys(g, EXERCISE_GROUP_KEYS, f"detail.exercises[{i}]")
        for j, st in enumerate(g["sets"]):
            assert_keys(st, SESSION_SET_KEYS, f"detail.exercises[{i}].sets[{j}]")
    listed = auth_client.get("/api/sessions").json()[0]
    assert (listed["main_region"], listed["region_label"]) == (detail["main_region"], detail["region_label"])


def test_set_save_and_patch_contract(auth_client):
    import uuid as _uuid

    ex = seed_exercise_id("데드리프트")
    payload = {
        "client_id": str(_uuid.uuid4()), "date": "2026-07-21", "exercise_id": ex,
        "weight_kg": 100, "reps": 5, "target": "hamstrings",
    }
    first = auth_client.post("/api/sets", json=payload)
    assert first.status_code == 201, first.text
    assert_keys(first.json(), WORKOUT_SET_KEYS, "post")
    assert (first.json()["target"], first.json()["target_ko"]) == ("hamstrings", "햄스트링")

    replay = auth_client.post("/api/sets", json=payload)
    assert replay.status_code == 200, replay.text
    assert_keys(replay.json(), WORKOUT_SET_KEYS, "replay")

    patched = auth_client.patch(f"/api/sets/{first.json()['id']}", json={"reps": 6})
    assert patched.status_code == 200, patched.text
    assert_keys(patched.json(), WORKOUT_SET_KEYS, "patch")

    # 타겟 미지정 세트는 종목 기본 타겟 (null 아님)
    plain = _post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=100, reps=5)
    assert (plain["target"], plain["target_ko"]) == ("glutes", "둔근")


def test_session_patch_contract(auth_client):
    ex = seed_exercise_id("벤치프레스")
    created = _post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10)
    res = auth_client.patch(f"/api/sessions/{created['session_id']}", json={"note": "오전"})
    assert res.status_code == 200, res.text
    assert_keys(res.json(), SESSION_SUMMARY_KEYS, "patched")


# ---- 부위 라벨 판정 로직 ----------------------------------------------------


def test_region_label_single(auth_client):
    ex = seed_exercise_id("벤치프레스")
    created = _post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=60, reps=10)
    _post_set(auth_client, date="2026-07-21", exercise_id=ex, weight_kg=80, reps=8)
    listed = auth_client.get("/api/sessions").json()[0]
    assert (listed["main_region"], listed["main_region_ko"], listed["region_label"]) == ("chest", "가슴", "가슴")
    detail = auth_client.get(f"/api/sessions/{created['session_id']}").json()
    assert detail["region_label"] == "가슴"


def test_region_label_two_regions_when_second_is_significant(auth_client):
    # 벤치 60×10=600 → chest 600 / 바벨 컬 50×10=500 → arms 500 (45%) → "가슴·팔"
    bench = seed_exercise_id("벤치프레스")
    curl = seed_exercise_id("바벨 컬")
    _post_set(auth_client, date="2026-07-21", exercise_id=bench, weight_kg=60, reps=10)
    _post_set(auth_client, date="2026-07-21", exercise_id=curl, weight_kg=50, reps=10)
    listed = auth_client.get("/api/sessions").json()[0]
    assert listed["main_region"] == "chest"
    assert listed["region_label"] == "가슴·팔"


def test_region_label_hides_minor_second_region(auth_client):
    # 벤치 100×10=1000 chest / 컬 10×10=100 arms (9%) → "가슴"만
    bench = seed_exercise_id("벤치프레스")
    curl = seed_exercise_id("바벨 컬")
    _post_set(auth_client, date="2026-07-21", exercise_id=bench, weight_kg=100, reps=10)
    _post_set(auth_client, date="2026-07-21", exercise_id=curl, weight_kg=10, reps=10)
    assert auth_client.get("/api/sessions").json()[0]["region_label"] == "가슴"


def test_region_label_follows_set_target_not_exercise_default(auth_client):
    # 벤치프레스지만 타겟을 삼두(arms)로 기록 → 부위 라벨도 팔
    bench = seed_exercise_id("벤치프레스")
    _post_set(auth_client, date="2026-07-21", exercise_id=bench, weight_kg=60, reps=10, target="triceps")
    listed = auth_client.get("/api/sessions").json()[0]
    assert (listed["main_region"], listed["region_label"]) == ("arms", "팔")


def test_region_label_excludes_warmup(auth_client):
    bench = seed_exercise_id("벤치프레스")
    squat = seed_exercise_id("백스쿼트")
    _post_set(auth_client, date="2026-07-21", exercise_id=squat, weight_kg=200, reps=10, is_warmup=True)
    _post_set(auth_client, date="2026-07-21", exercise_id=bench, weight_kg=60, reps=10)
    assert auth_client.get("/api/sessions").json()[0]["region_label"] == "가슴"


def test_region_label_tie_uses_fixed_order(auth_client):
    # 크로스오버 1000 chest / 레그 컬 500 + 레그 익스텐션 500 = legs 1000 → 동률 → chest 먼저, "가슴·하체"
    crossover = seed_exercise_id("케이블 크로스오버")
    leg_curl = seed_exercise_id("레그 컬")
    leg_ext = seed_exercise_id("레그 익스텐션")
    _post_set(auth_client, date="2026-07-21", exercise_id=crossover, weight_kg=100, reps=10)
    _post_set(auth_client, date="2026-07-21", exercise_id=leg_curl, weight_kg=50, reps=10)
    _post_set(auth_client, date="2026-07-21", exercise_id=leg_ext, weight_kg=50, reps=10)
    listed = auth_client.get("/api/sessions").json()[0]
    assert (listed["main_region"], listed["region_label"]) == ("chest", "가슴·하체")


def test_region_label_null_when_no_working_sets(auth_client):
    bench = seed_exercise_id("벤치프레스")
    created = _post_set(auth_client, date="2026-07-21", exercise_id=bench, weight_kg=40, reps=10, is_warmup=True)
    listed = auth_client.get("/api/sessions").json()[0]
    assert (listed["main_region"], listed["main_region_ko"], listed["region_label"]) == (None, None, None)
    assert auth_client.delete(f"/api/sets/{created['id']}").status_code == 204
    listed = auth_client.get("/api/sessions").json()[0]
    assert listed["region_label"] is None
