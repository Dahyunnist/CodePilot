"""Validated model configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ModelConfig(BaseModel):
    """Settings required for one model request."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model: str = Field(min_length=1)
    api_key: SecretStr
    base_url: str | None = None
    timeout_seconds: float = Field(default=60, gt=0)
    max_completion_tokens: int = Field(default=1024, gt=0)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("API key must not be empty")
        return value

    @classmethod
    def from_env(cls, dotenv_path: Path | None = None) -> "ModelConfig":
        """Load project settings from .env and process environment variables."""
        env_file = dotenv_path or Path(__file__).resolve().parents[1] / ".env"
        load_dotenv(dotenv_path=env_file, override=False)
        return cls(
            model=os.getenv("LLM_MODEL", ""),
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL") or None,
            timeout_seconds=os.getenv("LLM_TIMEOUT_SECONDS", "60"),
            max_completion_tokens=os.getenv(
                "LLM_MAX_COMPLETION_TOKENS", "1024"
            ),
        )

