"""Data contracts shared by the model, agent, and tool layers."""

import json
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolCall(BaseModel):
    """Validated function request returned by the model."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    arguments: dict[str, Any]

    def to_api_dict(self) -> dict[str, Any]:
        """Convert the normalized call back to Chat Completions format."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }


class ChatMessage(BaseModel):
    """One message in the model conversation."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def validate_role_fields(self) -> "ChatMessage":
        if self.role == "tool":
            if not self.tool_call_id or self.content is None:
                raise ValueError("tool messages require content and tool_call_id")
        elif self.tool_call_id is not None:
            raise ValueError("tool_call_id is only valid for tool messages")

        if self.tool_calls and self.role != "assistant":
            raise ValueError("tool_calls are only valid for assistant messages")
        if self.content is None and not self.tool_calls:
            raise ValueError("message requires content or tool_calls")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize only fields accepted by Chat Completions."""
        role = "system" if self.role == "developer" else self.role
        result: dict[str, Any] = {"role": role, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = [call.to_api_dict() for call in self.tool_calls]
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result


class FunctionSpec(BaseModel):
    """JSON Schema description of one callable function."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    description: str
    parameters: dict[str, Any]
    strict: bool = True


class ToolSpec(BaseModel):
    """Function tool supplied to the model."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["function"] = "function"
    function: FunctionSpec


class ModelReply(BaseModel):
    """Normalized text and tool calls returned by ModelClient."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    def to_assistant_message(self) -> ChatMessage:
        """Preserve the assistant turn before tool results are appended."""
        return ChatMessage(
            role="assistant",
            content=self.text,
            tool_calls=self.tool_calls,
        )


class Task(BaseModel):
    """One repository maintenance request."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex, min_length=1)
    repo_path: Path
    instruction: str = Field(min_length=1)
    test_command: list[str] = Field(min_length=1)
    max_steps: int = Field(default=12, ge=1, le=50)
    max_test_attempts: int = Field(default=3, ge=1, le=20)
    max_elapsed_seconds: float = Field(default=300, gt=0)
    max_total_tokens: int | None = Field(default=None, gt=0)


class ToolResult(BaseModel):
    """Normalized observation returned to the agent."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    ok: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = Field(default=0, ge=0)
    error_type: str | None = None


AgentStatus = Literal[
    "running",
    "success",
    "failed",
    "timeout",
    "budget_exceeded",
    "needs_approval",
    "max_steps",
]


class AgentState(BaseModel):
    """Mutable state carried through the explicit agent loop."""

    model_config = ConfigDict(extra="forbid")

    task: Task
    messages: list[ChatMessage]
    step_count: int = 0
    last_tool_result: ToolResult | None = None
    attempts: dict[str, int] = Field(default_factory=dict)
    workspace_path: Path | None = None
    tokens: int = Field(default=0, ge=0)
    status: AgentStatus = "running"


class RunResult(BaseModel):
    """Final result returned by the agent and CLI."""

    model_config = ConfigDict(extra="forbid")

    status: AgentStatus
    run_id: str
    final_text: str = ""
    diff: str = ""
    test_result: ToolResult | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    steps: int = 0
    tokens: int = Field(default=0, ge=0)
    elapsed_ms: int = Field(default=0, ge=0)
    trace_file: Path | None = None
    report_file: Path | None = None
    workspace_path: Path | None = None
    failure_type: Literal["model", "tool", "test", "policy", "budget"] | None = None
    error: str | None = None
