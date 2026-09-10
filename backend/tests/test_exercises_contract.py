"""Exercise 응답 계약(frontend/src/api/types.ts의 Exercise) 회귀 테스트 (v2).

계열·태그·기본 타겟·머신·소유 필드가 목록·생성·수정·복원 응답 전부에서 항상 존재해야 한다
(프론트가 undefined를 읽는 사고 방지). 키 집합만 보는 구조 검증 + write 경로의 최소 동작 검증.
"""

from app.seed_data.exercises import EXERCISES

EXERCISE_KEYS = {
    "id", "name_ko", "name_en", "base_movement", "tags", "default_target", "default_target_ko",
    "secondary_targets", "secondary_targets_ko",  # §11.2
    "machine_id", "machine_name", "bodyweight_factor", "load_multiplier",
    "is_builtin", "is_archived", "is_own", "note", "aliases",
}
MACHINE_KEYS = {"id", "brand", "model", "name_ko", "target"}


def _assert_exercise_shape(obj, label):
    assert isinstance(obj, dict), f"{label}: dict가 아님"
    assert set(obj.keys()) == EXERCISE_KEYS, (
        f"{label} 키 불일치 — 누락 {EXERCISE_KEYS - set(obj)}, 초과 {set(obj) - EXERCISE_KEYS}"
    )
    assert isinstance(obj["tags"], list)
    assert isinstance(obj["default_target"], str) and obj["default_target"]
    assert isinstance(obj["secondary_targets"], list)
    assert len(obj["secondary_targets"]) == len(obj["secondary_targets_ko"])
    assert obj["default_target"] not in obj["secondary_targets"]


def test_list_contract(auth_client):
    res = auth_client.get("/api/exercises")
    assert res.status_code == 200, res.text
    data = res.json()
    assert len(data) == len(EXERCISES)
    for ex in data:
        _assert_exercise_shape(ex, ex["name_ko"])

    by_name = {e["name_ko"]: e for e in data}
    bench = by_name["벤치프레스"]
    assert bench["base_movement"] == "벤치프레스" and bench["tags"] == ["바벨", "플랫"]
    assert "인클라인" in by_name["인클라인 벤치프레스"]["tags"]
    assert "밀리터리 프레스" in (by_name["오버헤드 프레스"]["aliases"] or "")
    seated_row = by_name["시티드 케이블 로우"]
    assert seated_row["base_movement"] == "로우" and "시티드" in seated_row["tags"]
    assert all(e["is_own"] is False for e in data)  # 내장은 소유 없음


def test_create_with_tags_and_machine_contract(auth_client):
    machine = auth_client.post(
        "/api/machines", json={"brand": "gym80", "model": "Chest Press", "target": "chest"}
    )
    assert machine.status_code == 201, machine.text
    assert set(machine.json().keys()) == MACHINE_KEYS
    res = auth_client.post(
        "/api/exercises",
        json={
            "name_ko": "클로즈 그립 벤치프레스 2", "base_movement": "벤치프레스",
            "tags": ["바벨", "클로즈"], "default_target": "triceps", "machine_id": machine.json()["id"],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    _assert_exercise_shape(body, "created")
    assert body["tags"] == ["바벨", "클로즈"]
    assert body["machine_id"] == machine.json()["id"]
    assert body["machine_name"] == "gym80 Chest Press"
    assert body["default_target_ko"] == "삼두"


def test_create_minimal_defaults(auth_client):
    res = auth_client.post("/api/exercises", json={"name_ko": "태그 없는 종목", "default_target": "abs"})
    assert res.status_code == 201, res.text
    body = res.json()
    _assert_exercise_shape(body, "created")
    assert body["tags"] == [] and body["base_movement"] is None and body["machine_id"] is None


def test_patch_tags_set_and_clear(auth_client):
    bench = next(e for e in auth_client.get("/api/exercises").json() if e["name_ko"] == "벤치프레스")
    res = auth_client.patch(f"/api/exercises/{bench['id']}", json={"tags": ["바벨", "와이드"], "base_movement": "프레스"})
    assert res.status_code == 200, res.text
    _assert_exercise_shape(res.json(), "patched")
    assert res.json()["tags"] == ["바벨", "와이드"] and res.json()["base_movement"] == "프레스"

    res = auth_client.patch(f"/api/exercises/{bench['id']}", json={"tags": []})
    assert res.status_code == 200 and res.json()["tags"] == []
    assert auth_client.patch(f"/api/exercises/{bench['id']}", json={"base_movement": ""}).status_code == 422


def test_delete_response_contract(auth_client):
    created = auth_client.post("/api/exercises", json={"name_ko": "삭제 계약 확인", "default_target": "abs"}).json()
    res = auth_client.delete(f"/api/exercises/{created['id']}")
    assert res.status_code == 200, res.text
    assert res.json() == {"deleted": True, "archived": False}


def test_archived_conflict_detail_contract(auth_client):
    created = auth_client.post("/api/exercises", json={"name_ko": "충돌 계약 확인", "default_target": "abs"}).json()
    auth_client.patch(f"/api/exercises/{created['id']}", json={"is_archived": True})
    res = auth_client.post("/api/exercises", json={"name_ko": "충돌 계약 확인", "default_target": "abs"})
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert set(detail.keys()) == {"code", "exercise_id", "name_ko"}
    assert (detail["code"], detail["exercise_id"], detail["name_ko"]) == ("archived_exists", created["id"], "충돌 계약 확인")


def test_restore_response_contract(auth_client):
    created = auth_client.post("/api/exercises", json={"name_ko": "복원 계약 확인", "default_target": "abs"}).json()
    auth_client.patch(f"/api/exercises/{created['id']}", json={"is_archived": True})
    res = auth_client.post(f"/api/exercises/{created['id']}/restore")
    assert res.status_code == 200, res.text
    _assert_exercise_shape(res.json(), "restored")


def test_machines_contract(auth_client):
    res = auth_client.get("/api/machines")
    assert res.status_code == 200, res.text
    for i, m in enumerate(res.json()):
        assert set(m.keys()) == MACHINE_KEYS, f"machines[{i}]"
    dup = {"brand": "Hammer Strength", "model": "Contract Test Row"}
    assert auth_client.post("/api/machines", json=dup).status_code == 201
    assert auth_client.post("/api/machines", json=dup).status_code == 409
    assert auth_client.post("/api/machines", json={**dup, "model": "x", "target": "nope"}).status_code == 422
