"""Bounded, secret-safe JSONL run tracing."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from enum import StrEnum

from opentelemetry import trace as otel_trace
from opentelemetry.trace import Status, StatusCode

from codepilot.schemas import ToolCall, ToolResult
from codepilot.security import redact_sensitive_text


_SENSITIVE_FIELD = re.compile(
    r"(?i)^(?:api[_-]?key|aws[_-]?access[_-]?key(?:[_-]?id)?|"
    r"aws[_-]?secret[_-]?access[_-]?key|secret[_-]?access[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|bearer[_-]?token|"
    r"client[_-]?secret|private[_-]?key|auth(?:orization)?|"
    r"secret|secrets|password|passwd|credential|credentials|token)$"
)
_PRIVATE_FIELD = re.compile(
    r"(?i)^(?:content|prompt|observation|patch|diff|source|stdout|stderr|messages|error)$"
)

class StandardTraceEvent(StrEnum):
    TIMEOUT = "timeout"
    RETRY = "retry"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNSAFE_ACTION_BLOCKED = "unsafe_action_blocked"
    CANCEL = "cancel"
    CHECKPOINT_RESUME = "checkpoint_resume"
    APPROVAL_EXPIRED = "approval_expired"

def validate_event_name(event: str) -> str:
    """Validate event spelling while preserving legacy custom event names."""
    if not isinstance(event, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", event):
        raise ValueError(f"invalid trace event name: {event!r}")
    return StandardTraceEvent(event).value if event in StandardTraceEvent._value2member_map_ else event


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
        self._evaluation_active = False
        self._last_model_span_id: str | None = None
        self._tool_spans: dict[str, tuple[str, str]] = {}
        self._patch_spans: dict[str, str] = {}
        self._otel_tracer = otel_tracer or otel_trace.get_tracer("codepilot")
        self._otel_spans: dict[str, Any] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, event: str, step: int, **fields: Any) -> None:
        event = validate_event_name(event)
        span_id = str(fields.pop("span_id", uuid.uuid4().hex))
        parent_span_id = str(fields.pop("parent_span_id", self.root_span_id))
        if event in {"run_started", "evaluation_started"}:
            span_id = self.root_span_id
            parent_span_id = ""
            if event == "evaluation_started":
                self._evaluation_active = True
        record = {
            **_redact_value(fields),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "event": event,
            "step": step,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        # JSONL is the durable local trace. An optional telemetry exporter must
        # never turn a completed JSONL write into an agent/tool failure.
        try:
            self._record_otel_span(record)
        except Exception:
            # Keep tracing best-effort when an SDK/exporter is unavailable.
            pass
        if event == "model_finished":
            self._last_model_span_id = span_id
        if event == "evaluation_finished":
            self._evaluation_active = False

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

        if event in {"run_started", "evaluation_started"}:
            if span_id in self._otel_spans:
                return
            span = self._otel_tracer.start_span(
                "codepilot.run",
                attributes={
                    "codepilot.run_id": self.run_id,
                    "codepilot.trace_id": self.trace_id,
                },
            )
            self._otel_spans[span_id] = span
            return
        if event == "verification_started":
            self._start_span(
                span_id,
                parent_id,
                "codepilot.verification",
                {
                    "codepilot.run_id": self.run_id,
                    "codepilot.trace_id": self.trace_id,
                    "codepilot.step": record["step"],
                    **fields,
                },
            )
            return
        if event == "model_budget_reserved":
            self._start_span(
                span_id,
                parent_id,
                "codepilot.model.call",
                {
                    "codepilot.run_id": self.run_id,
                    "codepilot.trace_id": self.trace_id,
                    "codepilot.step": record["step"],
                    **fields,
                },
            )
            return
        if event == "tool_started":
            self._start_span(
                span_id,
                parent_id,
                "codepilot.tool.execute",
                {
                    "codepilot.run_id": self.run_id,
                    "codepilot.trace_id": self.trace_id,
                    "codepilot.step": record["step"],
                    **fields,
                },
            )
            return
        if event == "patch_started":
            self._start_span(span_id, parent_id, "codepilot.workspace.patch", {
                "codepilot.run_id": self.run_id, "codepilot.trace_id": self.trace_id,
                "codepilot.tool": "apply_patch",
            })
            return
        if event in {"writeback_approval_requested", "writeback_started"}:
            self._start_span(
                span_id,
                parent_id,
                "codepilot.writeback.approval" if event.endswith("requested") else "codepilot.writeback.apply",
                {
                    "codepilot.run_id": self.run_id,
                    "codepilot.trace_id": self.trace_id,
                    **fields,
                },
            )
            return

        if event == "approval_expired" or (
            event == "writeback_approval_decided"
            and "writeback_approval" not in self._otel_spans
        ):
            # Durable approval may be decided after process restart, when the
            # request span is no longer in this logger's in-memory span map.
            decision_span = self._otel_tracer.start_span(
                "codepilot.writeback.approval.decision",
                attributes={
                    "codepilot.run_id": self.run_id,
                    "codepilot.trace_id": self.trace_id,
                    "codepilot.approval_span_id": span_id,
                    "codepilot.step": record["step"],
                    **fields,
                },
            )
            if event == "approval_expired" or fields.get("approved") is False:
                decision_span.set_attribute("codepilot.error_present", True)
                decision_span.set_status(Status(StatusCode.ERROR))
            decision_span.end()
            return

        close_span = None
        if event == "model_finished":
            close_span = self._otel_spans.get(span_id)
        elif event == "model_failed":
            close_span = self._otel_spans.pop(span_id, None)
        elif event == "tool_finished":
            close_span = self._otel_spans.pop(span_id, None)
        elif event == "patch_finished":
            close_span = self._otel_spans.pop(span_id, None)
        elif event == "writeback_approval_decided":
            close_span = self._otel_spans.pop("writeback_approval", None)
        elif event == "writeback_finished":
            close_span = self._otel_spans.pop("writeback_apply", None)
        elif event == "verification_finished":
            close_span = self._otel_spans.pop(span_id, None)
        elif event == "run_finished" and not self._evaluation_active:
            close_span = self._otel_spans.pop(self.root_span_id, None)
        elif event == "evaluation_finished":
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
            "tool_finished", step, tool=result.tool_name, ok=result.ok,
            exit_code=result.exit_code, duration_ms=result.duration_ms,
            error_type=result.error_type, stdout_chars=len(result.stdout),
            stderr_chars=len(result.stderr), call_id=call_id,
            span_id=span_id, parent_span_id=parent_span_id,
        )

    def patch_started(self, call: ToolCall) -> None:
        span_id = uuid.uuid4().hex
        tool_span = self._tool_spans.get(call.id)
        parent_id = tool_span[0] if tool_span else self.root_span_id
        self._patch_spans[call.id] = span_id
        self.event("patch_started", 0, span_id=span_id, parent_span_id=parent_id)

    def patch_finished(self, call: ToolCall, result: ToolResult) -> None:
        span_id = self._patch_spans.pop(call.id, None)
        if span_id:
            self.event("patch_finished", 0, span_id=span_id,
                       parent_span_id=self._tool_spans.get(call.id, ("", ""))[0],
                       ok=result.ok, error_type=result.error_type or "")

    @property
    def current_span_id(self) -> str:
        """Return most recent model span for lifecycle events after agent completion."""
        return self._last_model_span_id or self.root_span_id


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return {
            key: "[OMITTED]"
            if _PRIVATE_FIELD.fullmatch(str(key))
            else _redact_value(item)
            if _SENSITIVE_FIELD.fullmatch(str(key)) and isinstance(item, dict)
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
