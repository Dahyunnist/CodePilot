"""Budget-aware ordering and deduplication for repository evidence."""

from __future__ import annotations

import hashlib
from typing import Sequence

from codepilot.schemas import ChatMessage, ToolSpec


class ContextSelector:
    """Order tools and retain high-value repair evidence under context pressure."""

    VERSION = "layered-context-v1"
    _LAYERS = (
        ("repository", ("read_project_instructions", "project_map", "list_files")),
        ("search", ("search_code", "search_symbols")),
        ("dependencies", ("find_references",)),
        ("source", ("read_file",)),
        ("test_selection", ("suggest_tests", "run_selected_tests")),
        ("patch", ("apply_patch",)),
        ("verification", ("run_tests", "test_status")),
        ("review", ("git_diff",)),
    )
    _TOOL_LAYERS = {
        tool_name: (layer_index, layer_name)
        for layer_index, (layer_name, tool_names) in enumerate(_LAYERS)
        for tool_name in tool_names
    }
    _RETENTION_PRIORITY = {
        "repository": 0,
        "search": 1,
        "dependencies": 2,
        "source": 3,
        "test_selection": 4,
        "patch": 5,
        "review": 6,
        "verification": 7,
        "other": 1,
    }

    @classmethod
    def layer_for_tool(cls, name: str) -> str:
        """Return one stable context layer for a registered tool name."""
        return cls._TOOL_LAYERS.get(name, (len(cls._LAYERS), "other"))[1]

    @classmethod
    def describe_layers(cls, tools: Sequence[ToolSpec]) -> dict[str, list[str]]:
        """Group the model-visible tool names by their selected layer."""
        result: dict[str, list[str]] = {}
        for tool in tools:
            name = tool.function.name
            result.setdefault(cls.layer_for_tool(name), []).append(name)
        return result

    @classmethod
    def order_tools(cls, tools: Sequence[ToolSpec]) -> list[ToolSpec]:
        return sorted(
            tools,
            key=lambda spec: (
                cls._TOOL_LAYERS.get(spec.function.name, (len(cls._LAYERS), "other"))[0],
                spec.function.name,
            ),
        )

    @classmethod
    def compaction_order(cls, messages: Sequence[ChatMessage]) -> list[int]:
        """Return tool-message indexes from least to most valuable evidence."""
        call_layers = {
            call.id: cls.layer_for_tool(call.name)
            for message in messages
            if message.role == "assistant"
            for call in message.tool_calls
        }
        indexed = [
            (index, call_layers.get(message.tool_call_id or "", "other"))
            for index, message in enumerate(messages)
            if message.role == "tool" and message.content is not None
        ]
        return [
            index
            for index, _layer in sorted(
                indexed,
                key=lambda item: (
                    cls._RETENTION_PRIORITY[item[1]],
                    item[0],
                ),
            )
        ]

    @staticmethod
    def deduplicate_history(messages: list[ChatMessage]) -> int:
        """Replace earlier identical tool output with a compact evidence pointer."""
        latest: dict[str, int] = {}
        replaced = 0
        for index, message in enumerate(messages):
            if message.role != "tool" or message.content is None:
                continue
            digest = hashlib.sha256(message.content.encode("utf-8")).hexdigest()
            previous = latest.get(digest)
            latest[digest] = index
            if previous is None:
                continue
            prior_message = messages[previous]
            prior_message.content = (
                f"重复工具证据已去重；SHA-256: {digest}；"
                f"原始字符数: {len(prior_message.content or '')}。详见较新的相同哈希结果。"
            )
            replaced += 1
        return replaced
