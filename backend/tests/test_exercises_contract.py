"""Exercise 응답 계약(frontend/src/api/types.ts의 Exercise) 회귀 테스트.

§3.6 속성 6필드가 목록·생성·수정·복원 응답 전부에서 항상 존재해야 한다
(프론트가 undefined를 읽는 사고 방지). 키 집합만 보는 구조 검증 +
속성 write 경로의 최소 동작 검증.
"""

EXERCISE_KEYS = {
    "id", "name_ko", "name_en", "bodyweight_factor", "load_multiplier",
    "is_builtin", "is_archived", "note", "muscles",
    # §3.6 속성 6필드
    "base_movement", "equipment", "support", "grip", "angle", "aliases",
}
MUSCLE_KEYS = {"code", "role"}
ATTR_FIELDS = ("base_movement", "equipment", "support", "grip", "angle", "aliases")


def _assert_exercise_shape(obj, label):
    assert isinstance(obj, dict), f"{label}: dict가 아님"
    assert set(obj.keys()) == EXERCISE_KEYS, (
        f"{label} 키 불일치 — 누락 {EXERCISE_KEYS - set(obj)}, 초과 {set(obj) - EXERCISE_KEYS}"
    )
    for i, m in enumerate(obj["muscles"]):
        assert set(m.keys()) == MUSCLE_KEYS, f"{label}.muscles[{i}] 키 불일치"


def test_list_contract(auth_client):
    res = auth_client.get("/api/exercises")
    assert res.status_code == 200, res.text
    data = res.json()
    assert len(data) == 45
    for ex in data:
        _assert_exercise_shape(ex, ex["name_ko"])

    # 시드 백필 대표값 — 명백한 것만 채워졌는지 (§3.6)
    by_name = {e["name_ko"]: e for e in data}
    bench = by_name["벤치프레스"]
    assert bench["base_movement"] == "벤치프레스"
    assert bench["equipment"] == "바벨"
    assert bench["support"] is None and bench["grip"] is None and bench["angle"] is None

    incline = by_name["인클라인 벤치프레스"]
    assert incline["base_movement"] == "벤치프레스"
    assert incline["angle"] == "인클라인"

    ohp = by_name["오버헤드 프레스"]
    assert ohp["base_movement"] is None  # 프레스 base 통합은 애매 판정 — NULL
    assert ohp["equipment"] == "바벨"
    assert ohp["aliases"] == "숄더프레스,밀리터리 프레스"

    seated_row = by_name["시티드 케이블 로우"]
    assert seated_row["base_movement"] == "로우"
    assert seated_row["equipment"] == "케이블"
    assert seated_row["support"] == "시티드"
    assert seated_row["aliases"] == "시티드 로우"

    # 애매 판정 종목은 전부 NULL
    dips = by_name["딥스"]
    assert all(dips[f] is None for f in ATTR_FIELDS)
    leg_curl = by_name["레그 컬"]
    assert leg_curl["base_movement"] is None  # 이름만 '컬' — 이두 컬 계열에 합치지 않음
    assert leg_curl["equipment"] == "머신"


def test_create_with_attributes_contract(auth_client):
    res = auth_client.post(
        "/api/exercises",
        json={
            "name_ko": "클로즈 그립 벤치프레스",
            "muscles": [{"code": "triceps", "role": "primary"}],
            "base_movement": "벤치프레스",
            "equipment": "바벨",
            "grip": "클로즈",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    _assert_exercise_shape(body, "created")
    assert body["base_movement"] == "벤치프레스"
    assert body["equipment"] == "바벨"
    assert body["grip"] == "클로즈"
    assert body["support"] is None and body["angle"] is None and body["aliases"] is None


def test_create_without_attributes_defaults_null(auth_client):
    res = auth_client.post(
        "/api/exercises",
        json={"name_ko": "속성 없는 종목", "muscles": [{"code": "abs", "role": "primary"}]},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    _assert_exercise_shape(body, "created")
    assert all(body[f] is None for f in ATTR_FIELDS)


def test_patch_attributes_set_and_clear(auth_client):
    bench = next(
        e for e in auth_client.get("/api/exercises").json() if e["name_ko"] == "벤치프레스"
    )
    res = auth_client.patch(
        f"/api/exercises/{bench['id']}", json={"grip": "와이드", "equipment": "스미스머신"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_exercise_shape(body, "patched")
    assert body["grip"] == "와이드"
    assert body["equipment"] == "스미스머신"
    assert body["base_movement"] == "벤치프레스"  # 언급 안 한 속성은 유지

    # null 전송 = 값 비우기
    res = auth_client.patch(f"/api/exercises/{bench['id']}", json={"grip": None})
    assert res.status_code == 200, res.text
    assert res.json()["grip"] is None

    # 빈 문자열은 422 (min_length=1 — 빈 값은 null로)
    res = auth_client.patch(f"/api/exercises/{bench['id']}", json={"grip": ""})
    assert res.status_code == 422


def test_delete_response_contract(auth_client):
    """types.ts ExerciseDeleteResponse: {deleted, archived} — 키 집합 완전 일치."""
    # hard delete 경로 (세트 없음)
    created = auth_client.post(
        "/api/exercises",
        json={"name_ko": "삭제 계약 확인", "muscles": [{"code": "abs", "role": "primary"}]},
    ).json()
    res = auth_client.delete(f"/api/exercises/{created['id']}")
    assert res.status_code == 200, res.text
    assert res.json() == {"deleted": True, "archived": False}


def test_archived_conflict_detail_contract(auth_client):
    """types.ts ArchivedConflictDetail: 409 + detail {code, exercise_id, name_ko}."""
    created = auth_client.post(
        "/api/exercises",
        json={"name_ko": "충돌 계약 확인", "muscles": [{"code": "abs", "role": "primary"}]},
    ).json()
    auth_client.patch(f"/api/exercises/{created['id']}", json={"is_archived": True})

    res = auth_client.post(
        "/api/exercises",
        json={"name_ko": "충돌 계약 확인", "muscles": [{"code": "abs", "role": "primary"}]},
    )
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert set(detail.keys()) == {"code", "exercise_id", "name_ko"}
    assert detail["code"] == "archived_exists"
    assert detail["exercise_id"] == created["id"]
    assert detail["name_ko"] == "충돌 계약 확인"


def test_restore_response_contract(auth_client):
    created = auth_client.post(
        "/api/exercises",
        json={"name_ko": "복원 계약 확인", "muscles": [{"code": "abs", "role": "primary"}]},
    ).json()
    auth_client.patch(f"/api/exercises/{created['id']}", json={"is_archived": True})
    res = auth_client.post(f"/api/exercises/{created['id']}/restore")
    assert res.status_code == 200, res.text
    _assert_exercise_shape(res.json(), "restored")
