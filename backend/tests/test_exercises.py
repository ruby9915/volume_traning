from app.seed_data.exercises import EXERCISES
from helpers import add_session, add_set, ex_id, seed_exercise_id


def _find(client, name_ko):
    res = client.get("/api/exercises", params={"include_archived": True})
    assert res.status_code == 200
    return next(e for e in res.json() if e["name_ko"] == name_ko)


def _create(client, name_ko, **extra):
    payload = {"name_ko": name_ko, "default_target": "back", **extra}
    res = client.post("/api/exercises", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_requires_auth(client):
    assert client.get("/api/exercises").status_code == 401
    assert client.get("/api/favorites").status_code == 401
    assert client.get("/api/targets").status_code == 401


def test_list_builtin_default(auth_client):
    data = auth_client.get("/api/exercises").json()
    assert len(data) == len(EXERCISES)

    bench = next(e for e in data if e["name_ko"] == "벤치프레스")
    assert bench["is_builtin"] is True and bench["is_archived"] is False and bench["is_own"] is False
    assert (bench["default_target"], bench["default_target_ko"]) == ("mid_chest", "중부 가슴")
    assert bench["tags"] == ["바벨", "플랫"]
    assert bench["base_movement"] == "벤치프레스"

    deadlift = next(e for e in data if e["name_ko"] == "데드리프트")
    assert deadlift["default_target"] == "glutes"
    assert next(e for e in data if e["name_ko"] == "덤벨 벤치프레스")["load_multiplier"] == 2
    assert next(e for e in data if e["name_ko"] == "풀업")["bodyweight_factor"] == 1.0


def test_create_custom_exercise(auth_client, user_client):
    body = _create(
        auth_client, "시티드 로우 머신 2", tags=["머신", "시티드", "머신"], base_movement="로우",
        default_target="rhomboids",
    )
    assert body["is_builtin"] is False and body["is_own"] is True
    assert body["tags"] == ["머신", "시티드"]  # 중복 제거
    assert (body["default_target"], body["default_target_ko"]) == ("rhomboids", "능형근")
    assert body["bodyweight_factor"] == 0 and body["load_multiplier"] == 1
    assert len(auth_client.get("/api/exercises").json()) == len(EXERCISES) + 1
    # 다른 사용자에게는 보이지 않는다 (§10.3 커스텀 = 소유자 전용)
    assert all(e["name_ko"] != "시티드 로우 머신 2" for e in user_client.get("/api/exercises").json())
    assert user_client.get(f"/api/exercises/{body['id']}/last-record").status_code == 404


def test_create_duplicate_active_409(auth_client):
    res = auth_client.post("/api/exercises", json={"name_ko": "벤치프레스", "default_target": "chest"})
    assert res.status_code == 409


def test_create_validation_422(auth_client):
    assert auth_client.post("/api/exercises", json={"name_ko": "테스트 종목"}).status_code == 422
    assert auth_client.post(
        "/api/exercises", json={"name_ko": "테스트 종목", "default_target": "nope"}
    ).status_code == 422
    assert auth_client.post(
        "/api/exercises", json={"name_ko": "테스트 종목", "default_target": "chest", "bogus": 1}
    ).status_code == 422
    assert auth_client.post(
        "/api/exercises",
        json={"name_ko": "테스트 종목", "default_target": "chest", "tags": [f"t{i}" for i in range(21)]},
    ).status_code == 422
    assert auth_client.post(
        "/api/exercises", json={"name_ko": "테스트 종목", "default_target": "chest", "machine_id": 9999}
    ).status_code == 422


def test_patch_builtin_admin_only(auth_client, user_client):
    bench = _find(auth_client, "벤치프레스")
    res = auth_client.patch(
        f"/api/exercises/{bench['id']}",
        json={"name_ko": "벤치프레스(수정)", "bodyweight_factor": 0.5, "default_target": "upper_chest", "tags": ["바벨"]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["name_ko"] == "벤치프레스(수정)"
    assert body["bodyweight_factor"] == 0.5
    assert body["default_target"] == "upper_chest"
    assert body["tags"] == ["바벨"]
    assert body["is_builtin"] is True
    assert _find(auth_client, "벤치프레스(수정)")["id"] == bench["id"]

    # 일반 사용자는 내장 종목을 수정·삭제할 수 없다
    assert user_client.patch(f"/api/exercises/{bench['id']}", json={"note": "x"}).status_code == 403
    assert user_client.delete(f"/api/exercises/{bench['id']}").status_code == 403


def test_patch_custom_owner_only(auth_client, user_client):
    mine = _create(auth_client, "내 종목")
    assert auth_client.patch(f"/api/exercises/{mine['id']}", json={"note": "메모"}).json()["note"] == "메모"
    # 다른 사용자에게는 존재 자체가 보이지 않는다
    assert user_client.patch(f"/api/exercises/{mine['id']}", json={"note": "x"}).status_code == 404
    assert user_client.delete(f"/api/exercises/{mine['id']}").status_code == 404


def test_patch_404_and_409(auth_client):
    assert auth_client.patch("/api/exercises/99999", json={"name_ko": "없는 종목"}).status_code == 404
    bench = _find(auth_client, "벤치프레스")
    assert auth_client.patch(f"/api/exercises/{bench['id']}", json={"name_ko": "풀업"}).status_code == 409
    assert auth_client.patch(f"/api/exercises/{bench['id']}", json={"default_target": None}).status_code == 422


def test_delete_without_sets_hard_deletes(auth_client):
    created = _create(auth_client, "임시 종목", default_target="abs")
    res = auth_client.delete(f"/api/exercises/{created['id']}")
    assert res.status_code == 200
    assert res.json() == {"deleted": True, "archived": False}
    full = auth_client.get("/api/exercises", params={"include_archived": True}).json()
    assert all(e["id"] != created["id"] for e in full)


def test_delete_with_sets_archives_then_restore(auth_client, db):
    bench = _find(auth_client, "벤치프레스")
    add_set(db, add_session(db, "2026-07-18"), bench["id"], 60, 8)

    res = auth_client.delete(f"/api/exercises/{bench['id']}")
    assert res.status_code == 200
    assert res.json() == {"deleted": False, "archived": True}
    assert all(e["id"] != bench["id"] for e in auth_client.get("/api/exercises").json())
    assert _find(auth_client, "벤치프레스")["is_archived"] is True

    res = auth_client.post(f"/api/exercises/{bench['id']}/restore")
    assert res.status_code == 200
    assert res.json()["is_archived"] is False
    assert any(e["id"] == bench["id"] for e in auth_client.get("/api/exercises").json())


def test_delete_and_restore_404(auth_client):
    assert auth_client.delete("/api/exercises/99999").status_code == 404
    assert auth_client.post("/api/exercises/99999/restore").status_code == 404


def test_create_archived_name_returns_409_conflict(auth_client, db):
    """계약(types.ts ArchivedConflictDetail): 동명 아카이브 존재 시 409 + detail.code."""
    bench = _find(auth_client, "벤치프레스")
    add_set(db, add_session(db, "2026-07-18"), bench["id"], 60, 8)
    auth_client.delete(f"/api/exercises/{bench['id']}")

    res = auth_client.post("/api/exercises", json={"name_ko": "벤치프레스", "default_target": "chest"})
    assert res.status_code == 409
    assert res.json()["detail"] == {"code": "archived_exists", "exercise_id": bench["id"], "name_ko": "벤치프레스"}
    assert len(auth_client.get("/api/exercises", params={"include_archived": True}).json()) == len(EXERCISES)


def test_last_record_scoped_to_user(auth_client, user_client, db):
    squat = ex_id(db, "백스쿼트")
    assert auth_client.get(f"/api/exercises/{squat}/last-record").status_code == 404
    assert auth_client.get("/api/exercises/99999/last-record").status_code == 404

    s1 = add_session(db, "2026-07-10")
    add_set(db, s1, squat, 80, 8)
    add_set(db, s1, squat, 80, 7)
    s2 = add_session(db, "2026-07-15")
    add_set(db, s2, squat, 82.5, 8)
    add_set(db, s2, squat, 82.5, 6)

    body = auth_client.get(f"/api/exercises/{squat}/last-record").json()
    assert body["session_id"] == s2 and body["session_date"] == "2026-07-15"
    assert body["sets"] == [
        {"weight_kg": 82.5, "reps": 8, "is_warmup": False},
        {"weight_kg": 82.5, "reps": 6, "is_warmup": False},
    ]
    # bob에게는 관리자의 기록이 보이지 않는다
    assert user_client.get(f"/api/exercises/{squat}/last-record").status_code == 404


# ---------- 즐겨찾기 (§10.3) ----------


def test_favorites_crud_and_order(auth_client, user_client):
    bench = seed_exercise_id("벤치프레스")
    squat = seed_exercise_id("백스쿼트")
    pullup = seed_exercise_id("풀업")
    assert auth_client.get("/api/favorites").json() == {"exercise_ids": []}

    assert auth_client.post(f"/api/favorites/{bench}").json()["exercise_ids"] == [bench]
    assert auth_client.post(f"/api/favorites/{squat}").json()["exercise_ids"] == [bench, squat]
    assert auth_client.post(f"/api/favorites/{squat}").json()["exercise_ids"] == [bench, squat]  # 중복 무시

    # 전체 교체 = 순서 편집
    res = auth_client.put("/api/favorites", json={"exercise_ids": [pullup, squat, bench, squat]})
    assert res.status_code == 200, res.text
    assert res.json()["exercise_ids"] == [pullup, squat, bench]
    assert auth_client.get("/api/favorites").json()["exercise_ids"] == [pullup, squat, bench]

    assert auth_client.delete(f"/api/favorites/{squat}").json()["exercise_ids"] == [pullup, bench]
    assert auth_client.delete("/api/favorites/99999").status_code == 200  # 없는 항목 삭제는 무해

    # 사용자별 분리 + 보이지 않는 종목은 404
    assert user_client.get("/api/favorites").json() == {"exercise_ids": []}
    mine = auth_client.post("/api/exercises", json={"name_ko": "비공개 종목", "default_target": "abs"}).json()
    assert user_client.post(f"/api/favorites/{mine['id']}").status_code == 404
    assert user_client.put("/api/favorites", json={"exercise_ids": [mine["id"]]}).status_code == 404
