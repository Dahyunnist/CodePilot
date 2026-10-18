"""Safe demo tools for validating structured tool calls."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from codepilot.schemas import FunctionSpec, ToolCall, ToolSpec


class CalculatorArguments(BaseModel):
    """Validated calculator input."""

    model_config = ConfigDict(extra="forbid", strict=True)

    operation: Literal["add", "subtract", "multiply", "divide"]
    left: float
    right: float


class EchoArguments(BaseModel):
    """Validated echo input."""

    model_config = ConfigDict(extra="forbid", strict=True)

    text: str


DEMO_TOOL_SPECS = [
    ToolSpec(
        function=FunctionSpec(
            name="calculator",
            description="Perform basic arithmetic on two numbers.",
            parameters=CalculatorArguments.model_json_schema(),
        )
    ),
    ToolSpec(
        function=FunctionSpec(
            name="echo",
            description="Return the provided text unchanged.",
            parameters=EchoArguments.model_json_schema(),
        )
    ),
]


class DemoToolError(RuntimeError):
    """Raised when a demo tool cannot execute safely."""


def execute_demo_tool(call: ToolCall) -> float | str:
    """Validate and execute one calculator or echo tool call."""
    if call.name == "echo":
        return EchoArguments.model_validate(call.arguments).text

    if call.name != "calculator":
        raise DemoToolError(f"unknown demo tool: {call.name}")

    args = CalculatorArguments.model_validate(call.arguments)
    if args.operation == "add":
        return args.left + args.right
    if args.operation == "subtract":
        return args.left - args.right
    if args.operation == "multiply":
        return args.left * args.right
    if args.right == 0:
        raise DemoToolError("division by zero")
    return args.left / args.right

