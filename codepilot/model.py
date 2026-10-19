"""OpenAI-compatible chat model adapter."""

import json
import re
from typing import Any, Sequence

from openai import OpenAI

from codepilot.config import ModelConfig
from codepilot.schemas import ChatMessage, ModelReply, ToolCall, ToolSpec


class ModelClientError(RuntimeError):
    """Raised when a model request cannot be completed."""


class ModelResponseError(ModelClientError):
    """Raised when a model response violates the expected contract."""


class ModelClient:
    """Send validated messages and tools to a chat completion endpoint."""

    def __init__(self, config: ModelConfig, sdk_client: Any | None = None) -> None:
        self.config = config
        self._client = sdk_client or self._build_sdk_client(config)

    @staticmethod
    def _build_sdk_client(config: ModelConfig) -> OpenAI:
        client_options: dict[str, Any] = {
            "api_key": config.api_key.get_secret_value(),
            "timeout": config.timeout_seconds,
        }
        if config.base_url:
            client_options["base_url"] = config.base_url
        return OpenAI(**client_options)

    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
    ) -> ModelReply:
        """Return normalized text or structured tool calls."""
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": [message.to_api_dict() for message in messages],
            "max_completion_tokens": self.config.max_completion_tokens,
        }
        if tools:
            request["tools"] = [tool.model_dump() for tool in tools]
            request["tool_choice"] = "auto"

        try:
            completion = self._client.chat.completions.create(**request)
        except Exception as exc:
            message = str(exc)
            secret = self.config.api_key.get_secret_value()
            if secret:
                message = message.replace(secret, "[redacted]")
            message = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[redacted]", message)
            status = getattr(exc, "status_code", None)
            status_text = f", HTTP {status}" if status is not None else ""
            raise ModelClientError(
                f"model request failed ({type(exc).__name__}{status_text}): "
                f"{message[:500]}"
            ) from exc

        if not completion.choices:
            raise ModelResponseError("model returned no choices")

        message = completion.choices[0].message
        tool_calls = [self._parse_tool_call(call) for call in message.tool_calls or []]
        if message.content is None and not tool_calls:
            raise ModelResponseError("model returned neither text nor tool calls")

        usage = getattr(completion, "usage", None)
        return ModelReply(
            text=message.content,
            tool_calls=tool_calls,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

    @staticmethod
    def _parse_tool_call(raw_call: Any) -> ToolCall:
        try:
            arguments = json.loads(raw_call.function.arguments)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ModelResponseError("tool call arguments are not valid JSON") from exc

        if not isinstance(arguments, dict):
            raise ModelResponseError("tool call arguments must be a JSON object")

        return ToolCall(
            id=raw_call.id,
            name=raw_call.function.name,
            arguments=arguments,
        )

