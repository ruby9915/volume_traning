"""§10.2 세트 타겟(target) + §3.7-B 세션 직접 귀속(session_id) 테스트.

집계 규칙 (단일 규칙, 사용자 결정 2026-09-08):
- 세트 볼륨은 그 세트의 타겟에 100% 귀속. 협응근 분배 없음.
- 세부 타겟(level 3)은 근육(level 2)·부위(region)로 자동 합산.
- 볼륨 총량·PR·e1RM은 무영향 — 부위 귀속과 세트 수만 바뀐다.
"""

import uuid

import pytest

from helpers import effective_today, post_set, seed_exercise_id


def _muscles(client, **params):
    res = client.get("/api/stats/muscles", params=params)
    assert res.status_code == 200, res.text
    return {p["code"]: p for p in res.json()["points"]}


# ---------- POST /api/sets: target ----------


def test_post_target_saved_and_returned(auth_client):
    dead = seed_exercise_id("데드리프트")
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=5,
        target="hamstrings",
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["target"] == "hamstrings"
    assert body["target_ko"] == "햄스트링"

    # 세션 상세에도 동일 필드 + 종목 그룹에 기본 타겟
    detail = auth_client.get(f"/api/sessions/{body['session_id']}").json()
    group = detail["exercises"][0]
    assert group["default_target"] == "glutes"
    assert (group["sets"][0]["target"], group["sets"][0]["target_ko"]) == ("hamstrings", "햄스트링")


def test_post_target_default_is_exercise_default(auth_client):
    dead = seed_exercise_id("데드리프트")
    body = post_set(auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=5).json()
    assert (body["target"], body["target_ko"]) == ("glutes", "둔근")


def test_post_level3_target(auth_client):
    bench = seed_exercise_id("벤치프레스")
    body = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=10,
        target="upper_chest",
    ).json()
    assert (body["target"], body["target_ko"]) == ("upper_chest", "상부 가슴")


def test_post_invalid_target_422(auth_client):
    dead = seed_exercise_id("데드리프트")
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=5,
        target="hamstring",  # 오타 — 유효 code 아님
    )
    assert res.status_code == 422
    assert auth_client.get("/api/sessions").json() == []  # lazy 세션도 남지 않아야 한다


def test_idempotent_replay_same_shape_with_target(auth_client):
    dead = seed_exercise_id("데드리프트")
    payload = {
        "client_id": str(uuid.uuid4()),
        "date": "2026-07-20",
        "exercise_id": dead,
        "weight_kg": 100,
        "reps": 5,
        "target": "hamstrings",
    }
    first = auth_client.post("/api/sets", json=payload)
    assert first.status_code == 201
    replay = auth_client.post("/api/sets", json=payload)
    assert replay.status_code == 200
    assert set(replay.json().keys()) == set(first.json().keys())
    assert replay.json()["target"] == "hamstrings"


# ---------- PATCH /api/sets/{id}: target ----------


def test_patch_target_set_and_clear(auth_client):
    dead = seed_exercise_id("데드리프트")
    created = post_set(auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=5).json()

    res = auth_client.patch(f"/api/sets/{created['id']}", json={"target": "hamstrings"})
    assert res.status_code == 200, res.text
    assert (res.json()["target"], res.json()["target_ko"]) == ("hamstrings", "햄스트링")

    # 명시적 null = 종목 기본 타겟으로 복귀
    res = auth_client.patch(f"/api/sets/{created['id']}", json={"target": None})
    assert res.status_code == 200, res.text
    assert res.json()["target"] == "glutes"

    # target 미포함 PATCH는 타겟을 건드리지 않는다
    auth_client.patch(f"/api/sets/{created['id']}", json={"target": "quads"})
    res = auth_client.patch(f"/api/sets/{created['id']}", json={"reps": 6})
    assert res.json()["target"] == "quads"

    assert auth_client.patch(
        f"/api/sets/{created['id']}", json={"target": "nope"}
    ).status_code == 422


# ---------- POST /api/sets: session_id 직접 귀속 ----------


def test_session_id_attaches_to_that_session_not_latest(auth_client):
    bench = seed_exercise_id("벤치프레스")
    s1 = post_set(auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8).json()["session_id"]
    s2 = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8, new_session=True,
    ).json()["session_id"]
    assert s2 != s1

    lazy = post_set(auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8).json()
    assert lazy["session_id"] == s2

    direct = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8, session_id=s1,
    ).json()
    assert direct["session_id"] == s1
    assert direct["set_index"] == 2
    assert len(auth_client.get("/api/sessions").json()) == 2


def test_session_id_not_found_422(auth_client):
    bench = seed_exercise_id("벤치프레스")
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8, session_id=99999,
    )
    assert res.status_code == 422
    assert auth_client.get("/api/sessions").json() == []


def test_session_id_date_mismatch_422(auth_client):
    bench = seed_exercise_id("벤치프레스")
    sid = post_set(auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8).json()["session_id"]
    res = post_set(
        auth_client, date="2026-07-21", exercise_id=bench, weight_kg=60, reps=8, session_id=sid,
    )
    assert res.status_code == 422


def test_session_id_with_new_session_422(auth_client):
    bench = seed_exercise_id("벤치프레스")
    sid = post_set(auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8).json()["session_id"]
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8,
        session_id=sid, new_session=True,
    )
    assert res.status_code == 422


# ---------- 부위 귀속 (100% 단일 규칙) ----------


def test_muscles_attribution_is_100_percent_to_target(auth_client):
    """데드리프트 100kg×10 (volume 1000), target=hamstrings:
    → hamstrings 1세트·1000, 둔근·허리 등 나머지는 전부 0."""
    dead = seed_exercise_id("데드리프트")
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=10, target="hamstrings",
    )
    assert res.status_code == 201, res.text
    assert res.json()["volume_kg"] == 1000.0

    pts = _muscles(auth_client)
    assert (pts["hamstrings"]["set_count"], pts["hamstrings"]["volume_kg"]) == (1, 1000.0)
    for code in ("glutes", "lower_back", "back", "quads", "forearms", "chest"):
        assert (pts[code]["set_count"], pts[code]["volume_kg"]) == (0, 0.0), code


def test_muscles_level3_rolls_up_to_muscle(auth_client):
    """세부 타겟(상부 가슴)은 자기 행과 근육 행(가슴) 양쪽에 집계, 형제(중부 가슴)는 0."""
    bench = seed_exercise_id("벤치프레스")
    post_set(auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=10, target="upper_chest")
    pts = _muscles(auth_client)
    assert pts["upper_chest"]["level"] == 3 and pts["upper_chest"]["parent_code"] == "chest"
    assert (pts["upper_chest"]["set_count"], pts["upper_chest"]["volume_kg"]) == (1, 600.0)
    assert (pts["chest"]["set_count"], pts["chest"]["volume_kg"]) == (1, 600.0)
    assert (pts["mid_chest"]["set_count"], pts["mid_chest"]["volume_kg"]) == (0, 0.0)


def test_volume_per_muscle_and_region_with_target(auth_client):
    dead = seed_exercise_id("데드리프트")
    post_set(auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=10, target="hamstrings")
    body = auth_client.get(
        "/api/stats/volume", params={"granularity": "day", "from": "2026-07-20", "to": "2026-07-20"}
    ).json()
    assert len(body["points"]) == 1
    p = body["points"][0]
    assert p["total_volume"] == 1000.0
    assert p["per_muscle"]["hamstrings"] == pytest.approx(1000.0)
    assert p["per_muscle"]["glutes"] == 0.0
    assert p["per_region"]["legs"] == pytest.approx(1000.0)
    assert p["per_region"]["back"] == 0.0 and p["per_region"]["chest"] == 0.0


def test_summary_muscle_sets_with_target(auth_client):
    dead = seed_exercise_id("데드리프트")
    post_set(
        auth_client, date=effective_today().isoformat(), exercise_id=dead,
        weight_kg=100, reps=10, target="biceps_femoris",  # 세부 → 근육(hamstrings)으로 합산
    )
    body = auth_client.get("/api/stats/summary").json()
    sets = {m["code"]: m["set_count"] for m in body["muscle_sets_this_week"]}
    assert sets == {"hamstrings": 1}


def test_warmup_excluded_with_target(auth_client):
    dead = seed_exercise_id("데드리프트")
    post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=10,
        target="hamstrings", is_warmup=True,
    )
    pts = _muscles(auth_client)
    assert all(p["set_count"] == 0 for p in pts.values())
    pts = _muscles(auth_client, include_warmup=True)
    assert pts["hamstrings"]["set_count"] == 1


# ---------- 볼륨 총량·PR·e1RM 무영향 ----------


def test_pr_flags_unaffected_by_target(auth_client):
    dead = seed_exercise_id("데드리프트")
    post_set(auth_client, date="2026-07-10", exercise_id=dead, weight_kg=100, reps=5)
    with_target = post_set(
        auth_client, date="2026-07-12", exercise_id=dead, weight_kg=105, reps=5, target="hamstrings",
    ).json()
    assert with_target["volume_kg"] == 525.0
    assert with_target["is_weight_pr"] is True
    assert with_target["is_e1rm_pr"] is True
    stats = auth_client.get(f"/api/stats/exercises/{dead}").json()
    assert stats["weight_pr"]["value"] == 105.0
    assert [p["volume_kg"] for p in stats["points"]] == [500.0, 525.0]


def test_session_total_volume_unaffected_by_target(auth_client):
    dead = seed_exercise_id("데드리프트")
    created = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=10, target="hamstrings",
    ).json()
    detail = auth_client.get(f"/api/sessions/{created['session_id']}").json()
    assert detail["total_volume"] == 1000.0
