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
