"""Explicit Reason-Act-Observe loop for CodePilot Lite."""

from __future__ import annotations

import time
import uuid
import json
from typing import Protocol, Sequence

from codepilot.model import ModelClientError
from codepilot.prompts import SYSTEM_PROMPT, task_prompt
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
    ) -> ModelReply: ...


class ToolRegistryLike(Protocol):
    def read_tools(self) -> Sequence[ToolSpec]: ...

    def execute(self, call: ToolCall) -> ToolResult: ...

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

    def run(self, task: Task) -> RunResult:
        """Run until the model finishes, errors, or exhausts max_steps."""
        started = time.perf_counter()
        state = AgentState(
            task=task,
            messages=[
                ChatMessage(role="developer", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=task_prompt(task)),
            ],
            workspace_path=task.repo_path,
        )
        tool_results: list[ToolResult] = []
        last_test: ToolResult | None = None
        self._trace("run_started", 0, task_id=task.task_id)

        while state.step_count < task.max_steps:
            if self._elapsed_seconds(started) >= task.max_elapsed_seconds:
                state.status = "budget_exceeded"
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error="elapsed time budget exceeded",
                    failure_type="budget",
                )
            compacted = _fit_context(state.messages, task.max_context_chars)
            if compacted:
                self._trace(
                    "context_compacted",
                    state.step_count,
                    tool_messages=compacted,
                    context_chars=_context_chars(state.messages),
                    budget_chars=task.max_context_chars,
                )
            if _context_chars(state.messages) > task.max_context_chars:
                state.status = "budget_exceeded"
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error="conversation context budget exceeded",
                    failure_type="budget",
                )
            state.step_count += 1
            available_tools = self.tools.read_tools()
            try:
                reply = self.model.complete(state.messages, available_tools)
            except ModelClientError as exc:
                state.status = "failed"
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error=str(exc),
                    failure_type="model",
                )

            state.tokens += reply.input_tokens + reply.output_tokens
            self._trace(
                "model_finished",
                state.step_count,
                input_tokens=reply.input_tokens,
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
            if self._elapsed_seconds(started) >= task.max_elapsed_seconds:
                state.status = "budget_exceeded"
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error="elapsed time budget exceeded",
                    failure_type="budget",
                )

            state.messages.append(reply.to_assistant_message())
            if not reply.tool_calls:
                if last_test is None:
                    state.status = "failed"
                    error = "model finished before running tests"
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

            for call in reply.tool_calls:
                if call.name == "run_tests" and state.attempts.get(call.name, 0) >= task.max_test_attempts:
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
                if self.tracer:
                    self.tracer.tool_finished(state.step_count, result)
                state.last_tool_result = result
                tool_results.append(result)
                if call.name == "run_tests":
                    last_test = result
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

        state.status = "max_steps"
        return self._finish(
            state,
            tool_results,
            last_test,
            started,
            error=f"maximum step count reached: {task.max_steps}",
            failure_type="budget",
        )

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
            elapsed_ms=max(0, round((time.perf_counter() - started) * 1000)),
            trace_file=getattr(self.tracer, "path", None),
            workspace_path=state.workspace_path,
            failure_type=failure_type,
            error=error,
        )
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


def _context_chars(messages: list[ChatMessage]) -> int:
    return sum(len(json.dumps(message.to_api_dict(), ensure_ascii=False)) for message in messages)


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
        original_chars = len(message.content)
        message.content = json.dumps(
            {"compacted": True, "original_chars": original_chars},
            separators=(",", ":"),
        )
        compacted += 1
    return compacted

