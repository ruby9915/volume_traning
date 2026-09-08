from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 빈 값이면 기동(lifespan의 get_settings) 시점에 실패 — 빈 비밀번호 공개 배포 방지
    APP_PASSWORD: str = Field(min_length=1)
    JWT_SECRET: str = Field(min_length=1)
    DB_PATH: str = "./data/app.db"
    TOKEN_TTL_DAYS: int = 90
    BACKUP_DIR: str = ""  # 비어 있으면 자동 백업 끔 (SETTING.MD §7.4)


@lru_cache
def get_settings() -> Settings:
    return Settings()
