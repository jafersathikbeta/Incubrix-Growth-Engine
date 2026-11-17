"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings for the Incubrix Growth Engine."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")
    groq_api_keys: str = Field(default="", alias="GROQ_API_KEYS")
    database_path: str = Field(default="leads.db", alias="DATABASE_PATH")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_email: str = Field(default="", alias="SMTP_EMAIL")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")

    @field_validator("smtp_port", mode="before")
    @classmethod
    def _coerce_port(cls, value: object) -> int:
        if value is None or value == "":
            return 587
        return int(value)

    def groq_keys(self) -> List[str]:
        """Return a cleaned list of Groq API keys for failover."""
        if not self.groq_api_keys.strip():
            return []
        return [k.strip().strip('"') for k in self.groq_api_keys.split(",") if k.strip()]

    def resolve_db_path(self) -> Path:
        """Resolve the SQLite database path relative to the project root."""
        path = Path(self.database_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


def reload_settings() -> Settings:
    """Clear cache and reload settings from .env / environment."""
    get_settings.cache_clear()
    return get_settings()


def _quote_env(value: str) -> str:
    cleaned = (value or "").strip().strip('"').strip("'")
    return f'"{cleaned}"'


def save_api_keys_to_env(
    youtube_api_key: str,
    groq_api_keys: str,
    env_path: Path | None = None,
) -> Path:
    """
    Persist YOUTUBE_API_KEY and GROQ_API_KEYS into the project .env file.
    Preserves other existing keys. Reloads settings cache afterward.
    """
    path = env_path or (Path.cwd() / ".env")
    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, val = stripped.partition("=")
            existing[key.strip()] = val.strip()

    existing["YOUTUBE_API_KEY"] = _quote_env(youtube_api_key)
    existing["GROQ_API_KEYS"] = _quote_env(groq_api_keys)

    # Keep a stable preferred order for common keys
    preferred = [
        "YOUTUBE_API_KEY",
        "GROQ_API_KEYS",
        "DATABASE_PATH",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_EMAIL",
        "SMTP_PASSWORD",
    ]
    lines: list[str] = []
    seen: set[str] = set()
    for key in preferred:
        if key in existing:
            lines.append(f"{key}={existing[key]}")
            seen.add(key)
    for key, val in existing.items():
        if key not in seen:
            lines.append(f"{key}={val}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reload_settings()
    return path
