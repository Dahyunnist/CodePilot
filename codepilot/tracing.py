"""Bounded, secret-safe JSONL run tracing."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opentelemetry import trace as otel_trace
from opentelemetry.trace import Status, StatusCode

from codepilot.schemas import ToolCall, ToolResult
from codepilot.security import redact_sensitive_text


_SENSITIVE_FIELD = re.compile(
    r"(?i)^(?:api[_-]?key|access[_-]?token|auth(?:orization)?|"
    r"bearer[_-]?token|secret|password|passwd|credential)$"
)
_PRIVATE_FIELD = re.compile(
    r"(?i)^(?:content|prompt|observation|patch|diff|source|stdout|stderr|messages|error)$"
)


class TraceLogger:
    """Append compact events for one run without logging source or secrets."""

    def __init__(
        self,
        path: Path,
        run_id: str,
        trace_id: str | None = None,
        *,
        otel_tracer: Any | None = None,
    ) -> None:
        self.path = path.resolve()
        self.run_id = run_id
        self.trace_id = trace_id or run_id
        self.root_span_id = uuid.uuid4().hex
        self._last_model_span_id: str | None = None
        self._tool_spans: dict[str, tuple[str, str]] = {}
        self._otel_tracer = otel_tracer or otel_trace.get_tracer("codepilot")
        self._otel_spans: dict[str, Any] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, event: str, step: int, **fields: Any) -> None:
        span_id = str(fields.pop("span_id", uuid.uuid4().hex))
        parent_span_id = str(fields.pop("parent_span_id", self.root_span_id))
        if event == "run_started":
            span_id = self.root_span_id
            parent_span_id = ""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "event": event,
            "step": step,
            **_redact_value(fields),
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._record_otel_span(record)
        if event == "model_finished":
            self._last_model_span_id = span_id

    def _record_otel_span(self, record: dict[str, Any]) -> None:
        """Mirror lifecycle events into OpenTelemetry without exporting payloads."""
        event = record["event"]
        span_id = record["span_id"]
        parent_id = record.get("parent_span_id", "")
        fields = {
            key: value
            for key, value in record.items()
            if key not in {
                "timestamp", "run_id", "trace_id", "span_id", "parent_span_id",
                "event", "step", "arguments", "error", "diff", "stdout", "stderr",
            }
            and isinstance(value, (str, int, float, bool))
        }

        if event == "run_started":
            span = self._otel_tracer.start_span(
                "codepilot.run",
                attributes={"codepilot.run_id": self.run_id},
            )
            self._otel_spans[span_id] = span
            return
        if event == "model_budget_reserved":
            self._start_span(
                span_id,
                parent_id,
                "codepilot.model.call",
                {"codepilot.run_id": self.run_id, "codepilot.step": record["step"], **fields},
            )
            return
        if event == "tool_started":
            self._start_span(
                span_id,
                parent_id,
                "codepilot.tool.execute",
                {"codepilot.run_id": self.run_id, "codepilot.step": record["step"], **fields},
            )
            return
        if event in {"writeback_approval_requested", "writeback_started"}:
            self._start_span(
                span_id,
                parent_id,
                "codepilot.writeback.approval" if event.endswith("requested") else "codepilot.writeback.apply",
                {"codepilot.run_id": self.run_id, **fields},
            )
            return

        close_span = None
        if event == "model_finished":
            close_span = self._otel_spans.get(span_id)
        elif event == "model_failed":
            close_span = self._otel_spans.pop(span_id, None)
        elif event == "tool_finished":
            close_span = self._otel_spans.pop(span_id, None)
        elif event == "writeback_approval_decided":
            close_span = self._otel_spans.pop("writeback_approval", None)
        elif event == "writeback_finished":
            close_span = self._otel_spans.pop("writeback_apply", None)
        elif event == "run_finished":
            close_span = self._otel_spans.pop(self.root_span_id, None)

        if close_span is None:
            return
        for key, value in fields.items():
            close_span.set_attribute(f"codepilot.{key}", value)
        if (
            event == "model_failed"
            or fields.get("ok") is False
            or fields.get("approved") is False
            or fields.get("status") in {"failed", "timeout", "budget_exceeded"}
            or fields.get("outcome") in {"rejected", "stale_patch"}
        ):
            close_span.set_attribute("codepilot.error_present", True)
            close_span.set_status(Status(StatusCode.ERROR))
        close_span.end()
        if event == "run_finished":
            self._otel_spans.clear()

    def _start_span(
        self, span_id: str, parent_id: str, name: str, attributes: dict[str, Any]
    ) -> None:
        parent = self._otel_spans.get(parent_id)
        context = (
            otel_trace.set_span_in_context(parent)
            if parent is not None
            else None
        )
        span = self._otel_tracer.start_span(name, context=context, attributes=attributes)
        self._otel_spans[span_id] = span
        if name == "codepilot.writeback.approval":
            self._otel_spans["writeback_approval"] = span
        elif name == "codepilot.writeback.apply":
            self._otel_spans["writeback_apply"] = span

    def tool_started(self, step: int, call: ToolCall) -> None:
        span_id = uuid.uuid4().hex
        parent_span_id = self._last_model_span_id or self.root_span_id
        self._tool_spans[call.id] = (span_id, parent_span_id)
        self.event(
            "tool_started",
            step,
            tool=call.name,
            call_id=call.id,
            arguments=_argument_summary(call),
            span_id=span_id,
            parent_span_id=parent_span_id,
        )

    def tool_finished(
        self, step: int, result: ToolResult, call_id: str | None = None
    ) -> None:
        span_id, parent_span_id = self._tool_spans.pop(
            call_id or "", (uuid.uuid4().hex, self.root_span_id)
        )
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
            call_id=call_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return {
            key: "[OMITTED]"
            if _PRIVATE_FIELD.fullmatch(str(key))
            else "[REDACTED]"
            if _SENSITIVE_FIELD.fullmatch(str(key))
            else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


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
