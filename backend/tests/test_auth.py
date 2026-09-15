"""§10.1 계정·인증 + 사용자 범위 격리 + §10.5 관리자 조회."""

import jwt as pyjwt

from conftest import TEST_ADMIN, TEST_PASSWORD, login
from helpers import add_session, add_set, ex_id, post_set, seed_exercise_id


# ---------- 가입·로그인 ----------


def test_register_login_me(client):
    res = client.post("/api/auth/register", json={"username": "alice", "password": "pass1234"})
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    me = client.get("/api/auth/me").json()
    assert (me["username"], me["display_name"], me["is_admin"]) == ("alice", "alice", False)
    assert set(me.keys()) == {
        "id", "username", "display_name", "is_admin", "created_at",
        "bio", "avatar", "share_with_friends",  # §13 프로필
    }

    client.headers.pop("Authorization")
    login(client, "alice", "pass1234")
    assert client.get("/api/auth/me").json()["username"] == "alice"


def test_register_validation_and_duplicates(client):
    assert client.post("/api/auth/register", json={"username": "a", "password": "pass1234"}).status_code == 422
    assert client.post("/api/auth/register", json={"username": "한글", "password": "pass1234"}).status_code == 422
    assert client.post("/api/auth/register", json={"username": "ok_user", "password": "123"}).status_code == 422
    assert client.post("/api/auth/register", json={"username": TEST_ADMIN, "password": "pass1234"}).status_code == 409


def test_login_failures(client):
    assert client.post("/api/auth/login", json={"username": TEST_ADMIN, "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "nobody", "password": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": TEST_PASSWORD}).status_code == 422  # v1 형식 거부


def test_first_admin_from_env(auth_client):
    me = auth_client.get("/api/auth/me").json()
    assert (me["username"], me["is_admin"]) == (TEST_ADMIN, True)


def test_legacy_token_without_sub_rejected(client):
    from app.config import get_settings

    token = pyjwt.encode({"exp": 4102444800}, get_settings().JWT_SECRET, algorithm="HS256")
    client.headers["Authorization"] = f"Bearer {token}"
    assert client.get("/api/sessions").status_code == 401
    token = pyjwt.encode({"exp": 4102444800, "sub": "99999"}, get_settings().JWT_SECRET, algorithm="HS256")
    client.headers["Authorization"] = f"Bearer {token}"
    assert client.get("/api/sessions").status_code == 401  # 삭제된 사용자


def test_change_password(auth_client):
    res = auth_client.post("/api/auth/password", json={"current_password": "wrong", "new_password": "newpass"})
    assert res.status_code == 401
    res = auth_client.post("/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "newpass"})
    assert res.status_code == 204, res.text
    assert auth_client.post("/api/auth/login", json={"username": TEST_ADMIN, "password": TEST_PASSWORD}).status_code == 401
    assert auth_client.post("/api/auth/login", json={"username": TEST_ADMIN, "password": "newpass"}).status_code == 200


# ---------- 사용자 범위 격리 ----------


def test_data_is_scoped_per_user(auth_client, user_client):
    bench = seed_exercise_id("벤치프레스")
    mine = post_set(auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8).json()
    assert user_client.get("/api/sessions").json() == []
    assert user_client.get(f"/api/sessions/{mine['session_id']}").status_code == 404
    assert user_client.patch(f"/api/sets/{mine['id']}", json={"reps": 5}).status_code == 404
    assert user_client.delete(f"/api/sets/{mine['id']}").status_code == 404
    assert user_client.patch(f"/api/sessions/{mine['session_id']}", json={"note": "x"}).status_code == 404
    assert user_client.delete(f"/api/sessions/{mine['session_id']}").status_code == 404
    # session_id 직접 귀속도 남의 세션엔 불가
    assert post_set(
        user_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8, session_id=mine["session_id"],
    ).status_code == 422
    assert user_client.get("/api/stats/summary").json()["totals"]["set_count"] == 0

    theirs = post_set(user_client, date="2026-07-20", exercise_id=bench, weight_kg=40, reps=8).json()
    assert theirs["session_id"] != mine["session_id"]  # 같은 날이라도 사용자별 세션
    assert [s["id"] for s in auth_client.get("/api/sessions").json()] == [mine["session_id"]]


def test_client_id_is_scoped_per_user(auth_client, user_client):
    """같은 client_id라도 다른 사용자면 다른 세트 (멱등 키는 사용자 범위)."""
    bench = seed_exercise_id("벤치프레스")
    payload = {"client_id": "shared-id", "date": "2026-07-20", "exercise_id": bench, "weight_kg": 60, "reps": 8}
    a = auth_client.post("/api/sets", json=payload)
    assert a.status_code == 201
    b = user_client.post("/api/sets", json={**payload, "weight_kg": 40})
    # UNIQUE(client_id)는 전역 — 남의 세트와 충돌하면 멱등 200도 500도 아닌 명확한 409
    assert b.status_code == 409, b.text
    assert user_client.get("/api/sessions").json() == []


def test_bodyweight_is_per_user(auth_client, user_client):
    assert auth_client.post("/api/bodyweight", json={"date": "2026-07-19", "weight_kg": 80}).status_code == 200
    assert user_client.post("/api/bodyweight", json={"date": "2026-07-19", "weight_kg": 60}).status_code == 200
    assert [r["weight_kg"] for r in auth_client.get("/api/bodyweight").json()] == [80]
    assert [r["weight_kg"] for r in user_client.get("/api/bodyweight").json()] == [60]


# ---------- 관리자 조회 (§10.5) ----------


def test_admin_endpoints(auth_client, user_client, db):
    assert user_client.get("/api/admin/users").status_code == 403
    bench = ex_id(db, "벤치프레스")
    bob_id = db.execute("SELECT id FROM user WHERE username = 'bob'").fetchone()[0]
    s = add_session(db, "2026-07-20", user_id=bob_id)
    add_set(db, s, bench, 60, 8)
    add_set(db, s, bench, 60, 8)

    users = auth_client.get("/api/admin/users").json()
    assert [u["username"] for u in users] == [TEST_ADMIN, "bob"]
    bob = users[1]
    assert set(bob.keys()) == {
        "id", "username", "display_name", "is_admin", "created_at", "session_count", "set_count", "last_date",
    }
    assert (bob["session_count"], bob["set_count"], bob["last_date"], bob["is_admin"]) == (1, 2, "2026-07-20", False)

    sessions = auth_client.get(f"/api/admin/users/{bob_id}/sessions").json()
    assert [x["id"] for x in sessions] == [s]
    detail = auth_client.get(f"/api/admin/users/{bob_id}/sessions/{s}").json()
    assert detail["set_count"] == 2 and detail["exercises"][0]["name_ko"] == "벤치프레스"
    assert auth_client.get(f"/api/admin/users/{bob_id}/bodyweight").json() == []
    assert auth_client.get("/api/admin/users/99999/sessions").status_code == 404
    assert auth_client.get(f"/api/admin/users/{bob_id}/sessions/99999").status_code == 404
    # 관리자 조회는 읽기 전용 — 쓰기 경로 없음
    assert auth_client.delete(f"/api/admin/users/{bob_id}").status_code in (404, 405)
