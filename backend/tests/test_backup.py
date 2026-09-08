import sqlite3
import time

import pytest

from app import backup


@pytest.fixture(autouse=True)
def reset_backup_state():
    def _reset():
        backup._dirty_since = None
        backup._last_write = None
        backup._fail_count = 0
        backup._retry_not_before = 0.0

    _reset()
    yield
    _reset()


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (v INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    conn.close()


def test_snapshot_creates_consistent_copy(tmp_path):
    db = tmp_path / "src.db"
    _make_db(db)
    dest = tmp_path / "bk"

    out = backup.snapshot(str(db), str(dest))

    assert out.exists()
    conn = sqlite3.connect(out)
    assert conn.execute("SELECT v FROM t").fetchone()[0] == 42
    conn.close()
    assert not (dest / ".app-snapshot.tmp").exists()


def test_snapshot_same_day_overwrites(tmp_path):
    db = tmp_path / "src.db"
    _make_db(db)
    dest = tmp_path / "bk"

    first = backup.snapshot(str(db), str(dest))
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO t VALUES (7)")
    conn.commit()
    conn.close()
    second = backup.snapshot(str(db), str(dest))

    assert first == second
    assert len(list(dest.glob("app-*.db"))) == 1
    conn = sqlite3.connect(second)
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2
    conn.close()


def test_prune_keeps_recent_snapshots(tmp_path):
    dest = tmp_path / "bk"
    dest.mkdir()
    for i in range(35):
        (dest / f"app-2026{i:04d}.db").write_bytes(b"x")

    backup._prune(dest)

    remaining = sorted(p.name for p in dest.glob("app-*.db"))
    assert len(remaining) == backup.KEEP_SNAPSHOTS
    assert remaining[0] == "app-20260005.db"  # 오래된 5개 삭제


def test_mark_dirty_sets_timestamps():
    assert backup._dirty_since is None
    backup.mark_dirty()
    first_dirty = backup._dirty_since
    assert first_dirty is not None
    time.sleep(0.01)
    backup.mark_dirty()
    assert backup._dirty_since == first_dirty  # 최초 dirty 시각 유지
    assert backup._last_write is not None
    assert backup._last_write > first_dirty


def test_should_snapshot_decision():
    now = time.monotonic()
    assert backup._should_snapshot(now) is False  # dirty 아님

    backup._dirty_since = now - 100
    backup._last_write = now - 100
    assert backup._should_snapshot(now) is False  # idle 100s < 300s

    backup._last_write = now - backup.IDLE_SECONDS
    assert backup._should_snapshot(now) is True  # idle 충족

    backup._last_write = now - 10  # 쓰기 직후지만
    backup._dirty_since = now - backup.MAX_DIRTY_SECONDS
    assert backup._should_snapshot(now) is True  # 강제 백업 시각 도달

    backup._retry_not_before = now + 60
    assert backup._should_snapshot(now) is False  # 백오프 중


def test_tick_failure_keeps_dirty_and_backs_off(tmp_path, monkeypatch):
    import asyncio

    backup._dirty_since = time.monotonic() - backup.IDLE_SECONDS - 1
    backup._last_write = backup._dirty_since

    def boom(db, dest):
        raise OSError("locked")

    monkeypatch.setattr(backup, "snapshot", boom)
    asyncio.run(backup._tick("x.db", str(tmp_path)))

    assert backup._dirty_since is not None  # dirty 유지 → 재시도 대상
    assert backup._fail_count == 1
    assert backup._retry_not_before > time.monotonic()


def test_tick_write_during_snapshot_keeps_dirty(tmp_path, monkeypatch):
    import asyncio

    db = tmp_path / "src.db"
    _make_db(db)
    backup._dirty_since = time.monotonic() - backup.IDLE_SECONDS - 1
    backup._last_write = backup._dirty_since

    real_snapshot = backup.snapshot

    def snapshot_with_concurrent_write(db_path, dest):
        result = real_snapshot(db_path, dest)
        backup.mark_dirty()  # 스냅샷 도중 새 쓰기 도착을 재현
        return result

    monkeypatch.setattr(backup, "snapshot", snapshot_with_concurrent_write)
    asyncio.run(backup._tick(str(db), str(tmp_path / "bk")))

    assert backup._dirty_since is not None  # 꼬리 쓰기가 백업 안 된 상태로 남았음을 인지
    assert backup._fail_count == 0


def test_tick_success_clears_dirty(tmp_path):
    import asyncio

    db = tmp_path / "src.db"
    _make_db(db)
    backup._dirty_since = time.monotonic() - backup.IDLE_SECONDS - 1
    backup._last_write = backup._dirty_since

    asyncio.run(backup._tick(str(db), str(tmp_path / "bk")))

    assert backup._dirty_since is None
    assert (tmp_path / "bk").glob("app-*.db")


def test_write_api_marks_dirty(auth_client):
    assert backup._dirty_since is None
    res = auth_client.post("/api/bodyweight", json={"date": "2026-07-20", "weight_kg": 70})
    assert res.status_code in (200, 201)
    assert backup._dirty_since is not None


def test_read_and_auth_do_not_mark_dirty(auth_client):
    auth_client.get("/api/exercises")
    assert backup._dirty_since is None
    auth_client.post("/api/auth/login", json={"password": "test-password"})
    assert backup._dirty_since is None


def test_failed_write_does_not_mark_dirty(auth_client):
    res = auth_client.post("/api/bodyweight", json={"date": "invalid", "weight_kg": 70})
    assert res.status_code == 422
    assert backup._dirty_since is None
