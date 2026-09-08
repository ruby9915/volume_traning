import sqlite3

import pytest
from fastapi.testclient import TestClient

TEST_PASSWORD = "test-password"
TEST_ADMIN = "admin"
TEST_JWT_SECRET = "a" * 64


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", TEST_PASSWORD)
    monkeypatch.setenv("ADMIN_USERNAME", TEST_ADMIN)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BACKUP_DIR", "")  # 테스트에서 실 백업 폴더로 쓰지 않도록 차단

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app as fastapi_app

    yield fastapi_app
    get_settings.cache_clear()


@pytest.fixture()
def client(app):
    with TestClient(app) as c:  # lifespan 실행 → init_db + seed + 첫 관리자 생성
        yield c


def login(client: TestClient, username: str, password: str) -> None:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"


@pytest.fixture()
def auth_client(client):
    """마이그레이션이 만든 첫 관리자(admin)로 로그인한 클라이언트."""
    login(client, TEST_ADMIN, TEST_PASSWORD)
    return client


@pytest.fixture()
def user_client(app, client):
    """일반 사용자(bob)로 가입·로그인한 두 번째 클라이언트 — 사용자 범위 격리 검증용."""
    with TestClient(app) as c:
        res = c.post(
            "/api/auth/register",
            json={"username": "bob", "password": "bob-pass", "display_name": "밥"},
        )
        assert res.status_code == 201, res.text
        c.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
        yield c


@pytest.fixture()
def db(auth_client):
    """시드된 테스트 DB에 대한 raw 연결 — API를 우회해 fixture 데이터를 직접 넣을 때."""
    from app.config import get_settings

    conn = sqlite3.connect(get_settings().DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()
