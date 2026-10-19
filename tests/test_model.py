from types import SimpleNamespace
from typing import Any

import pytest

from codepilot.config import ModelConfig
from codepilot.model import ModelClient, ModelClientError, ModelResponseError
from codepilot.schemas import ChatMessage
from codepilot.tools.demo import DEMO_TOOL_SPECS, execute_demo_tool


class FakeCompletions:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.request: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> Any:
        self.request = kwargs
        if self.error:
            raise self.error
        return self.response


def fake_sdk(completions: FakeCompletions) -> Any:
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def model_config() -> ModelConfig:
    return ModelConfig(
        model="test-model",
        api_key="test-key",
        timeout_seconds=15,
        max_completion_tokens=128,
    )


def test_builds_sdk_client_with_connection_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("codepilot.model.OpenAI", fake_openai)
    config = ModelConfig(
        model="test-model",
        api_key="secret-key",
        base_url="https://example.test/v1",
        timeout_seconds=15,
    )

    ModelClient(config)

    assert captured == {
        "api_key": "secret-key",
        "base_url": "https://example.test/v1",
        "timeout": 15.0,
    }


def test_returns_text_and_forwards_request_settings() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4),
    )
    completions = FakeCompletions(response=response)
    client = ModelClient(model_config(), sdk_client=fake_sdk(completions))

    reply = client.complete([ChatMessage(role="user", content="hello")])

    assert reply.text == "done"
    assert reply.tool_calls == []
    assert reply.input_tokens == 11
    assert reply.output_tokens == 4
    assert completions.request == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "hello"}],
        "max_completion_tokens": 128,
    }


def test_serializes_developer_message_as_system_for_chat_completions() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]))]
    )
    completions = FakeCompletions(response=response)
    client = ModelClient(model_config(), sdk_client=fake_sdk(completions))

    client.complete([ChatMessage(role="developer", content="instructions")])

    assert completions.request["messages"] == [
        {"role": "system", "content": "instructions"}
    ]


def test_returns_structured_tool_call() -> None:
    raw_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="calculator",
            arguments='{"operation":"add","left":2.0,"right":3.0}',
        ),
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[raw_call]))
        ]
    )
    completions = FakeCompletions(response=response)
    client = ModelClient(model_config(), sdk_client=fake_sdk(completions))

    reply = client.complete(
        [ChatMessage(role="user", content="add 2 and 3")], DEMO_TOOL_SPECS
    )

    assert reply.tool_calls[0].name == "calculator"
    assert reply.tool_calls[0].arguments["left"] == 2.0
    assert execute_demo_tool(reply.tool_calls[0]) == 5.0
    assert completions.request["tool_choice"] == "auto"
    assert completions.request["tools"][0]["function"]["name"] == "calculator"


def test_rejects_invalid_tool_arguments_json() -> None:
    raw_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="echo", arguments="not-json"),
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[raw_call]))
        ]
    )
    client = ModelClient(
        model_config(), sdk_client=fake_sdk(FakeCompletions(response=response))
    )

    with pytest.raises(ModelResponseError, match="not valid JSON"):
        client.complete([ChatMessage(role="user", content="echo")])


def test_wraps_sdk_errors() -> None:
    client = ModelClient(
        model_config(),
        sdk_client=fake_sdk(FakeCompletions(error=TimeoutError("late"))),
    )

    with pytest.raises(ModelClientError, match="model request failed"):
        client.complete([ChatMessage(role="user", content="hello")])


def test_model_errors_include_provider_status_without_api_key() -> None:
    class ProviderError(Exception):
        status_code = 422

    client = ModelClient(
        model_config(),
        sdk_client=fake_sdk(
            FakeCompletions(error=ProviderError("invalid role test-key"))
        ),
    )

    with pytest.raises(ModelClientError) as error:
        client.complete([ChatMessage(role="user", content="hello")])

    assert "HTTP 422" in str(error.value)
    assert "test-key" not in str(error.value)


def test_model_errors_redact_deepseek_style_key() -> None:
    exposed = "sk-1234567890abcdef_secret"
    client = ModelClient(
        model_config(),
        sdk_client=fake_sdk(FakeCompletions(error=RuntimeError(exposed))),
    )

    with pytest.raises(ModelClientError) as error:
        client.complete([ChatMessage(role="user", content="hello")])

    assert exposed not in str(error.value)
    assert "[redacted]" in str(error.value)

