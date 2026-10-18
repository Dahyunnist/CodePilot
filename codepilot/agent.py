"""Explicit Reason-Act-Observe loop for CodePilot Lite."""

from __future__ import annotations

import time
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
    specs: list[ToolSpec]

    def execute(self, call: ToolCall) -> ToolResult: ...


class Agent:
    """Ask the model, execute validated tools, and feed observations back."""

    def __init__(self, model: ModelLike, tools: ToolRegistryLike) -> None:
        self.model = model
        self.tools = tools

    def run(self, task: Task) -> RunResult:
        """Run until the model finishes, errors, or exhausts max_steps."""
        started = time.perf_counter()
        state = AgentState(
            task=task,
            messages=[
                ChatMessage(role="developer", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=task_prompt(task)),
            ],
        )
        tool_results: list[ToolResult] = []
        last_test: ToolResult | None = None

        while state.step_count < task.max_steps:
            state.step_count += 1
            try:
                reply = self.model.complete(state.messages, self.tools.specs)
            except ModelClientError as exc:
                state.status = "failed"
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    error=str(exc),
                )

            state.messages.append(reply.to_assistant_message())
            if not reply.tool_calls:
                if last_test is None:
                    state.status = "failed"
                    error = "model finished before running tests"
                elif not last_test.ok:
                    state.status = "failed"
                    error = "model finished while tests were failing"
                else:
                    state.status = "success"
                    error = None
                return self._finish(
                    state,
                    tool_results,
                    last_test,
                    started,
                    final_text=reply.text or "",
                    error=error,
                )

            for call in reply.tool_calls:
                state.attempts[call.name] = state.attempts.get(call.name, 0) + 1
                result = self.tools.execute(call)
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
                        content=result.model_dump_json(),
                    )
                )

        state.status = "max_steps"
        return self._finish(
            state,
            tool_results,
            last_test,
            started,
            error=f"maximum step count reached: {task.max_steps}",
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
    ) -> RunResult:
        diff_result = self.tools.execute(
            ToolCall(id="internal-git-diff", name="git_diff", arguments={})
        )
        diff = diff_result.stdout if diff_result.ok else ""
        if diff == "(no output)":
            diff = ""
        return RunResult(
            status=state.status,
            final_text=final_text,
            diff=diff,
            test_result=last_test,
            tool_results=tool_results,
            steps=state.step_count,
            elapsed_ms=max(0, round((time.perf_counter() - started) * 1000)),
            error=error,
        )

