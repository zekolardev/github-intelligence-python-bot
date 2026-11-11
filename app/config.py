from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    bot_token: SecretStr
    github_token: SecretStr | None = None

    database_path: Path = BASE_DIR / "data" / "bot.sqlite3"
    github_api_url: str = "https://api.github.com"
    github_timeout: float = 15.0
    github_cache_ttl: int = 300
    github_cache_max_entries: int = 256
    log_level: str = "INFO"

    @field_validator("github_timeout")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("GITHUB_TIMEOUT must be greater than zero.")
        return value

    @field_validator("github_cache_ttl")
    @classmethod
    def validate_cache_ttl(cls, value: int) -> int:
        if value < 0:
            raise ValueError("GITHUB_CACHE_TTL cannot be negative.")
        return value

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
