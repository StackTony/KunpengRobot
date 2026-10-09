"""应用配置 (pydantic-settings, 环境变量优先, .env 兜底)."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 基础
    APP_NAME: str = "KunpengRobot"
    DEBUG: bool = False
    API_PREFIX: str = "/api"

    # 安全
    SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 数据库 / 缓存
    DATABASE_URL: str = "postgresql+asyncpg://kunpeng:kunpeng@localhost:5432/kunpeng"
    REDIS_URL: str = "redis://localhost:6379/0"

    # 存储
    DATA_DIR: str = "./data"
    MAX_UPLOAD_SIZE_MB: int = 2048

    # Redis Stream 任务队列
    QUEUE_STREAM: str = "kunpeng:tasks"
    QUEUE_GROUP: str = "workers"
    QUEUE_MAX_LEN: int = 100000

    # 事件通道 (SSE 断线补发)
    EVENT_STREAM_PREFIX: str = "kunpeng:events"
    EVENT_CHANNEL_PREFIX: str = "kunpeng:ch"
    EVENT_TTL_SECONDS: int = 3600

    # Worker
    WORKER_CONCURRENCY: int = 8          # 单 Worker 同时分析任务数
    WORKER_CONSUMER_NAME: str = "worker-1"
    WORKER_PENDING_TIMEOUT_MS: int = 600000  # 超过该时长的 pending 任务视为崩溃遗留, 重新投递

    # LLM (OpenAI 兼容 API, 留空则降级为纯规则)
    LLM_API_BASE: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_MAX_CONCURRENCY: int = 4

    # 指标
    METRIC_RETENTION_DAYS: int = 90

    # 上传限流 (按用户, Redis 计数)
    UPLOAD_RATE_LIMIT_PER_MIN: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
