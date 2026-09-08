from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # v2 (§10.1): 첫 관리자 계정 — 사용자 테이블이 비어 있을 때 한 번만 이 값으로 생성된다.
    # 이후 비밀번호는 앱(설정 > 비밀번호 변경)에서 바꾸며 .env 값은 더 이상 쓰이지 않는다.
    APP_PASSWORD: str = Field(min_length=1)
    ADMIN_USERNAME: str = Field(default="admin", min_length=1)
    JWT_SECRET: str = Field(min_length=1)
    DB_PATH: str = "./data/app.db"
    TOKEN_TTL_DAYS: int = 90
    BACKUP_DIR: str = ""  # 비어 있으면 자동 백업 끔 (SETTING.MD §7.4)


@lru_cache
def get_settings() -> Settings:
    return Settings()
