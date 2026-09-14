"""§10.4 머신 아카이브 검색 + 내 머신 목록."""


def _combined(m: dict) -> str:
    return f"{m['brand']} {m['model']} {m['name_ko']}".lower()


def test_machine_search_tokens_brand_limit(auth_client):
    total = auth_client.get("/api/machines").json()
    assert len(total) >= 1400, "아카이브 전체(파라미터 없음)"

    res = auth_client.get("/api/machines", params={"q": "핵 스쿼트", "limit": 20}).json()
    assert 1 <= len(res) <= 20
    for m in res:
        assert "핵" in _combined(m) and "스쿼트" in _combined(m), m

    res = auth_client.get("/api/machines", params={"q": "HACK squat"}).json()
    assert res and all("hack" in _combined(m) for m in res), "대소문자 무시"

    res = auth_client.get("/api/machines", params={"brand": "Panatta", "q": "leg"}).json()
    assert res and all(m["brand"] == "Panatta" for m in res)

    assert auth_client.get("/api/machines", params={"q": "zzz없는머신"}).json() == []
    assert auth_client.get("/api/machines", params={"q": "100% _"}).status_code == 200, "LIKE 이스케이프"
    assert auth_client.get("/api/machines", params={"limit": 0}).status_code == 422
    assert len(auth_client.get("/api/machines", params={"limit": 3}).json()) == 3


def test_machine_brands_counts(auth_client):
    total = len(auth_client.get("/api/machines").json())
    brands = auth_client.get("/api/machines/brands").json()
    assert {b["brand"] for b in brands} >= {"Hammer Strength", "Cybex", "Panatta", "렉스코", "뉴텍"}
    assert sum(b["count"] for b in brands) == total
    assert brands == sorted(brands, key=lambda b: (-b["count"], b["brand"]))


def test_my_machines_crud_and_scope(auth_client, user_client):
    found = auth_client.get("/api/machines", params={"q": "핵 스쿼트", "limit": 2}).json()
    a, b = found[0]["id"], found[1]["id"]
    assert auth_client.get("/api/me/machines").json() == []

    res = auth_client.post(f"/api/me/machines/{a}")
    assert res.status_code == 200, res.text
    assert [m["id"] for m in res.json()] == [a]
    assert {m["id"] for m in auth_client.post(f"/api/me/machines/{b}").json()} == {a, b}
    assert len(auth_client.post(f"/api/me/machines/{a}").json()) == 2, "중복 무시"
    assert set(auth_client.get("/api/me/machines").json()[0].keys()) == {
        "id", "brand", "model", "name_ko", "target"
    }

    assert auth_client.post("/api/me/machines/999999").status_code == 404
    assert user_client.get("/api/me/machines").json() == [], "사용자별 분리"

    assert [m["id"] for m in auth_client.delete(f"/api/me/machines/{a}").json()] == [b]
    assert auth_client.delete(f"/api/me/machines/{a}").status_code == 200, "없는 항목 삭제는 무해"
    assert auth_client.get("/api/me/machines").json()[0]["id"] == b


def test_custom_machine_is_added_to_creator_list(auth_client, user_client):
    created = auth_client.post(
        "/api/machines", json={"brand": "테스트짐", "model": "Custom Press", "target": "chest"}
    )
    assert created.status_code == 201, created.text
    mine = auth_client.get("/api/me/machines").json()
    assert [m["id"] for m in mine] == [created.json()["id"]]
    assert user_client.get("/api/me/machines").json() == []
    # 아카이브 검색에도 바로 잡힌다
    hit = auth_client.get("/api/machines", params={"q": "custom press"}).json()
    assert [m["id"] for m in hit] == [created.json()["id"]]
