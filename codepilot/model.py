"""OpenAI-compatible chat model adapter."""

import json
import re
from typing import Any, Sequence
from urllib.parse import urlsplit

from openai import OpenAI

from codepilot.config import ModelConfig
from codepilot.schemas import ChatMessage, ModelReply, ToolCall, ToolSpec


class ModelClientError(RuntimeError):
    """Raised when a model request cannot be completed."""


class ModelResponseError(ModelClientError):
    """Raised when a model response violates the expected contract."""


class ModelClient:
    """Send validated messages and tools to a chat completion endpoint."""

    def __init__(
        self,
        config: ModelConfig,
        sdk_client: Any | None = None,
        *,
        max_input_tokens_per_request: int | None = None,
    ) -> None:
        self.config = config
        self._client = sdk_client or self._build_sdk_client(config)
        self.max_input_tokens_per_request = max_input_tokens_per_request
        self.last_input_token_upper_bound = 0

    @staticmethod
    def _build_sdk_client(config: ModelConfig) -> OpenAI:
        client_options: dict[str, Any] = {
            "api_key": config.api_key.get_secret_value(),
            "timeout": config.timeout_seconds,
            "max_retries": 0,
        }
        if config.base_url:
            client_options["base_url"] = config.base_url
        return OpenAI(**client_options)

    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        *,
        max_completion_tokens: int | None = None,
    ) -> ModelReply:
        """Return normalized text or structured tool calls."""
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": [message.to_api_dict() for message in messages],
        }
        output_limit = (
            max_completion_tokens
            if max_completion_tokens is not None
            else self.config.max_completion_tokens
        )
        if _uses_deepseek_chat_api(self.config):
            request["max_tokens"] = output_limit
        else:
            request["max_completion_tokens"] = output_limit
        if tools:
            request["tools"] = [tool.model_dump() for tool in tools]
            request["tool_choice"] = "auto"

        input_token_upper_bound = _input_token_upper_bound(request)
        self.last_input_token_upper_bound = input_token_upper_bound
        if (
            self.max_input_tokens_per_request is not None
            and input_token_upper_bound > self.max_input_tokens_per_request
        ):
            raise ModelClientError(
                "request input upper bound "
                f"({input_token_upper_bound}) exceeds hard limit "
                f"({self.max_input_tokens_per_request}); request was not sent"
            )

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
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        cached_input_tokens = getattr(prompt_details, "cached_tokens", None)
        if cached_input_tokens is None:
            cached_input_tokens = getattr(usage, "prompt_cache_hit_tokens", 0)
        return ModelReply(
            text=message.content,
            tool_calls=tool_calls,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            cached_input_tokens=cached_input_tokens or 0,
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


def _uses_deepseek_chat_api(config: ModelConfig) -> bool:
    """DeepSeek Chat Completions uses `max_tokens`, not OpenAI's newer field."""
    if not config.base_url:
        return config.model.casefold().startswith("deepseek-")
    hostname = (urlsplit(config.base_url).hostname or "").casefold()
    return hostname == "deepseek.com" or hostname.endswith(".deepseek.com")


def _input_token_upper_bound(request: dict[str, Any]) -> int:
    """Conservatively bound text tokens by UTF-8 bytes plus protocol framing."""
    messages = request.get("messages", [])
    tools = request.get("tools", [])
    serialized = json.dumps(
        {"messages": messages, "tools": tools},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    # A text token cannot encode more than its source bytes. Add ample room for
    # provider chat framing and tool-call delimiters that are not in the JSON.
    return len(serialized) + 2_048 + 128 * (len(messages) + len(tools))

