import pytest
from pydantic import ValidationError

from codepilot.schemas import ToolCall
from codepilot.tools.demo import DEMO_TOOL_SPECS, DemoToolError, execute_demo_tool


def test_tool_specs_expose_json_schemas() -> None:
    names = [tool.function.name for tool in DEMO_TOOL_SPECS]

    assert names == ["calculator", "echo"]
    assert DEMO_TOOL_SPECS[0].function.parameters["type"] == "object"


def test_executes_calculator_call() -> None:
    call = ToolCall(
        id="call-1",
        name="calculator",
        arguments={"operation": "multiply", "left": 4.0, "right": 2.5},
    )

    assert execute_demo_tool(call) == 10.0


def test_executes_echo_call() -> None:
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hello"})

    assert execute_demo_tool(call) == "hello"


def test_rejects_invalid_arguments() -> None:
    call = ToolCall(id="call-1", name="echo", arguments={"unexpected": "value"})

    with pytest.raises(ValidationError):
        execute_demo_tool(call)


def test_rejects_division_by_zero() -> None:
    call = ToolCall(
        id="call-1",
        name="calculator",
        arguments={"operation": "divide", "left": 4.0, "right": 0.0},
    )

    with pytest.raises(DemoToolError, match="division by zero"):
        execute_demo_tool(call)

