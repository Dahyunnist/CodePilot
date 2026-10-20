"""Explicit Reason-Act-Observe loop for CodePilot Lite."""

from __future__ import annotations

import time
import uuid
import json
import math
from typing import Any, Callable, Protocol, Sequence

from codepilot.model import ModelClientError
from codepilot.prompts import SYSTEM_PROMPT, task_prompt
from codepilot.security import redact_sensitive_text
from codepilot.schemas import (
    AgentState,
    ChatMessage,
    ModelReply,
    RunResult,
    Task,
    ToolCall,
    ToolResult,
    ToolSpec,
)


class ModelLike(Protocol):
    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        *,
        max_completion_tokens: int | None = None,
    ) -> ModelReply: ...


class ToolRegistryLike(Protocol):
    def read_tools(self) -> Sequence[ToolSpec]: ...

    def execute(self, call: ToolCall) -> ToolResult: ...

    def execute_many(self, calls: Sequence[ToolCall]) -> list[ToolResult]: ...

    def can_execute_many_in_parallel(self, calls: Sequence[ToolCall]) -> bool: ...

    def requires_approval(self, call: ToolCall) -> bool: ...

    def approve(self, call: ToolCall) -> None: ...


class ApprovalProvider(Protocol):
    def approve(self, call: ToolCall) -> bool: ...


class TraceLike(Protocol):
    path: object

    def event(self, event: str, step: int, **fields: object) -> None: ...

    def tool_started(self, step: int, call: ToolCall) -> None: ...

    def tool_finished(self, step: int, result: ToolResult) -> None: ...


class Agent:
    """Ask the model, execute validated tools, and feed observations back."""

    def __init__(
        self,
        model: ModelLike,
        tools: ToolRegistryLike,
        *,
        approval: ApprovalProvider | None = None,
        tracer: TraceLike | None = None,
        run_id: str | None = None,
    ) -> None:
        self.model = model
        self.tools = tools
        self.approval = approval
        self.tracer = tracer
        self.run_id = run_id or uuid.uuid4().hex

    def run(
        self,
        task: Task,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        resume_data: dict[str, Any] | None = None,
    ) -> RunResult:
        """Run until the model finishes, errors, or exhausts max_steps."""
        started = time.perf_counter()
        elapsed_before_ms = int((resume_data or {}).get("elapsed_ms", 0))
        self._progress_callback = progress_callback
        self._progress_started = started
        self._progress_elapsed_before_ms = elapsed_before_ms
        if resume_data and resume_data.get("done"):
            return RunResult.model_validate(resume_data["result"])
        if resume_data and "agent_state" in resume_data:
            state = AgentState.model_validate(resume_data["agent_state"])
            if state.task.task_id != task.task_id:
                raise ValueError("持久化任务与恢复任务 ID 不匹配")
            tool_results = [
                ToolResult.model_validate(item)
                for item in resume_data.get("tool_results", [])
            ]
            raw_last_test = resume_data.get("last_test")
            last_test = ToolResult.model_validate(raw_last_test) if raw_last_test else None
        else:
            state = AgentState(
                task=task,
                messages=[
                    ChatMessage(role="developer", content=SYSTEM_PROMPT),
                    ChatMessage(role="user", content=task_prompt(task)),
                ],
                workspace_path=task.repo_path,
            )
            tool_results = []
            last_test = None
        if state.model_request_in_flight and state.pending_model_reply is None:
            state.status = "failed"
            return self._finish(
                state,
                tool_results,
                last_test,
                started,
                error=(
                    "上次模型请求中断，响应结果未知；为避免重复计费，未自动重发"
                ),
                failure_type="model",
            )
        self._save_progress(state, tool_results, last_test)
        self._trace("run_started", 0, task_id=task.task_id)

        while state.step_count < task.max_steps or state.pending_model_reply is not None:
            if self._elapsed_seconds(started) + elapsed_before_ms / 1000 >= task.max_elapsed_seconds:
                state.status = "budget_exceeded"
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error="elapsed time budget exceeded",
                    failure_type="budget",
                )
            resuming_reply = state.pending_model_reply is not None
            compacted = 0 if resuming_reply else _fit_context(state.messages, task.max_context_chars)
            if compacted:
                self._trace(
                    "context_compacted",
                    state.step_count,
                    tool_messages=compacted,
                    context_chars=_context_chars(state.messages),
                    budget_chars=task.max_context_chars,
                )
            if not resuming_reply and _context_chars(state.messages) > task.max_context_chars:
                state.status = "budget_exceeded"
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error="conversation context budget exceeded",
                    failure_type="budget",
                )
            available_tools = self.tools.read_tools()
            if resuming_reply:
                reply = state.pending_model_reply
            else:
                remaining = (
                    task.max_total_tokens - state.tokens
                    if task.max_total_tokens is not None
                    else None
                )
                input_reserve = _estimate_request_tokens(state.messages, available_tools)
                configured_output = getattr(
                    getattr(self.model, "config", None), "max_completion_tokens", 1024
                )
                output_limit = int(configured_output)
                if remaining is not None:
                    output_limit = min(output_limit, remaining - input_reserve)
                    if output_limit < 1:
                        state.status = "budget_exceeded"
                        return self._finish(
                            state, tool_results, last_test, started,
                            error=(
                                "token budget cannot reserve estimated input and "
                                "one output token"
                            ),
                            failure_type="budget",
                        )
                state.step_count += 1
                state.model_request_in_flight = True
                self._save_progress(state, tool_results, last_test)
                self._trace(
                    "model_budget_reserved",
                    state.step_count,
                    estimated_input_tokens=input_reserve,
                    max_completion_tokens=output_limit,
                    remaining_tokens=remaining,
                )
                try:
                    reply = self.model.complete(
                        state.messages,
                        available_tools,
                        max_completion_tokens=output_limit,
                    )
                except ModelClientError as exc:
                    state.model_request_in_flight = False
                    self._save_progress(state, tool_results, last_test)
                    state.status = "failed"
                    return self._finish(
                        state,
                        tool_results,
                        last_test,
                        started,
                        error=str(exc),
                        failure_type="model",
                    )

                state.model_request_in_flight = False
                state.tokens += reply.input_tokens + reply.output_tokens
                state.pending_model_reply = reply
                state.pending_tool_index = 0
                state.messages.append(reply.to_assistant_message())
                self._save_progress(state, tool_results, last_test)

            self._trace(
                "model_finished",
                state.step_count,
                input_tokens=reply.input_tokens,
                cached_input_tokens=reply.cached_input_tokens,
                output_tokens=reply.output_tokens,
                tool_calls=len(reply.tool_calls),
            )
            if task.max_total_tokens is not None and state.tokens > task.max_total_tokens:
                state.status = "budget_exceeded"
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error="token budget exceeded",
                    failure_type="budget",
                )
            if self._elapsed_seconds(started) + elapsed_before_ms / 1000 >= task.max_elapsed_seconds:
                state.status = "budget_exceeded"
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error="elapsed time budget exceeded",
                    failure_type="budget",
                )

            if not reply.tool_calls:
                state.pending_model_reply = None
                if last_test is None:
                    state.status = "failed"
                    error = "model finished before running the full test suite"
                    failure_type = "test"
                elif not last_test.ok:
                    state.status = "failed"
                    error = "model finished while tests were failing"
                    failure_type = "test"
                else:
                    state.status = "success"
                    error = None
                    failure_type = None
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    final_text=reply.text or "",
                    error=error,
                    failure_type=failure_type,
                )

            can_parallel = getattr(
                self.tools, "can_execute_many_in_parallel", lambda unused: False
            )
            execute_many = getattr(self.tools, "execute_many", None)
            if (
                not resuming_reply
                and execute_many is not None
                and can_parallel(reply.tool_calls)
            ):
                for call in reply.tool_calls:
                    state.attempts[call.name] = state.attempts.get(call.name, 0) + 1
                    if self.tracer:
                        self.tracer.tool_started(state.step_count, call)
                results = execute_many(reply.tool_calls)
                for call, result in zip(reply.tool_calls, results, strict=True):
                    last_test = self._record_tool_result(
                        state, tool_results, last_test, call, result, available_tools
                    )
                    if result.error_type == "timeout":
                        state.status = "timeout"
                        return self._finish(
                            state,
                            tool_results,
                            last_test,
                            started,
                            error=f"{call.name} timed out",
                            failure_type="tool",
                        )
                state.pending_tool_index = len(reply.tool_calls)
                self._save_progress(state, tool_results, last_test)
            else:
                for call_index in range(state.pending_tool_index, len(reply.tool_calls)):
                    call = reply.tool_calls[call_index]
                    test_attempts = sum(
                        state.attempts.get(name, 0)
                        for name in ("run_tests", "run_selected_tests")
                    )
                    if call.name in {"run_tests", "run_selected_tests"} and test_attempts >= task.max_test_attempts:
                        state.status = "budget_exceeded"
                        return self._finish(
                            state,
                            tool_results,
                            last_test,
                            started,
                            error="maximum test attempts reached",
                            failure_type="budget",
                        )

                    requires_approval = getattr(
                        self.tools, "requires_approval", lambda unused: False
                    )(call)
                    if requires_approval:
                        if self.approval is None or not self.approval.approve(call):
                            state.status = "needs_approval"
                            return self._finish(
                                state,
                                tool_results,
                                last_test,
                                started,
                                error=f"approval required for {call.name}",
                                failure_type="policy",
                            )
                        getattr(self.tools, "approve", lambda unused: None)(call)

                    state.attempts[call.name] = state.attempts.get(call.name, 0) + 1
                    if self.tracer:
                        self.tracer.tool_started(state.step_count, call)
                    result = self.tools.execute(call)
                    last_test = self._record_tool_result(
                        state, tool_results, last_test, call, result, available_tools
                    )
                    state.pending_tool_index = call_index + 1
                    self._save_progress(state, tool_results, last_test)
                    if result.error_type == "timeout":
                        state.status = "timeout"
                        return self._finish(
                            state,
                            tool_results,
                            last_test,
                            started,
                            error=f"{call.name} timed out",
                            failure_type="tool",
                        )
            state.pending_model_reply = None
            state.pending_tool_index = 0
            self._save_progress(state, tool_results, last_test)

        state.status = "max_steps"
        return self._finish(
            state,
            tool_results,
            last_test,
            started,
            error=f"maximum step count reached: {task.max_steps}",
            failure_type="budget",
        )

    def _record_tool_result(
        self,
        state: AgentState,
        tool_results: list[ToolResult],
        last_test: ToolResult | None,
        call: ToolCall,
        result: ToolResult,
        available_tools: Sequence[ToolSpec],
    ) -> ToolResult | None:
        result = result.model_copy(
            update={
                "stdout": redact_sensitive_text(result.stdout),
                "stderr": redact_sensitive_text(result.stderr),
            }
        )
        if self.tracer:
            self.tracer.tool_finished(state.step_count, result)
        state.last_tool_result = result
        tool_results.append(result)
        if call.name == "run_tests":
            last_test = result
        elif call.name == "run_selected_tests":
            # Targeted tests guide iteration but cannot satisfy final acceptance.
            last_test = None
        elif call.name == "apply_patch" and result.ok:
            # A passing test result becomes stale after source changes.
            last_test = None
        state.messages.append(
            ChatMessage(
                role="tool",
                tool_call_id=call.id,
                content=_tool_observation(call.name, result, available_tools),
            )
        )
        return last_test

    def _finish(
        self,
        state: AgentState,
        tool_results: list[ToolResult],
        last_test: ToolResult | None,
        started: float,
        *,
        final_text: str = "",
        error: str | None = None,
        failure_type: str | None = None,
    ) -> RunResult:
        diff_result = self.tools.execute(
            ToolCall(id="internal-git-diff", name="git_diff", arguments={})
        )
        diff = diff_result.stdout if diff_result.ok else ""
        if diff == "(no output)":
            diff = ""
        result = RunResult(
            status=state.status,
            run_id=self.run_id,
            final_text=final_text,
            diff=diff,
            test_result=last_test,
            tool_results=tool_results,
            steps=state.step_count,
            tokens=state.tokens,
            elapsed_ms=getattr(self, "_progress_elapsed_before_ms", 0)
            + max(0, round((time.perf_counter() - started) * 1000)),
            trace_file=getattr(self.tracer, "path", None),
            workspace_path=state.workspace_path,
            failure_type=failure_type,
            error=error,
        )
        self._save_progress(state, tool_results, last_test, result=result)
        self._trace(
            "run_finished",
            state.step_count,
            status=result.status,
            elapsed_ms=result.elapsed_ms,
            tokens=result.tokens,
            failure_type=result.failure_type,
        )
        return result

    def _trace(self, event: str, step: int, **fields: object) -> None:
        if self.tracer:
            self.tracer.event(event, step, **fields)

    @staticmethod
    def _elapsed_seconds(started: float) -> float:
        return time.perf_counter() - started

    def _save_progress(
        self,
        state: AgentState,
        tool_results: list[ToolResult],
        last_test: ToolResult | None,
        *,
        result: RunResult | None = None,
    ) -> None:
        callback = getattr(self, "_progress_callback", None)
        if callback is None:
            return
        started = getattr(self, "_progress_started", time.perf_counter())
        elapsed_before_ms = getattr(self, "_progress_elapsed_before_ms", 0)
        snapshot: dict[str, Any] = {
            "agent_state": state.model_dump(mode="json"),
            "tool_results": [item.model_dump(mode="json") for item in tool_results],
            "last_test": last_test.model_dump(mode="json") if last_test else None,
            "elapsed_ms": elapsed_before_ms + max(0, round((time.perf_counter() - started) * 1000)),
            "done": result is not None,
        }
        if result is not None:
            snapshot["result"] = result.model_dump(mode="json")
        callback(snapshot)


def _context_chars(messages: list[ChatMessage]) -> int:
    return sum(len(json.dumps(message.to_api_dict(), ensure_ascii=False)) for message in messages)


def _estimate_request_tokens(
    messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
) -> int:
    """Reserve a byte-based upper bound before sending a request.

    UTF-8 byte volume is converted to a conservative token estimate; fixed
    framing allowance covers message and tool boundaries. Provider usage remains
    the final guard because tokenization varies by provider and model.
    """
    message_bytes = sum(
        len(json.dumps(message.to_api_dict(), ensure_ascii=False).encode("utf-8"))
        for message in messages
    )
    tool_bytes = len(
        json.dumps([tool.model_dump() for tool in tools], ensure_ascii=False).encode("utf-8")
    )
    payload_bytes = message_bytes + tool_bytes
    return math.ceil(payload_bytes / 3) + 16 * len(messages) + 64


def _tool_observation(
    tool_name: str, result: ToolResult, tools: Sequence[ToolSpec]
) -> str:
    description = next(
        (
            spec.function.description
            for spec in tools
            if spec.function.name == tool_name
        ),
        tool_name,
    )
    status = "成功" if result.ok else "失败"
    lines = [
        f"工具执行结果：{description}（{tool_name}）",
        f"执行状态：{status}",
    ]
    if result.exit_code is not None:
        lines.append(f"退出码：{result.exit_code}")
    if result.error_type:
        lines.append(f"错误类型：{result.error_type}")
    if result.stdout:
        output = "（无输出）" if result.stdout == "(no output)" else result.stdout
        lines.extend(["标准输出：", output])
    if result.stderr:
        lines.extend(["错误输出：", result.stderr])
    return "\n".join(lines)


def _fit_context(messages: list[ChatMessage], budget: int) -> int:
    compacted = 0
    for message in messages:
        if _context_chars(messages) <= budget:
            break
        if message.role == "assistant" and message.tool_calls:
            for call in message.tool_calls:
                if call.arguments:
                    call.arguments = {}
                    compacted += 1
            if message.content:
                message.content = "Historical tool-call details compacted."
                compacted += 1
            continue
        if message.role != "tool" or message.content is None:
            continue
        message.content, did_compact = _compact_tool_observation(message.content)
        if not did_compact:
            continue
        compacted += 1
    return compacted


def _compact_tool_observation(content: str) -> tuple[str, bool]:
    """Keep a bounded evidence excerpt when old tool output leaves context."""
    try:
        previous = json.loads(content)
    except json.JSONDecodeError:
        previous = None

    if isinstance(previous, dict) and previous.get("compacted") is True:
        original_chars = int(previous.get("original_chars", len(content)))
        summary = str(previous.get("summary", ""))
        excerpt_limit = 96
        if len(summary) <= excerpt_limit:
            return content, False
    else:
        original_chars = len(content)
        summary = content
        excerpt_limit = 320

    excerpt = _bounded_excerpt(summary, excerpt_limit)
    compacted = json.dumps(
        {
            "compacted": True,
            "original_chars": original_chars,
            "summary": excerpt,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if compacted == content:
        return content, False
    return compacted, True


def _bounded_excerpt(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head
    omitted = len(text) - limit
    return f"{text[:head]}…省略 {omitted} 字符…{text[-tail:]}"

