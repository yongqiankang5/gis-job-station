"""应用配置管理模块。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量或 .env 文件读取应用配置。"""

    app_name: str = "GIS 遥感就业情报站"
    database_url: str = Field(
        default="sqlite:///./data/gis_jobs.db", validation_alias="DATABASE_URL"
    )
    secret_key: str = Field(
        default="please-change-me", validation_alias="SECRET_KEY"
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8000"],
        validation_alias="CORS_ORIGINS",
    )
    debug: bool = Field(default=False, validation_alias="DEBUG")
    redis_url: str | None = Field(default=None, validation_alias="REDIS_URL")
    enable_scheduler: bool = Field(
        default=False, validation_alias="ENABLE_SCHEDULER"
    )
    chromium_path: str | None = Field(
        default=None, validation_alias="CHROMIUM_PATH"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """返回缓存后的全局配置对象。"""

    return Settings()


settings = get_settings()
