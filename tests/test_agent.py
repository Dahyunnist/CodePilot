from collections.abc import Sequence

from codepilot.agent import Agent
from codepilot.model import ModelClientError
from codepilot.schemas import (
    ChatMessage,
    ModelReply,
    Task,
    ToolCall,
    ToolResult,
    ToolSpec,
)


class ScriptedModel:
    def __init__(self, replies: list[ModelReply]) -> None:
        self.replies = replies
        self.requests: list[list[ChatMessage]] = []

    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
    ) -> ModelReply:
        self.requests.append(list(messages))
        return self.replies.pop(0)


class StubTools:
    specs: list[ToolSpec] = []

    def execute(self, call: ToolCall) -> ToolResult:
        if call.name == "run_tests":
            return ToolResult(tool_name="run_tests", ok=True, exit_code=0)
        if call.name == "git_diff":
            return ToolResult(tool_name="git_diff", ok=True, stdout="diff --git")
        return ToolResult(tool_name=call.name, ok=True, stdout="found")


def task(tmp_path, max_steps: int = 5) -> Task:
    (tmp_path / ".git").mkdir()
    return Task(
        repo_path=tmp_path,
        instruction="fix the bug",
        test_command=["python", "-m", "pytest"],
        max_steps=max_steps,
    )


def test_loop_returns_observations_to_model(tmp_path) -> None:
    model = ScriptedModel(
        [
            ModelReply(
                tool_calls=[
                    ToolCall(id="call-1", name="search_code", arguments={})
                ]
            ),
            ModelReply(
                tool_calls=[ToolCall(id="call-2", name="run_tests", arguments={})]
            ),
            ModelReply(text="fixed"),
        ]
    )

    result = Agent(model, StubTools()).run(task(tmp_path))

    assert result.status == "success"
    assert result.steps == 3
    assert result.diff == "diff --git"
    assert model.requests[1][-1].role == "tool"
    assert model.requests[1][-1].tool_call_id == "call-1"


def test_loop_stops_at_max_steps(tmp_path) -> None:
    repeated = ModelReply(
        tool_calls=[ToolCall(id="call-1", name="search_code", arguments={})]
    )
    model = ScriptedModel([repeated, repeated])

    result = Agent(model, StubTools()).run(task(tmp_path, max_steps=2))

    assert result.status == "max_steps"
    assert result.steps == 2


def test_finishing_without_tests_is_failure(tmp_path) -> None:
    result = Agent(ScriptedModel([ModelReply(text="done")]), StubTools()).run(
        task(tmp_path)
    )

    assert result.status == "failed"
    assert result.error == "model finished before running tests"


def test_agent_requires_retest_after_successful_patch(tmp_path) -> None:
    model = ScriptedModel(
        [
            ModelReply(
                tool_calls=[ToolCall(id="call-1", name="run_tests", arguments={})]
            ),
            ModelReply(
                tool_calls=[
                    ToolCall(
                        id="call-2",
                        name="apply_patch",
                        arguments={
                            "path": "app.py",
                            "old_text": "old",
                            "new_text": "new",
                        },
                    )
                ]
            ),
            ModelReply(text="done"),
        ]
    )

    result = Agent(model, StubTools()).run(task(tmp_path))

    assert result.status == "failed"
    assert result.error == "model finished before running tests"


def test_model_error_ends_cleanly(tmp_path) -> None:
    class BrokenModel:
        def complete(self, messages, tools=()):
            raise ModelClientError("offline")

    result = Agent(BrokenModel(), StubTools()).run(task(tmp_path))

    assert result.status == "failed"
    assert result.error == "offline"

