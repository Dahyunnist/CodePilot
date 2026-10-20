"""Common contract and execution context for repository tools."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, TypeVar, cast

from pydantic import BaseModel, ValidationError

from codepilot.schemas import FunctionSpec, ToolResult, ToolSpec
from codepilot.security import redact_sensitive_text


ArgumentsT = TypeVar("ArgumentsT", bound=BaseModel)
ApprovalPolicy = Literal["never", "always", "host_tests"]


@dataclass
class ToolContext:
    """Dependencies shared by tools in one repository run."""

    repo_root: Path
    test_command: list[str]
    test_timeout_seconds: float = 30
    execution_mode: str = "host"
    docker_image: str = "codepilot-runner:0.1"
    read_cache: dict[tuple[str, int, int | None], tuple[str, str]] = field(
        default_factory=dict
    )
    last_test_result: ToolResult | None = None
    repository_index: Any | None = None
    repository_index_revision: str | None = None


class Tool(ABC, Generic[ArgumentsT]):
    """Base class that owns one tool's schema, validation, and execution."""

    name: ClassVar[str]
    description: ClassVar[str]
    arguments_model: ClassVar[type[ArgumentsT]]
    approval_policy: ClassVar[ApprovalPolicy] = "never"
    parallel_safe: ClassVar[bool] = False

    def __init__(self, context: ToolContext) -> None:
        self.context = context

    def to_spec(self) -> ToolSpec:
        """Build the function schema sent to the model from this tool class."""
        return ToolSpec(
            function=FunctionSpec(
                name=self.name,
                description=self.description,
                parameters=self.arguments_model.model_json_schema(),
                strict=False,
            )
        )

    def execute(self, raw_arguments: dict[str, Any]) -> ToolResult:
        """Validate model arguments, execute the tool, and normalize its result."""
        started = time.perf_counter()
        try:
            arguments = cast(
                ArgumentsT, self.arguments_model.model_validate(raw_arguments)
            )
            result = self.run(arguments)
            if isinstance(result, ToolResult):
                return result.model_copy(
                    update={
                        "tool_name": self.name,
                        "stdout": redact_sensitive_text(result.stdout),
                        "stderr": redact_sensitive_text(result.stderr),
                    }
                )
            return ToolResult(
                tool_name=self.name,
                ok=True,
                stdout=redact_sensitive_text(result or "(no output)"),
                duration_ms=_elapsed_ms(started),
            )
        except ValidationError as exc:
            return ToolResult(
                tool_name=self.name,
                ok=False,
                stderr=redact_sensitive_text(str(exc)),
                duration_ms=_elapsed_ms(started),
                error_type="validation",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                ok=False,
                stderr=str(exc),
                duration_ms=_elapsed_ms(started),
                error_type=type(exc).__name__,
            )

    @abstractmethod
    def run(self, arguments: ArgumentsT) -> str | ToolResult:
        """Execute validated arguments and return text or a normalized result."""


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
