"""Explicit Reason-Act-Observe loop for CodePilot Lite."""

from __future__ import annotations

import time
import uuid
import json
import math
import os
from pathlib import Path
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

    _EXPLORATION_TOOLS = frozenset(
        {
            "read_project_instructions",
            "project_map",
            "search_symbols",
            "find_references",
            "list_files",
            "search_code",
            "read_file",
            "suggest_tests",
        }
    )
    _EXPLORATION_REMINDER_AFTER = 2
    _EXPLORATION_STOP_AFTER = 6

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
            if state.status in {"needs_approval", "needs_user_input"}:
                state.transition("running")
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
        repository_files = _count_repository_files(task.repo_path)
        context_budget = _effective_context_budget(task, repository_files)
        max_observation_chars = _max_tool_observation_chars(context_budget)
        self._max_observation_chars = max_observation_chars
        self._trace(
            "task_context_profile",
            state.step_count,
            repository_files=repository_files,
            configured_context_chars=task.max_context_chars,
            effective_context_chars=context_budget,
            max_tool_observation_chars=max_observation_chars,
            max_total_tokens=task.max_total_tokens,
        )
        if state.model_request_in_flight and state.pending_model_reply is None:
            state.transition("failed")
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
            exploration_streak = state.attempts.get("__exploration_streak", 0)
            if (
                state.pending_model_reply is None
                and exploration_streak >= self._EXPLORATION_STOP_AFTER
            ):
                state.transition("needs_user_input")
                message = (
                    f"连续 {exploration_streak} 轮只读探索，没有代码修改。"
                    "Agent 已暂停；请补充修复方向或指出需要确认的行为。"
                )
                self._trace(
                    "exploration_circuit_breaker",
                    state.step_count,
                    consecutive_read_only_rounds=exploration_streak,
                )
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    final_text=message,
                    error=message,
                    failure_type="policy",
                )
            if self._elapsed_seconds(started) + elapsed_before_ms / 1000 >= task.max_elapsed_seconds:
                state.transition("budget_exceeded")
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error="elapsed time budget exceeded",
                    failure_type="budget",
                )
            resuming_reply = state.pending_model_reply is not None
            compacted = 0 if resuming_reply else _fit_context(state.messages, context_budget)
            if compacted:
                self._trace(
                    "context_compacted",
                    state.step_count,
                    tool_messages=compacted,
                    context_chars=_context_chars(state.messages),
                    budget_chars=context_budget,
                )
            if not resuming_reply and _context_chars(state.messages) > context_budget:
                state.transition("budget_exceeded")
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
                completion_ceiling = 256 if last_test is not None and last_test.ok else 512
                output_limit = min(int(configured_output), completion_ceiling)
                if remaining is not None:
                    needs_test = last_test is None or not last_test.ok
                    future_reserve = _protected_future_tokens(
                        context_budget,
                        available_tools,
                        needs_test=needs_test,
                    )
                    output_limit = min(
                        output_limit,
                        remaining - input_reserve - future_reserve,
                    )
                    minimum_output = min(int(configured_output), 128)
                    if output_limit < minimum_output:
                        state.transition("budget_exceeded")
                        return self._finish(
                            state, tool_results, last_test, started,
                            error=(
                                "token budget cannot reserve current request and "
                                "required test/finalization calls"
                            ),
                            failure_type="budget",
                        )
                else:
                    future_reserve = 0
                state.step_count += 1
                state.model_request_in_flight = True
                self._save_progress(state, tool_results, last_test)
                self._trace(
                    "model_budget_reserved",
                    state.step_count,
                    estimated_input_tokens=input_reserve,
                    max_completion_tokens=output_limit,
                    remaining_tokens=remaining,
                    protected_future_tokens=future_reserve,
                    needs_test=last_test is None or not last_test.ok,
                    effective_context_chars=context_budget,
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
                    state.transition("failed")
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
                if reply.tool_calls and all(
                    call.name in self._EXPLORATION_TOOLS for call in reply.tool_calls
                ):
                    state.attempts["__exploration_streak"] = exploration_streak + 1
                    if (
                        state.attempts["__exploration_streak"]
                        == self._EXPLORATION_REMINDER_AFTER
                    ):
                        self._trace(
                            "exploration_reminder",
                            state.step_count,
                            consecutive_read_only_rounds=state.attempts[
                                "__exploration_streak"
                            ],
                        )
                else:
                    state.attempts["__exploration_streak"] = 0
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
                state.transition("budget_exceeded")
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error="token budget exceeded",
                    failure_type="budget",
                )
            if self._elapsed_seconds(started) + elapsed_before_ms / 1000 >= task.max_elapsed_seconds:
                state.transition("budget_exceeded")
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
                    state.transition("failed")
                    error = "model finished before running the full test suite"
                    failure_type = "test"
                elif not last_test.ok:
                    state.transition("failed")
                    error = "model finished while tests were failing"
                    failure_type = "test"
                else:
                    state.transition("success")
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
                        state.transition("timeout")
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
                        state.transition("budget_exceeded")
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
                            state.transition("needs_approval")
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
                        state.transition("timeout")
                        return self._finish(
                            state,
                            tool_results,
                            last_test,
                            started,
                            error=f"{call.name} timed out",
                            failure_type="tool",
                        )
            if (
                state.attempts.get("__exploration_streak")
                == self._EXPLORATION_REMINDER_AFTER
                and not state.attempts.get("__exploration_reminder_sent")
            ):
                state.messages.append(
                    ChatMessage(
                        role="developer",
                        content=(
                            "探索提醒：你已连续两轮只读探索。请基于现有证据选择最小补丁并运行测试；"
                            "若行为要求仍有歧义，请向用户提出具体问题。不要继续重复读取，也不要猜测或强行修改。"
                        ),
                    )
                )
                state.attempts["__exploration_reminder_sent"] = 1
                self._trace(
                    "exploration_reminder_delivered",
                    state.step_count,
                    consecutive_read_only_rounds=state.attempts[
                        "__exploration_streak"
                    ],
                )
            state.pending_model_reply = None
            state.pending_tool_index = 0
            self._save_progress(state, tool_results, last_test)

        state.transition("max_steps")
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
        observation_limit = getattr(self, "_max_observation_chars", 4_000)
        result = _bounded_tool_result(result, observation_limit)
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


def _count_repository_files(repo_root: Any, limit: int = 2_000) -> int:
    """Count repository files cheaply, stopping once scale is clear."""
    ignored = {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
    }
    count = 0
    for current, directories, files in os.walk(repo_root, followlinks=False):
        directories[:] = [name for name in directories if name.casefold() not in ignored]
        count += sum(1 for name in files if not (Path(current) / name).is_symlink())
        if count >= limit:
            return limit
    return count


def _effective_context_budget(task: Task, repository_files: int | None = None) -> int:
    """Scale per-request history by repository size and total token budget."""
    if repository_files is None:
        repository_files = _count_repository_files(task.repo_path)
    if repository_files < 100:
        scale_limit = 16_000
    elif repository_files < 500:
        scale_limit = 10_000
    else:
        scale_limit = 8_000
    budget = min(task.max_context_chars, scale_limit)
    if task.max_total_tokens is not None:
        token_budget_limit = max(6_000, min(16_000, int(task.max_total_tokens * 0.30)))
        budget = min(budget, token_budget_limit)
    return budget


def _max_tool_observation_chars(context_budget: int) -> int:
    """Limit one tool result to a fraction of the task's context window."""
    return max(512, min(4_000, context_budget // 3))


def _protected_future_tokens(
    context_budget: int,
    tools: Sequence[ToolSpec],
    *,
    needs_test: bool,
) -> int:
    """Hold budget for one test decision and its final response."""
    if not needs_test:
        return 0
    tool_bytes = len(
        json.dumps([tool.model_dump() for tool in tools], ensure_ascii=False).encode("utf-8")
    )
    projected_input = math.ceil(context_budget / 3) + math.ceil(tool_bytes / 3) + 128
    completion_floor = 256
    return 2 * (projected_input + completion_floor)


def _bounded_tool_result(result: ToolResult, limit: int) -> ToolResult:
    """Keep useful edges of large tool output before adding it to history."""
    if len(result.stdout) + len(result.stderr) <= limit:
        return result
    stderr_limit = min(len(result.stderr), max(128, limit // 3)) if result.stderr else 0
    stdout_limit = max(0, limit - stderr_limit)
    if not result.stdout and result.stderr:
        stderr_limit = limit
    return result.model_copy(
        update={
            "stdout": _bounded_tool_text(result.stdout, stdout_limit),
            "stderr": _bounded_tool_text(result.stderr, stderr_limit),
        }
    )


def _bounded_tool_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    marker = f"…已截断，原文共 {len(text)} 字符…"
    remaining = max(0, limit - len(marker))
    head = remaining // 2
    tail = remaining - head
    return f"{text[:head]}{marker}{text[-tail:] if tail else ''}"


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
    while _context_chars(messages) > budget:
        pass_compacted = 0
        for message in messages:
            if _context_chars(messages) <= budget:
                break
            if message.role == "assistant" and message.tool_calls:
                for call in message.tool_calls:
                    if call.arguments:
                        call.arguments = {}
                        pass_compacted += 1
                compacted_content = "Historical tool-call details compacted."
                if message.content and message.content != compacted_content:
                    message.content = compacted_content
                    pass_compacted += 1
                continue
            if message.role != "tool" or message.content is None:
                continue
            message.content, did_compact = _compact_tool_observation(message.content)
            if did_compact:
                pass_compacted += 1
        if not pass_compacted:
            break
        compacted += pass_compacted
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

