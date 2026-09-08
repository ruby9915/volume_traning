"""데이터 변경 감지 자동 백업 (SETTING.MD §7.4).

쓰기 API 성공 시 mark_dirty()가 호출되고, 백그라운드 루프가
"마지막 쓰기 후 IDLE_SECONDS 동안 조용하면" (= 운동 종료로 간주) 스냅샷을 만든다.
쓰기가 계속 이어져도 MAX_DIRTY_SECONDS가 지나면 강제로 한 번 만든다.
스냅샷은 VACUUM INTO라 서비스 중에도 일관된 사본이 보장된다.
재시작으로 dirty 상태가 유실되는 창은 기동 직후 1회 스냅샷(main.py lifespan)으로 메운다.
"""

import asyncio
import logging
import os
import sqlite3
import time
from datetime import date
from pathlib import Path

logger = logging.getLogger("app.backup")

IDLE_SECONDS = 300
MAX_DIRTY_SECONDS = 1800
CHECK_INTERVAL_SECONDS = 30
MAX_BACKOFF_SECONDS = 1800
KEEP_SNAPSHOTS = 30

_dirty_since: float | None = None
_last_write: float | None = None
_fail_count = 0
_retry_not_before = 0.0


def mark_dirty() -> None:
    global _dirty_since, _last_write
    now = time.monotonic()
    if _dirty_since is None:
        _dirty_since = now
    _last_write = now


def snapshot(db_path: str, backup_dir: str) -> Path:
    """같은 날짜 파일(app-YYYYMMDD.db)을 최신 상태로 교체하고 오래된 것을 정리한다."""
    dest_dir = Path(backup_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / f"app-{date.today():%Y%m%d}.db"
    tmp = dest_dir / ".app-snapshot.tmp"
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM INTO ?", (str(tmp),))
    finally:
        conn.close()
    os.replace(tmp, final)  # 대상 폴더 안에서 교체 → 항상 같은 볼륨
    _prune(dest_dir)
    return final


def _prune(dest_dir: Path) -> None:
    snaps = sorted(dest_dir.glob("app-*.db"))
    for old in snaps[:-KEEP_SNAPSHOTS]:
        try:
            old.unlink()
        except OSError:
            pass


def _should_snapshot(now: float) -> bool:
    if _dirty_since is None:
        return False
    if now < _retry_not_before:
        return False
    idle = now - (_last_write if _last_write is not None else now)
    return idle >= IDLE_SECONDS or (now - _dirty_since) >= MAX_DIRTY_SECONDS


async def _tick(db_path: str, backup_dir: str) -> None:
    """루프 1회분. 판정 → 스냅샷 → 상태 갱신 (테스트 가능하도록 분리)."""
    global _dirty_since, _fail_count, _retry_not_before
    now = time.monotonic()
    if not _should_snapshot(now):
        return
    marker = _last_write
    try:
        path = await asyncio.to_thread(snapshot, db_path, backup_dir)
    except Exception:
        # dirty 유지 → 지수 백오프 후 재시도 (OneDrive 잠금 등 일시 오류 / 경로 오타 등 영구 오류 공통)
        _fail_count += 1
        _retry_not_before = now + min(
            CHECK_INTERVAL_SECONDS * (2 ** _fail_count), MAX_BACKOFF_SECONDS
        )
        if _fail_count == 1:
            logger.exception("auto backup failed; retrying with backoff")
        else:
            logger.warning("auto backup still failing (attempt %d)", _fail_count)
        return
    _fail_count = 0
    _retry_not_before = 0.0
    if _last_write == marker:
        # 스냅샷 도중 새 쓰기가 들어왔다면 dirty를 유지해 꼬리 누락을 막는다
        _dirty_since = None
    logger.info("auto backup written: %s", path)


async def backup_loop(db_path: str, backup_dir: str) -> None:
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        await _tick(db_path, backup_dir)
