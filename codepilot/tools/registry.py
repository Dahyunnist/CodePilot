"""Tool registration, model discovery, policy checks, and dispatch."""

import inspect
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Sequence, get_type_hints

from pydantic import BaseModel, ConfigDict, create_model

from codepilot.schemas import ToolCall, ToolResult, ToolSpec
from codepilot.tools.base import Tool, ToolContext
from codepilot.tools.builtins import BUILTIN_TOOL_TYPES


class _FunctionTool(Tool[BaseModel]):
    def __init__(
        self,
        context: ToolContext,
        name: str,
        description: str,
        function: Callable[..., str | ToolResult],
        arguments_model: type[BaseModel],
        signature: inspect.Signature,
        parameter_fields: dict[str, str],
    ) -> None:
        super().__init__(context)
        self.name = name
        self.description = description
        self._function = function
        self.arguments_model = arguments_model
        self._signature = signature
        self._parameter_fields = parameter_fields

    def run(self, arguments: BaseModel) -> str | ToolResult:
        values = arguments.model_dump()
        positional = [
            values[self._parameter_fields[parameter.name]]
            for parameter in self._signature.parameters.values()
            if parameter.kind is inspect.Parameter.POSITIONAL_ONLY
        ]
        keyword = {
            parameter.name: values[self._parameter_fields[parameter.name]]
            for parameter in self._signature.parameters.values()
            if parameter.kind is not inspect.Parameter.POSITIONAL_ONLY
        }
        return self._function(*positional, **keyword)


class ToolRegistry:
    """Instantiate tool classes once and route calls by their registered names."""

    def __init__(
        self,
        repo_root: Path,
        test_command: list[str],
        *,
        test_timeout_seconds: float = 30,
        execution_mode: str = "host",
        docker_image: str = "codepilot-runner:0.1",
        docker_python: str = "python",
        host_tests_approved: bool = False,
        tool_types: Sequence[type[Tool]] | None = None,
    ) -> None:
        self.context = ToolContext(
            repo_root=repo_root.resolve(strict=True),
            test_command=test_command,
            test_timeout_seconds=test_timeout_seconds,
            execution_mode=execution_mode,
            docker_image=docker_image,
            docker_python=docker_python,
        )
        self.host_tests_approved = host_tests_approved
        self._approved_call_ids: set[str] = set()
        self._tools: dict[str, Tool[Any]] = {}
        types = BUILTIN_TOOL_TYPES if tool_types is None else tool_types
        for tool_type in types:
            self.register_tool(tool_type(self.context))

    def register_tool(self, tool: Tool[Any]) -> None:
        """Register one tool instance and reject accidental name collisions."""
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        tool.to_spec()
        self._tools[tool.name] = tool

    def register_function(
        self,
        name: str,
        description: str,
        function: Callable[..., str | ToolResult],
    ) -> None:
        """Register a typed function and derive its validated JSON schema."""
        try:
            signature = inspect.signature(function)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"cannot inspect tool function: {exc}") from exc
        try:
            annotations = get_type_hints(function, include_extras=True)
        except (TypeError, ValueError, NameError):
            annotations = {}

        fields: dict[str, tuple[Any, Any]] = {}
        parameter_fields: dict[str, str] = {}
        for parameter in signature.parameters.values():
            if parameter.kind not in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
                inspect.Parameter.POSITIONAL_ONLY,
            ):
                raise ValueError(
                    "tool functions must use named parameters without *args or **kwargs"
                )
            annotation = annotations.get(parameter.name, parameter.annotation)
            if annotation is inspect.Parameter.empty:
                if (
                    len(signature.parameters) == 1
                    and parameter.default is inspect.Parameter.empty
                ):
                    annotation = str
                else:
                    raise ValueError(
                        f"tool parameter '{parameter.name}' requires a type annotation"
                    )
            default = (
                ...
                if parameter.default is inspect.Parameter.empty
                else parameter.default
            )
            field_name = (
                "input"
                if len(signature.parameters) == 1
                and parameter.name in {"self", "cls"}
                else parameter.name
            )
            fields[field_name] = (annotation, default)
            parameter_fields[parameter.name] = field_name

        arguments_model = create_model(
            f"{name.title().replace('_', '')}Arguments",
            __config__=ConfigDict(extra="forbid", strict=True),
            **fields,
        )
        self.register_tool(
            _FunctionTool(
                self.context,
                name,
                description,
                function,
                arguments_model,
                signature,
                parameter_fields,
            )
        )

    def read_tools(self) -> tuple[ToolSpec, ...]:
        """Return model schemas generated by the registered tool instances."""
        return tuple(tool.to_spec() for tool in self._tools.values())

    def requires_approval(self, call: ToolCall) -> bool:
        """Require approval for tools marked sensitive by their class."""
        tool = self._tools.get(call.name)
        if tool is None or call.id in self._approved_call_ids:
            return False
        if tool.approval_policy == "always":
            return True
        if tool.approval_policy == "host_tests":
            return (
                self.context.execution_mode == "host"
                and not self.host_tests_approved
            )
        return False

    def approve(self, call: ToolCall) -> None:
        self._approved_call_ids.add(call.id)

    def execute(self, call: ToolCall) -> ToolResult:
        """Dispatch one call to its registered tool after policy checks."""
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                tool_name=call.name,
                ok=False,
                stderr=f"unknown tool: {call.name}",
                error_type="ValueError",
            )
        if self.requires_approval(call):
            return ToolResult(
                tool_name=call.name,
                ok=False,
                stderr="host test execution requires approval",
                error_type="PermissionError",
            )
        return tool.execute(call.arguments)

    def execute_many(self, calls: Sequence[ToolCall]) -> list[ToolResult]:
        """Run independent read-only calls concurrently; keep other batches serial."""
        if not self.can_execute_many_in_parallel(calls):
            return [self.execute(call) for call in calls]
        with ThreadPoolExecutor(max_workers=min(4, len(calls))) as executor:
            return list(executor.map(self.execute, calls))

    def can_execute_many_in_parallel(self, calls: Sequence[ToolCall]) -> bool:
        """Return whether every call is explicitly safe to run concurrently."""
        return len(calls) > 1 and all(
            (tool := self._tools.get(call.name)) is not None
            and tool.parallel_safe
            and not self.requires_approval(call)
            for call in calls
        )
