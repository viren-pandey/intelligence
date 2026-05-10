from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://nexus:nexus@localhost:5432/nexus"
    REDIS_URL: str = "redis://localhost:6379/0"
    GROQ_API_KEY: str = ""
    PROXY_API_KEY: str = ""
    PROXY_LIST: list[str] = []
    ADMIN_API_KEY: str = "nexus-admin-dev"
    NEXUS_API_KEY: str = "nexus-client-dev"
    MAX_CRAWLERS: int = 100
    CRAWL_TIMEOUT_SECONDS: int = 120
    MAX_RESULTS_PER_REQUEST: int = 50
    DEBUG: bool = False
    CACHE_TTL_SECONDS: int = 21600
    MIN_JOBS_FOR_CACHED_RESPONSE: int = 1
    FRESHNESS_CUTOFF: float = 0.6
    DEAD_LINK_CHECK_TIMEOUT: int = 5
    DEFAULT_FREE_CREDITS: int = 50
    DEFAULT_FREE_RATE_LIMIT: int = 50
    WEBHOOK_RETRY_MAX: int = 3
    ADMIN_EMAIL: str = "admin@nexus.local"
    CRAWL_INTERVAL_MINUTES: int = 30
    SKIP_PLAYWRIGHT_SOURCES: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
