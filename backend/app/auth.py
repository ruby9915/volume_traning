import asyncio
import datetime as dt
import secrets

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    settings = get_settings()
    if not secrets.compare_digest(
        body.password.encode(), settings.APP_PASSWORD.encode()
    ):
        await asyncio.sleep(1)
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다")
    ttl = dt.timedelta(days=settings.TOKEN_TTL_DAYS)
    token = jwt.encode(
        {"exp": dt.datetime.now(dt.timezone.utc) + ttl},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    return LoginResponse(access_token=token, expires_in=int(ttl.total_seconds()))


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    if credentials is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    try:
        jwt.decode(
            credentials.credentials,
            get_settings().JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["exp"]},  # exp 없는 토큰 거부 (§4.1)
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다")
