"""§13 프로필·친구·읽기 공유."""

from helpers import effective_today, ex_id


def _id(client) -> int:
    return client.get("/api/auth/me").json()["id"]


def _name(client) -> str:
    return client.get("/api/auth/me").json()["username"]


def test_profile_get_and_patch(auth_client, user_client):
    me = auth_client.get("/api/auth/me").json()
    assert me["share_with_friends"] is True and me["bio"] is None and me["avatar"] is None

    res = auth_client.patch(
        "/api/me/profile", json={"display_name": "루비", "bio": "5분할 · 등 이두", "avatar": "🦍"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["display_name"] == "루비" and res.json()["avatar"] == "🦍"

    mine = auth_client.get(f"/api/profile/{me['username']}").json()
    assert mine["relation"] == "self" and mine["share_with_friends"] is True
    assert set(mine["stats"].keys()) == {"training_weeks", "session_count", "set_count", "volume_4w", "last_session_date"}

    # 남의 프로필: 친구 아니면 통계·공개설정 없음
    other = user_client.get(f"/api/profile/{me['username']}").json()
    assert other["relation"] == "none" and other["stats"] is None and other["share_with_friends"] is None

    assert auth_client.patch("/api/me/profile", json={}).status_code == 422
    assert auth_client.patch("/api/me/profile", json={"display_name": ""}).status_code == 422
    assert auth_client.get("/api/profile/no-such-user").status_code == 404


def test_friend_request_accept_and_share(auth_client, user_client, db):
    admin_id, bob_id = _id(auth_client), _id(user_client)
    admin_name, bob_name = _name(auth_client), _name(user_client)

    # 검색: 본인 제외, 2자 이상
    assert user_client.get("/api/users/search", params={"q": "x"}).status_code == 422
    found = user_client.get("/api/users/search", params={"q": admin_name[:2]}).json()
    assert any(u["username"] == admin_name and u["relation"] == "none" for u in found)
    assert all(u["id"] != bob_id for u in found)

    # 친구 아님 → 상대 데이터 403 not_friends (관리자는 예외라 bob→admin 방향으로 검사)
    res = user_client.get("/api/sessions", params={"user_id": admin_id})
    assert res.status_code == 403 and res.json()["detail"]["code"] == "not_friends"
    assert user_client.get("/api/stats/summary", params={"user_id": admin_id}).status_code == 403
    assert user_client.get("/api/bodyweight", params={"user_id": admin_id}).status_code == 403

    # bob → admin 요청
    res = user_client.post("/api/friends/requests", json={"username": admin_name})
    assert res.status_code == 200, res.text
    assert [r["user"]["username"] for r in res.json()["outgoing"]] == [admin_name]
    assert user_client.post("/api/friends/requests", json={"username": admin_name}).status_code == 409
    assert user_client.post("/api/friends/requests", json={"username": bob_name}).status_code == 422
    assert user_client.get(f"/api/profile/{admin_name}").json()["relation"] == "pending_out"

    inbox = auth_client.get("/api/friends").json()
    assert [r["user"]["username"] for r in inbox["incoming"]] == [bob_name]
    req_id = inbox["incoming"][0]["request_id"]
    # 요청자는 수락 못 한다
    assert user_client.post(f"/api/friends/requests/{req_id}/accept").status_code == 404

    res = auth_client.post(f"/api/friends/requests/{req_id}/accept")
    assert res.status_code == 200 and [f["username"] for f in res.json()["friends"]] == [bob_name]
    assert user_client.get("/api/friends").json()["friends"][0]["username"] == admin_name
    assert user_client.get(f"/api/profile/{admin_name}").json()["relation"] == "friend"

    # 친구 → 읽기 공유 (세션·통계·체중·분석 게이트), 프로필 통계 보임
    assert user_client.get("/api/sessions", params={"user_id": admin_id}).status_code == 200
    assert user_client.get("/api/stats/summary", params={"user_id": admin_id}).status_code == 200
    assert user_client.get("/api/bodyweight", params={"user_id": admin_id}).status_code == 200
    adv = user_client.get("/api/stats/advanced/frequency", params={"user_id": admin_id})
    assert adv.status_code in (200, 403)
    if adv.status_code == 403:
        assert adv.json()["detail"]["code"] == "insufficient_data"
    assert user_client.get(f"/api/profile/{admin_name}").json()["stats"] is not None

    # 쓰기는 항상 본인 것: user_id를 붙여도 bob 자신의 세션에 들어간다
    admin_sets_before = sum(s["set_count"] for s in auth_client.get("/api/sessions").json())
    res = user_client.post(
        "/api/sets",
        params={"user_id": admin_id},
        json={
            "client_id": "friend-write-1", "date": str(effective_today()), "exercise_id": ex_id(db, "벤치프레스"),
            "weight_kg": 40, "reps": 5,
        },
    )
    assert res.status_code == 201, res.text
    own = user_client.get("/api/sessions").json()
    assert own and sum(s["set_count"] for s in own) == 1
    assert sum(s["set_count"] for s in auth_client.get("/api/sessions").json()) == admin_sets_before

    # 공개 끄면 친구도 403, 관리자는 계속 가능
    assert auth_client.patch("/api/me/profile", json={"share_with_friends": False}).json()["share_with_friends"] is False
    assert user_client.get("/api/sessions", params={"user_id": admin_id}).status_code == 403
    assert auth_client.get("/api/sessions", params={"user_id": bob_id}).status_code == 200
    auth_client.patch("/api/me/profile", json={"share_with_friends": True})

    # 끊기: 양쪽에서 사라지고 다시 403
    res = auth_client.delete(f"/api/friends/{bob_id}")
    assert res.status_code == 200 and res.json()["friends"] == []
    assert user_client.get("/api/friends").json()["friends"] == []
    assert user_client.get("/api/sessions", params={"user_id": admin_id}).status_code == 403


def test_reverse_request_auto_accepts_and_decline(auth_client, user_client):
    admin_name, bob_name = _name(auth_client), _name(user_client)
    # admin → bob 요청, bob이 반대로 요청하면 곧바로 친구
    auth_client.post("/api/friends/requests", json={"username": bob_name})
    res = user_client.post("/api/friends/requests", json={"username": admin_name})
    assert res.status_code == 200 and [f["username"] for f in res.json()["friends"]] == [admin_name]
    assert auth_client.get("/api/friends").json()["outgoing"] == []

    auth_client.delete(f"/api/friends/{_id(user_client)}")
    # 거절: 받은 쪽이 decline → 관계 없음, 요청자도 취소 가능
    auth_client.post("/api/friends/requests", json={"username": bob_name})
    req_id = user_client.get("/api/friends").json()["incoming"][0]["request_id"]
    assert user_client.post(f"/api/friends/requests/{req_id}/decline").status_code == 200
    assert user_client.get(f"/api/profile/{admin_name}").json()["relation"] == "none"
    auth_client.post("/api/friends/requests", json={"username": bob_name})
    req_id = auth_client.get("/api/friends").json()["outgoing"][0]["request_id"]
    assert auth_client.post(f"/api/friends/requests/{req_id}/decline").status_code == 200
    assert auth_client.get("/api/friends").json()["outgoing"] == []
    assert auth_client.post("/api/friends/requests/999999/accept").status_code == 404


def test_subject_unknown_user_404(auth_client):
    assert auth_client.get("/api/sessions", params={"user_id": 999999}).status_code == 404


def test_machine_region_filter(auth_client):
    res = auth_client.get("/api/machines", params={"region": "legs", "q": "레그", "limit": 10}).json()
    assert res and all(m["target"] for m in res)
    codes = {m["target"] for m in res}
    assert codes <= {"quads", "hamstrings", "glutes", "calves", "adductors", "vastus_medialis", "vastus_lateralis",
                     "rectus_femoris", "vastus_intermedius", "biceps_femoris", "medial_hamstrings", "glute_max",
                     "glute_med", "glute_min", "gastrocnemius", "soleus", "tibialis_anterior", "adductor_magnus",
                     "adductor_longus"}
    assert auth_client.get("/api/machines", params={"region": "nope"}).json() == []
