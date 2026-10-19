from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from codepilot.schemas import ToolCall
from codepilot.tools import Tool
from codepilot.tools.builtins import BUILTIN_TOOL_TYPES
from codepilot.tools.registry import ToolRegistry


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: str = Field(min_length=1)


class EchoTool(Tool[EchoArguments]):
    name = "echo"
    description = "Return the provided value."
    arguments_model = EchoArguments

    def run(self, arguments: EchoArguments) -> str:
        return arguments.value


class ApprovedEchoTool(EchoTool):
    name = "approved_echo"
    approval_policy = "always"


class ParallelArguments(BaseModel):
    value: str


class ParallelEchoTool(Tool[ParallelArguments]):
    name = "parallel_echo"
    description = "Echo a value and allow concurrent calls."
    arguments_model = ParallelArguments
    parallel_safe = True

    def run(self, arguments: ParallelArguments) -> str:
        return arguments.value


def test_builtin_tool_types_share_tool_base() -> None:
    assert all(issubclass(tool_type, Tool) for tool_type in BUILTIN_TOOL_TYPES)


def test_registry_builds_schema_and_dispatch_from_custom_tool(tmp_path) -> None:
    registry = ToolRegistry(
        tmp_path,
        ["python", "-m", "pytest"],
        tool_types=[EchoTool],
    )

    [tool_spec] = registry.read_tools()
    assert tool_spec.function.name == "echo"
    assert tool_spec.function.description == "Return the provided value."
    assert tool_spec.function.parameters["required"] == ["value"]

    result = registry.execute(
        ToolCall(
            id="echo-call",
            name="echo",
            arguments={"value": "hello"},
        )
    )
    invalid = registry.execute(
        ToolCall(id="invalid-call", name="echo", arguments={"value": ""})
    )

    assert result.ok and result.stdout == "hello"
    assert not invalid.ok and invalid.error_type == "validation"


def test_registry_applies_tool_declared_approval_policy(tmp_path) -> None:
    registry = ToolRegistry(
        tmp_path,
        ["python", "-m", "pytest"],
        tool_types=[ApprovedEchoTool],
    )
    call = ToolCall(
        id="approved-call",
        name="approved_echo",
        arguments={"value": "hello"},
    )

    assert registry.requires_approval(call)
    registry.approve(call)
    assert not registry.requires_approval(call)
    assert registry.execute(call).ok


def test_registry_accepts_tools_after_initialization(tmp_path) -> None:
    registry = ToolRegistry(tmp_path, ["python", "-m", "pytest"])
    registry.register_tool(EchoTool(registry.context))

    tools = {tool.function.name: tool for tool in registry.read_tools()}
    result = registry.execute(
        ToolCall(id="dynamic-echo", name="echo", arguments={"value": "hello"})
    )

    assert "echo" in tools
    assert result.ok and result.stdout == "hello"


def test_registry_registers_validated_string_functions(tmp_path) -> None:
    registry = ToolRegistry(tmp_path, ["python", "-m", "pytest"])
    registry.register_function(
        "uppercase",
        "Convert input text to uppercase.",
        str.upper,
    )

    tools = {tool.function.name: tool for tool in registry.read_tools()}
    result = registry.execute(
        ToolCall(
            id="uppercase-call",
            name="uppercase",
            arguments={"input": "hello"},
        )
    )
    invalid = registry.execute(
        ToolCall(id="uppercase-invalid", name="uppercase", arguments={})
    )

    assert "input" in tools["uppercase"].function.parameters["required"]
    assert result.ok and result.stdout == "HELLO"
    assert not invalid.ok and invalid.error_type == "validation"


def test_function_registration_builds_typed_schema_and_applies_defaults(tmp_path) -> None:
    registry = ToolRegistry(tmp_path, ["python", "-m", "pytest"])

    def format_items(
        label: Annotated[str, Field(min_length=1, description="显示名称")],
        count: Annotated[int, Field(ge=1, le=5)] = 2,
    ) -> str:
        return f"{label}:{count}"

    registry.register_function("format_items", "格式化项目", format_items)
    [spec] = [tool for tool in registry.read_tools() if tool.function.name == "format_items"]

    result = registry.execute(
        ToolCall(
            id="typed-call",
            name="format_items",
            arguments={"label": "任务"},
        )
    )

    assert spec.function.parameters["required"] == ["label"]
    assert spec.function.parameters["properties"]["label"]["description"] == "显示名称"
    assert spec.function.parameters["properties"]["count"]["default"] == 2
    assert result.ok and result.stdout == "任务:2"


def test_function_registration_rejects_bad_types_and_extra_arguments(tmp_path) -> None:
    registry = ToolRegistry(tmp_path, ["python", "-m", "pytest"])

    def multiply(left: int, right: int) -> str:
        return str(left * right)

    registry.register_function("multiply", "相乘", multiply)
    wrong_type = registry.execute(
        ToolCall(
            id="wrong-type",
            name="multiply",
            arguments={"left": "3", "right": 4},
        )
    )
    extra = registry.execute(
        ToolCall(
            id="extra-field",
            name="multiply",
            arguments={"left": 3, "right": 4, "unsafe": True},
        )
    )

    assert not wrong_type.ok and wrong_type.error_type == "validation"
    assert not extra.ok and extra.error_type == "validation"


def test_function_registration_requires_annotations_for_multiple_arguments(tmp_path) -> None:
    registry = ToolRegistry(tmp_path, ["python", "-m", "pytest"])

    def ambiguous(left, right):
        return f"{left}{right}"

    try:
        registry.register_function("ambiguous", "未标注类型", ambiguous)
    except ValueError as exc:
        assert "requires a type annotation" in str(exc)
    else:
        raise AssertionError("untyped multi-argument function was registered")

    assert all(tool.function.name != "ambiguous" for tool in registry.read_tools())


def test_registry_executes_parallel_safe_calls_and_preserves_result_order(tmp_path) -> None:
    registry = ToolRegistry(
        tmp_path,
        ["python", "-m", "pytest"],
        tool_types=[ParallelEchoTool],
    )
    calls = [
        ToolCall(id="first", name="parallel_echo", arguments={"value": "first"}),
        ToolCall(id="second", name="parallel_echo", arguments={"value": "second"}),
    ]

    assert registry.can_execute_many_in_parallel(calls)
    results = registry.execute_many(calls)

    assert [result.stdout for result in results] == ["first", "second"]
    assert all(result.ok for result in results)


def test_registry_keeps_mixed_parallel_and_mutating_calls_serial(tmp_path) -> None:
    registry = ToolRegistry(
        tmp_path,
        ["python", "-m", "pytest"],
        tool_types=[ParallelEchoTool, EchoTool],
    )
    calls = [
        ToolCall(id="parallel", name="parallel_echo", arguments={"value": "read"}),
        ToolCall(id="mutating", name="echo", arguments={"value": "write"}),
    ]

    assert not registry.can_execute_many_in_parallel(calls)
    results = registry.execute_many(calls)

    assert [result.stdout for result in results] == ["read", "write"]
