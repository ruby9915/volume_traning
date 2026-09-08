import sqlite3


def _db(tmp_path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_set(
    tmp_path, exercise_id, date="2026-07-18", weight=60.0, reps=8, set_index=1, session_id=None
):
    conn = _db(tmp_path)
    try:
        if session_id is None:
            session_id = conn.execute(
                "INSERT INTO workout_session (date) VALUES (?)", (date,)
            ).lastrowid
        conn.execute(
            "INSERT INTO workout_set (session_id, exercise_id, set_index, weight_kg, reps)"
            " VALUES (?, ?, ?, ?, ?)",
            (session_id, exercise_id, set_index, weight, reps),
        )
        conn.commit()
        return session_id
    finally:
        conn.close()


def _find(auth_client, name_ko):
    res = auth_client.get("/api/exercises", params={"include_archived": True})
    assert res.status_code == 200
    return next(e for e in res.json() if e["name_ko"] == name_ko)


def test_requires_auth(client):
    assert client.get("/api/exercises").status_code == 401


def test_list_builtin_default(auth_client):
    res = auth_client.get("/api/exercises")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 45

    bench = next(e for e in data if e["name_ko"] == "벤치프레스")
    assert bench["is_builtin"] is True
    assert bench["is_archived"] is False
    assert {"code": "chest", "role": "primary"} in bench["muscles"]

    deadlift = next(e for e in data if e["name_ko"] == "데드리프트")
    primaries = [m["code"] for m in deadlift["muscles"] if m["role"] == "primary"]
    assert sorted(primaries) == ["glutes", "hamstrings", "lower_back"]

    dumbbell_bench = next(e for e in data if e["name_ko"] == "덤벨 벤치프레스")
    assert dumbbell_bench["load_multiplier"] == 2

    pullup = next(e for e in data if e["name_ko"] == "풀업")
    assert pullup["bodyweight_factor"] == 1.0


def test_create_exercise(auth_client):
    payload = {
        "name_ko": "시티드 로우 머신",
        "muscles": [
            {"code": "back", "role": "primary"},
            {"code": "biceps", "role": "secondary"},
        ],
    }
    res = auth_client.post("/api/exercises", json=payload)
    assert res.status_code == 201
    body = res.json()
    assert body["name_ko"] == "시티드 로우 머신"
    assert body["is_builtin"] is False
    assert body["is_archived"] is False
    assert body["bodyweight_factor"] == 0
    assert body["load_multiplier"] == 1
    assert body["muscles"] == [
        {"code": "back", "role": "primary"},
        {"code": "biceps", "role": "secondary"},
    ]
    assert len(auth_client.get("/api/exercises").json()) == 46


def test_create_duplicate_active_409(auth_client):
    res = auth_client.post(
        "/api/exercises",
        json={"name_ko": "벤치프레스", "muscles": [{"code": "chest", "role": "primary"}]},
    )
    assert res.status_code == 409


def test_create_validation_422(auth_client):
    no_primary = {
        "name_ko": "테스트 종목",
        "muscles": [{"code": "chest", "role": "secondary"}],
    }
    assert auth_client.post("/api/exercises", json=no_primary).status_code == 422

    dup_muscle = {
        "name_ko": "테스트 종목",
        "muscles": [
            {"code": "chest", "role": "primary"},
            {"code": "chest", "role": "secondary"},
        ],
    }
    assert auth_client.post("/api/exercises", json=dup_muscle).status_code == 422

    extra_field = {
        "name_ko": "테스트 종목",
        "muscles": [{"code": "chest", "role": "primary"}],
        "bogus": 1,
    }
    assert auth_client.post("/api/exercises", json=extra_field).status_code == 422


def test_patch_builtin(auth_client):
    bench = _find(auth_client, "벤치프레스")
    res = auth_client.patch(
        f"/api/exercises/{bench['id']}",
        json={
            "name_ko": "벤치프레스(수정)",
            "bodyweight_factor": 0.5,
            "muscles": [{"code": "chest", "role": "primary"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name_ko"] == "벤치프레스(수정)"
    assert body["bodyweight_factor"] == 0.5
    assert body["muscles"] == [{"code": "chest", "role": "primary"}]
    assert body["is_builtin"] is True

    again = _find(auth_client, "벤치프레스(수정)")
    assert again["id"] == bench["id"]


def test_patch_404_and_409(auth_client):
    assert (
        auth_client.patch("/api/exercises/99999", json={"name_ko": "없는 종목"}).status_code
        == 404
    )
    bench = _find(auth_client, "벤치프레스")
    res = auth_client.patch(f"/api/exercises/{bench['id']}", json={"name_ko": "풀업"})
    assert res.status_code == 409


def test_delete_without_sets_hard_deletes(auth_client):
    created = auth_client.post(
        "/api/exercises",
        json={"name_ko": "임시 종목", "muscles": [{"code": "abs", "role": "primary"}]},
    ).json()
    res = auth_client.delete(f"/api/exercises/{created['id']}")
    assert res.status_code == 200
    assert res.json() == {"deleted": True, "archived": False}

    full = auth_client.get("/api/exercises", params={"include_archived": True}).json()
    assert all(e["id"] != created["id"] for e in full)


def test_delete_with_sets_archives_then_restore(auth_client, tmp_path):
    bench = _find(auth_client, "벤치프레스")
    _insert_set(tmp_path, bench["id"])

    res = auth_client.delete(f"/api/exercises/{bench['id']}")
    assert res.status_code == 200
    assert res.json() == {"deleted": False, "archived": True}

    default_list = auth_client.get("/api/exercises").json()
    assert all(e["id"] != bench["id"] for e in default_list)

    full_list = auth_client.get("/api/exercises", params={"include_archived": True}).json()
    archived = next(e for e in full_list if e["id"] == bench["id"])
    assert archived["is_archived"] is True

    res = auth_client.post(f"/api/exercises/{bench['id']}/restore")
    assert res.status_code == 200
    assert res.json()["is_archived"] is False
    default_list = auth_client.get("/api/exercises").json()
    assert any(e["id"] == bench["id"] for e in default_list)


def test_delete_and_restore_404(auth_client):
    assert auth_client.delete("/api/exercises/99999").status_code == 404
    assert auth_client.post("/api/exercises/99999/restore").status_code == 404


def test_create_archived_name_returns_409_conflict(auth_client, tmp_path):
    """계약(types.ts ArchivedConflictDetail): 동명 아카이브 존재 시 409 + detail.code."""
    bench = _find(auth_client, "벤치프레스")
    _insert_set(tmp_path, bench["id"])
    auth_client.delete(f"/api/exercises/{bench['id']}")

    res = auth_client.post(
        "/api/exercises",
        json={"name_ko": "벤치프레스", "muscles": [{"code": "chest", "role": "primary"}]},
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail == {
        "code": "archived_exists",
        "exercise_id": bench["id"],
        "name_ko": "벤치프레스",
    }

    full = auth_client.get("/api/exercises", params={"include_archived": True}).json()
    assert len(full) == 45  # 새 행이 생기지 않았다


def test_last_record(auth_client, tmp_path):
    squat = _find(auth_client, "백스쿼트")
    assert auth_client.get(f"/api/exercises/{squat['id']}/last-record").status_code == 404
    assert auth_client.get("/api/exercises/99999/last-record").status_code == 404

    s1 = _insert_set(tmp_path, squat["id"], date="2026-07-10", weight=80, reps=8, set_index=1)
    _insert_set(tmp_path, squat["id"], date="2026-07-10", weight=80, reps=7, set_index=2, session_id=s1)
    s2 = _insert_set(tmp_path, squat["id"], date="2026-07-15", weight=82.5, reps=8, set_index=1)
    _insert_set(tmp_path, squat["id"], date="2026-07-15", weight=82.5, reps=6, set_index=2, session_id=s2)

    res = auth_client.get(f"/api/exercises/{squat['id']}/last-record")
    assert res.status_code == 200
    body = res.json()
    assert body["session_id"] == s2
    assert body["session_date"] == "2026-07-15"
    assert body["sets"] == [
        {"weight_kg": 82.5, "reps": 8, "is_warmup": False},
        {"weight_kg": 82.5, "reps": 6, "is_warmup": False},
    ]
