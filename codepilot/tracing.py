"""Bounded, secret-safe JSONL run tracing."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codepilot.schemas import ToolCall, ToolResult
from codepilot.security import redact_sensitive_text


class TraceLogger:
    """Append compact events for one run without logging source or secrets."""

    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path.resolve()
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, event: str, step: int, **fields: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
            "step": step,
            **fields,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def tool_started(self, step: int, call: ToolCall) -> None:
        self.event(
            "tool_started",
            step,
            tool=call.name,
            call_id=call.id,
            arguments=_argument_summary(call),
        )

    def tool_finished(self, step: int, result: ToolResult) -> None:
        self.event(
            "tool_finished",
            step,
            tool=result.tool_name,
            ok=result.ok,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            error_type=result.error_type,
            stdout_chars=len(result.stdout),
            stderr_chars=len(result.stderr),
        )


def _argument_summary(call: ToolCall) -> dict[str, Any]:
    """Keep routing metadata while excluding patch contents and secret values."""
    summary: dict[str, Any] = {"keys": sorted(call.arguments)}
    if "path" in call.arguments:
        summary["path"] = str(call.arguments["path"])[:300]
    if call.name == "search_code" and "query" in call.arguments:
        summary["query_chars"] = len(str(call.arguments["query"]))
    if call.name == "read_file" and "reason" in call.arguments:
        summary["reason"] = redact_sensitive_text(str(call.arguments["reason"]))[:240]
    return summary
