import asyncio
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, backup
from .config import get_settings
from .db import init_db
from .routers import admin, catalog, exercises, sessions, stats

logger = logging.getLogger("app")

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Windows mimetypes 테이블에 woff2가 없어 FileResponse가 text/plain으로 서빙되는 것 방지
mimetypes.add_type("font/woff2", ".woff2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.DB_PATH)
    backup_task = None
    if settings.BACKUP_DIR:
        # 기동 직후 1회 스냅샷: 이전 프로세스가 dirty 상태로 죽었어도 백업 공백이 안 생긴다
        try:
            await asyncio.to_thread(backup.snapshot, settings.DB_PATH, settings.BACKUP_DIR)
        except Exception:
            logger.exception("startup backup failed (server continues)")
        backup_task = asyncio.create_task(
            backup.backup_loop(settings.DB_PATH, settings.BACKUP_DIR)
        )
        logger.info("auto backup enabled -> %s", settings.BACKUP_DIR)
    yield
    if backup_task:
        backup_task.cancel()
        try:
            await backup_task
        except asyncio.CancelledError:
            pass
        if backup._dirty_since is not None:
            # 정상 종료라면 미백업분을 마지막으로 한 번 남긴다
            try:
                await asyncio.to_thread(backup.snapshot, settings.DB_PATH, settings.BACKUP_DIR)
            except Exception:
                logger.exception("shutdown backup failed")


app = FastAPI(title="운동 볼륨 트래킹", lifespan=lifespan)

# auth 라우터는 공개(login/register)와 보호(me/password) 경로를 함께 갖고 경로별로 의존성을 건다
app.include_router(auth.router)
# 핸들러마다 require_auth로 사용자를 받지만, 라우터 수준에서도 한 번 더 걸어 빠뜨림을 막는다
_protected = [Depends(auth.require_auth)]
app.include_router(catalog.router, dependencies=_protected)
app.include_router(exercises.router, dependencies=_protected)
app.include_router(sessions.router, dependencies=_protected)
app.include_router(stats.router, dependencies=_protected)
app.include_router(admin.router)  # require_admin은 라우터 자체에 걸려 있다


@app.middleware("http")
async def mark_data_write(request: Request, call_next):
    """데이터를 바꾸는 API가 성공하면 자동 백업 대상으로 표시 (§7.4). 가입·비밀번호 변경 포함."""
    response = await call_next(request)
    path = request.url.path
    if (
        request.method in {"POST", "PATCH", "PUT", "DELETE"}
        and response.status_code < 400
        and path.startswith("/api/")
        and not path.startswith("/api/auth/login")
        and not path.startswith("/api/export")
    ):
        backup.mark_dirty()
    return response


@app.middleware("http")
async def cache_control(request: Request, call_next):
    # iOS Safari가 헤더 없는 응답을 휴리스틱 캐시해 배포 후에도 구버전 index.html을
    # 계속 쓰는 사고 방지: HTML은 매번 재검증(ETag), 해시 파일명 자산은 영구 캐시.
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/fonts/"):
        response.headers["Cache-Control"] = "public, max-age=2592000"
    elif path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


if FRONTEND_DIST.is_dir():
    _assets = FRONTEND_DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIST):
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
