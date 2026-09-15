"""§14 세트 운동 방식(technique) — 기록·수정·표시·내보내기. 볼륨·PR에는 영향 없음."""

from helpers import effective_today, post_set, seed_exercise_id


def test_set_technique_create_update_clear(auth_client):
    ex = seed_exercise_id("벤치프레스")
    today = str(effective_today())
    plain = post_set(auth_client, date=today, exercise_id=ex, weight_kg=60, reps=8).json()
    assert plain["technique"] is None

    drop = post_set(auth_client, date=today, exercise_id=ex, weight_kg=50, reps=10, technique="drop").json()
    assert drop["technique"] == "drop"
    assert drop["volume_kg"] == 500, "방식은 볼륨 계산과 무관"

    res = auth_client.patch(f"/api/sets/{drop['id']}", json={"technique": "superset"})
    assert res.status_code == 200 and res.json()["technique"] == "superset"
    res = auth_client.patch(f"/api/sets/{drop['id']}", json={"technique": None})
    assert res.status_code == 200 and res.json()["technique"] is None
    res = auth_client.patch(f"/api/sets/{drop['id']}", json={"weight_kg": 55})
    assert res.json()["technique"] is None and res.json()["weight_kg"] == 55, "다른 필드 수정은 방식 유지"

    # 유효하지 않은 값은 422
    assert auth_client.patch(f"/api/sets/{drop['id']}", json={"technique": "pyramid"}).status_code == 422
    res = auth_client.post(
        "/api/sets",
        json={"client_id": "tech-bad", "date": today, "exercise_id": ex, "weight_kg": 40, "reps": 5, "technique": "x"},
    )
    assert res.status_code == 422


def test_technique_in_session_detail_and_csv(auth_client):
    ex = seed_exercise_id("백스쿼트")
    today = str(effective_today())
    post_set(auth_client, date=today, exercise_id=ex, weight_kg=100, reps=5, technique="rest_pause")
    post_set(auth_client, date=today, exercise_id=ex, weight_kg=100, reps=3)
    sessions = auth_client.get("/api/sessions").json()
    detail = auth_client.get(f"/api/sessions/{sessions[0]['id']}").json()
    techniques = [s["technique"] for g in detail["exercises"] for s in g["sets"] if g["exercise_id"] == ex]
    assert techniques == ["rest_pause", None]

    csv = auth_client.get("/api/export/csv").text.splitlines()
    header = csv[0].split(",")
    assert "technique" in header
    col = header.index("technique")
    values = [line.split(",")[col] for line in csv[1:] if line]
    assert "rest_pause" in values
