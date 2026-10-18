import pytest
from pydantic import ValidationError

from codepilot.config import ModelConfig


def test_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("LLM_MAX_COMPLETION_TOKENS", "256")

    config = ModelConfig.from_env()

    assert config.model == "test-model"
    assert config.timeout_seconds == 12.5
    assert config.max_completion_tokens == 256


def test_config_rejects_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        ModelConfig.from_env()

