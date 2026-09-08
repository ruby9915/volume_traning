"""§3.7 기록 의도 주동근(intent) + 세션 직접 귀속(session_id) 테스트.

집계 규칙 (단일 규칙):
- intent NULL 세트: 종목 매핑 primary 1.0 / secondary 0.5 (기존 §6.1).
- intent 지정 세트: intent 근육 1.0 + 그 종목 매핑의 나머지 근육 전부
  (원래 primary 포함, intent 제외) 0.5. intent가 매핑 밖 근육이어도 허용.
- 볼륨 총량·PR·e1RM은 무영향 — 부위 귀속과 부위별 세트 수만 바뀐다.
"""

import uuid

import pytest

from helpers import effective_today, post_set, seed_exercise_id


def _muscles(client, **params):
    res = client.get("/api/stats/muscles", params=params)
    assert res.status_code == 200, res.text
    return {p["code"]: p for p in res.json()["points"]}


# ---------- POST /api/sets: intent_muscle ----------


def test_post_intent_saved_and_returned(auth_client):
    dead = seed_exercise_id("데드리프트")
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=5,
        intent_muscle="hamstrings",
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["intent_muscle"] == "hamstrings"
    assert body["intent_muscle_ko"] == "햄스트링"

    # 세션 상세에도 동일 필드
    detail = auth_client.get(f"/api/sessions/{body['session_id']}").json()
    st = detail["exercises"][0]["sets"][0]
    assert (st["intent_muscle"], st["intent_muscle_ko"]) == ("hamstrings", "햄스트링")


def test_post_intent_default_null(auth_client):
    dead = seed_exercise_id("데드리프트")
    body = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=5
    ).json()
    assert (body["intent_muscle"], body["intent_muscle_ko"]) == (None, None)


def test_post_invalid_intent_code_422(auth_client):
    dead = seed_exercise_id("데드리프트")
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=5,
        intent_muscle="hamstring",  # 오타 — 유효 code 아님
    )
    assert res.status_code == 422


def test_post_intent_outside_mapping_allowed(auth_client):
    # 사용자 의도 우선 — 매핑에 없는 근육도 허용 (벤치 매핑에 abs 없음)
    bench = seed_exercise_id("벤치프레스")
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=10,
        intent_muscle="abs",
    )
    assert res.status_code == 201, res.text
    assert res.json()["intent_muscle"] == "abs"


def test_idempotent_replay_same_shape_with_intent(auth_client):
    dead = seed_exercise_id("데드리프트")
    payload = {
        "client_id": str(uuid.uuid4()),
        "date": "2026-07-20",
        "exercise_id": dead,
        "weight_kg": 100,
        "reps": 5,
        "intent_muscle": "hamstrings",
    }
    first = auth_client.post("/api/sets", json=payload)
    assert first.status_code == 201
    replay = auth_client.post("/api/sets", json=payload)
    assert replay.status_code == 200
    assert set(replay.json().keys()) == set(first.json().keys())
    assert replay.json()["intent_muscle"] == "hamstrings"
    assert replay.json()["intent_muscle_ko"] == "햄스트링"


# ---------- PATCH /api/sets/{id}: intent_muscle ----------


def test_patch_intent_set_and_clear(auth_client):
    dead = seed_exercise_id("데드리프트")
    created = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=5
    ).json()

    res = auth_client.patch(
        f"/api/sets/{created['id']}", json={"intent_muscle": "hamstrings"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["intent_muscle"] == "hamstrings"
    assert res.json()["intent_muscle_ko"] == "햄스트링"

    # 명시적 null = intent 해제 (기본 매핑으로 복귀)
    res = auth_client.patch(f"/api/sets/{created['id']}", json={"intent_muscle": None})
    assert res.status_code == 200, res.text
    assert (res.json()["intent_muscle"], res.json()["intent_muscle_ko"]) == (None, None)

    # intent_muscle 미포함 PATCH는 intent를 건드리지 않는다
    auth_client.patch(f"/api/sets/{created['id']}", json={"intent_muscle": "quads"})
    res = auth_client.patch(f"/api/sets/{created['id']}", json={"reps": 6})
    assert res.json()["intent_muscle"] == "quads"

    assert auth_client.patch(
        f"/api/sets/{created['id']}", json={"intent_muscle": "nope"}
    ).status_code == 422


# ---------- POST /api/sets: session_id 직접 귀속 ----------


def test_session_id_attaches_to_that_session_not_latest(auth_client):
    """기존 결함 시나리오: 같은 날 두 세션이면 date만으로는 최신 세션에 붙는다.
    session_id 지정 시 첫 세션에 정확히 귀속되어야 한다."""
    bench = seed_exercise_id("벤치프레스")
    s1 = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8
    ).json()["session_id"]
    s2 = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8,
        new_session=True,
    ).json()["session_id"]
    assert s2 != s1

    # date만: 최신(s2)에 붙는다
    lazy = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8
    ).json()
    assert lazy["session_id"] == s2

    # session_id 지정: s1에 붙고 set_index는 s1 기준으로 이어진다
    direct = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8,
        session_id=s1,
    ).json()
    assert direct["session_id"] == s1
    assert direct["set_index"] == 2

    # 세션 수는 늘지 않았다 (lazy 생성 생략)
    assert len(auth_client.get("/api/sessions").json()) == 2


def test_session_id_not_found_422(auth_client):
    bench = seed_exercise_id("벤치프레스")
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8,
        session_id=99999,
    )
    assert res.status_code == 422
    assert auth_client.get("/api/sessions").json() == []  # 세션 lazy 생성도 없어야 함


def test_session_id_date_mismatch_422(auth_client):
    bench = seed_exercise_id("벤치프레스")
    sid = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8
    ).json()["session_id"]
    res = post_set(
        auth_client, date="2026-07-21", exercise_id=bench, weight_kg=60, reps=8,
        session_id=sid,
    )
    assert res.status_code == 422


def test_session_id_with_new_session_422(auth_client):
    bench = seed_exercise_id("벤치프레스")
    sid = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8
    ).json()["session_id"]
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=8,
        session_id=sid, new_session=True,
    )
    assert res.status_code == 422


# ---------- 부위 귀속 가중치 손계산 회귀 (§3.7 단일 규칙) ----------


def test_muscles_weighting_deadlift_intent_hamstrings(auth_client):
    """데드리프트(primary hamstrings·glutes·lower_back / secondary back·quads·forearms)
    100kg×10 (volume 1000) 1세트, intent=hamstrings:
    → hamstrings 1.0세트·1000 / 나머지 매핑 5근육 각 0.5세트·500 / 그 외 0."""
    dead = seed_exercise_id("데드리프트")
    res = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=10,
        intent_muscle="hamstrings",
    )
    assert res.status_code == 201, res.text
    assert res.json()["volume_kg"] == 1000.0  # 볼륨 총량 무영향

    pts = _muscles(auth_client)
    assert pts["hamstrings"]["set_count"] == 1.0
    assert pts["hamstrings"]["volume_kg"] == 1000.0
    for code in ("glutes", "lower_back", "back", "quads", "forearms"):
        assert pts[code]["set_count"] == 0.5, code
        assert pts[code]["volume_kg"] == 500.0, code
    for code in ("chest", "shoulders", "biceps", "triceps", "calves", "abs"):
        assert pts[code]["set_count"] == 0.0, code
        assert pts[code]["volume_kg"] == 0.0, code


def test_muscles_weighting_intent_null_unchanged(auth_client):
    """intent NULL이면 기존 규칙 그대로: 데드리프트 primary 3근육 1.0 / secondary 3근육 0.5."""
    dead = seed_exercise_id("데드리프트")
    post_set(auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=10)

    pts = _muscles(auth_client)
    for code in ("hamstrings", "glutes", "lower_back"):
        assert pts[code]["set_count"] == 1.0, code
        assert pts[code]["volume_kg"] == 1000.0, code
    for code in ("back", "quads", "forearms"):
        assert pts[code]["set_count"] == 0.5, code
        assert pts[code]["volume_kg"] == 500.0, code


def test_muscles_weighting_intent_outside_mapping(auth_client):
    """벤치프레스(primary chest / secondary triceps·shoulders) 60×10 (600),
    intent=abs(매핑 밖): abs 1.0·600 + chest·triceps·shoulders 각 0.5·300.
    원래 primary(chest)도 0.5로 강등된다."""
    bench = seed_exercise_id("벤치프레스")
    post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=10,
        intent_muscle="abs",
    )

    pts = _muscles(auth_client)
    assert pts["abs"]["set_count"] == 1.0
    assert pts["abs"]["volume_kg"] == 600.0
    for code in ("chest", "triceps", "shoulders"):
        assert pts[code]["set_count"] == 0.5, code
        assert pts[code]["volume_kg"] == 300.0, code


def test_muscles_weighting_intent_equals_sole_primary(auth_client):
    """intent가 원래 primary와 같으면(벤치+chest) 기존 규칙과 결과 동일."""
    bench = seed_exercise_id("벤치프레스")
    post_set(
        auth_client, date="2026-07-20", exercise_id=bench, weight_kg=60, reps=10,
        intent_muscle="chest",
    )
    pts = _muscles(auth_client)
    assert pts["chest"]["set_count"] == 1.0
    assert pts["chest"]["volume_kg"] == 600.0
    for code in ("triceps", "shoulders"):
        assert pts[code]["set_count"] == 0.5, code
        assert pts[code]["volume_kg"] == 300.0, code


def test_volume_per_muscle_and_region_with_intent(auth_client):
    """/api/stats/volume: 데드리프트 1000 intent=hamstrings →
    per_muscle hamstrings 1000·나머지 5근육 500,
    per_region legs 2000(ham 1000+glutes 500+quads 500)·back 1000(back 500+lower_back 500)·arms 500.
    total_volume은 1000 그대로."""
    dead = seed_exercise_id("데드리프트")
    post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=10,
        intent_muscle="hamstrings",
    )
    body = auth_client.get(
        "/api/stats/volume",
        params={"granularity": "day", "from": "2026-07-20", "to": "2026-07-20"},
    ).json()
    assert len(body["points"]) == 1
    p = body["points"][0]
    assert p["total_volume"] == 1000.0  # 총볼륨 무영향
    pm = p["per_muscle"]
    assert pm["hamstrings"] == pytest.approx(1000.0)
    for code in ("glutes", "lower_back", "back", "quads", "forearms"):
        assert pm[code] == pytest.approx(500.0), code
    pr = p["per_region"]
    assert pr["legs"] == pytest.approx(2000.0)
    assert pr["back"] == pytest.approx(1000.0)
    assert pr["arms"] == pytest.approx(500.0)
    assert pr["chest"] == 0.0 and pr["shoulders"] == 0.0 and pr["core"] == 0.0


def test_summary_muscle_sets_with_intent(auth_client):
    """summary muscle_sets_this_week에도 동일 규칙 반영 (이번 주 날짜 사용)."""
    dead = seed_exercise_id("데드리프트")
    post_set(
        auth_client, date=effective_today().isoformat(), exercise_id=dead,
        weight_kg=100, reps=10, intent_muscle="hamstrings",
    )
    body = auth_client.get("/api/stats/summary").json()
    sets = {m["code"]: m["weighted_sets"] for m in body["muscle_sets_this_week"]}
    assert sets["hamstrings"] == 1.0
    for code in ("glutes", "lower_back", "back", "quads", "forearms"):
        assert sets[code] == 0.5, code


def test_warmup_excluded_with_intent(auth_client):
    dead = seed_exercise_id("데드리프트")
    post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=10,
        intent_muscle="hamstrings", is_warmup=True,
    )
    pts = _muscles(auth_client)
    assert all(p["set_count"] == 0.0 for p in pts.values())
    pts = _muscles(auth_client, include_warmup=True)
    assert pts["hamstrings"]["set_count"] == 1.0


# ---------- 볼륨 총량·PR·e1RM 무영향 ----------


def test_pr_flags_unaffected_by_intent(auth_client):
    dead = seed_exercise_id("데드리프트")
    post_set(auth_client, date="2026-07-10", exercise_id=dead, weight_kg=100, reps=5)

    with_intent = post_set(
        auth_client, date="2026-07-12", exercise_id=dead, weight_kg=105, reps=5,
        intent_muscle="hamstrings",
    ).json()
    assert with_intent["volume_kg"] == 525.0
    assert with_intent["is_weight_pr"] is True
    assert with_intent["is_e1rm_pr"] is True  # 105*(1+5/30) > 100*(1+5/30)

    # 종목 통계의 e1RM·top weight에도 intent는 무영향
    stats = auth_client.get(f"/api/stats/exercises/{dead}").json()
    assert stats["weight_pr"]["value"] == 105.0
    assert [p["volume_kg"] for p in stats["points"]] == [500.0, 525.0]


def test_session_total_volume_unaffected_by_intent(auth_client):
    dead = seed_exercise_id("데드리프트")
    created = post_set(
        auth_client, date="2026-07-20", exercise_id=dead, weight_kg=100, reps=10,
        intent_muscle="hamstrings",
    ).json()
    detail = auth_client.get(f"/api/sessions/{created['session_id']}").json()
    assert detail["total_volume"] == 1000.0
