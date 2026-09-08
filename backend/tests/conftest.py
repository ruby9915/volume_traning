import sqlite3

import pytest
from fastapi.testclient import TestClient

TEST_PASSWORD = "test-password"
TEST_JWT_SECRET = "a" * 64


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", TEST_PASSWORD)
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
    with TestClient(app) as c:  # lifespan 실행 → init_db + seed
        yield c


@pytest.fixture()
def auth_client(client):
    res = client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture()
def db(auth_client):
    """시드된 테스트 DB에 대한 raw 연결 — API를 우회해 fixture 데이터를 직접 넣을 때."""
    from app.config import get_settings

    conn = sqlite3.connect(get_settings().DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()
