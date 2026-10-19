"""Tool schemas, validation, dispatch, and normalized observations."""

import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from codepilot.schemas import FunctionSpec, ToolCall, ToolResult, ToolSpec
from codepilot.tools.edit import apply_patch, git_diff
from codepilot.tools.execute import run_tests
from codepilot.tools.repo import list_files, read_file, search_code


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ListFilesArguments(ToolArguments):
    path: str = "."
    max_files: int = Field(default=200, ge=1, le=500)


class SearchCodeArguments(ToolArguments):
    query: str = Field(min_length=1)
    path: str = "."
    max_results: int = Field(default=50, ge=1, le=200)


class ReadFileArguments(ToolArguments):
    path: str
    reason: str = Field(min_length=1, max_length=240, description="\u7528\u7b80\u4f53\u4e2d\u6587\u8bf4\u660e\u8bfb\u53d6\u539f\u56e0\uff0c\u5e76\u5173\u8054\u4efb\u52a1\u6216\u6d4b\u8bd5\u8bc1\u636e\u3002")
    start_line: int = Field(default=1, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class ApplyPatchArguments(ToolArguments):
    path: str
    old_text: str = Field(min_length=1)
    new_text: str


class NoArguments(ToolArguments):
    pass


class ToolRegistry:
    """Expose bounded repository tools and dispatch validated calls."""

    def __init__(
        self,
        repo_root: Path,
        test_command: list[str],
        *,
        test_timeout_seconds: float = 30,
        execution_mode: str = "host",
        docker_image: str = "codepilot-runner:0.1",
        host_tests_approved: bool = False,
    ) -> None:
        self.repo_root = repo_root.resolve(strict=True)
        self.test_command = test_command
        self.test_timeout_seconds = test_timeout_seconds
        self.execution_mode = execution_mode
        self.docker_image = docker_image
        self.host_tests_approved = host_tests_approved
        self._approved_call_ids: set[str] = set()
        self._read_cache: dict[tuple[str, int, int | None], str] = {}
        self._specs = tuple(self._build_specs())

    def read_tools(self) -> tuple[ToolSpec, ...]:
        """Return the current callable tool definitions for the model."""
        return self._specs

    def requires_approval(self, call: ToolCall) -> bool:
        """Require explicit approval before tests execute on the host."""
        return (
            call.name == "run_tests"
            and self.execution_mode == "host"
            and not self.host_tests_approved
            and call.id not in self._approved_call_ids
        )

    def approve(self, call: ToolCall) -> None:
        self._approved_call_ids.add(call.id)

    def execute(self, call: ToolCall) -> ToolResult:
        """Validate one untrusted model call and return a safe observation."""
        started = time.perf_counter()
        try:
            if call.name == "list_files":
                args = ListFilesArguments.model_validate(call.arguments)
                output = list_files(self.repo_root, args.path, args.max_files)
            elif call.name == "search_code":
                args = SearchCodeArguments.model_validate(call.arguments)
                output = search_code(
                    self.repo_root, args.query, args.path, args.max_results
                )
            elif call.name == "read_file":
                args = ReadFileArguments.model_validate(call.arguments)
                key = (args.path.replace("\\", "/"), args.start_line, args.end_line)
                if key in self._read_cache:
                    output = "\u5df2\u7701\u7565\u91cd\u590d\u8bfb\u53d6\uff1b\u8bf7\u4f7f\u7528\u65b0\u7684\u884c\u8303\u56f4\u6216\u6839\u636e\u641c\u7d22\u7ed3\u679c\u8bfb\u53d6\u5176\u4ed6\u4f4d\u7f6e\u3002"
                else:
                    output = read_file(
                        self.repo_root, args.path, args.start_line, args.end_line
                    )
                    self._read_cache[key] = output
            elif call.name == "apply_patch":
                args = ApplyPatchArguments.model_validate(call.arguments)
                output = apply_patch(
                    self.repo_root, args.path, args.old_text, args.new_text
                )
                self._read_cache = {
                    key: value for key, value in self._read_cache.items()
                    if key[0] != args.path.replace("\\", "/")
                }
            elif call.name == "git_diff":
                NoArguments.model_validate(call.arguments)
                output = git_diff(self.repo_root)
            elif call.name == "run_tests":
                NoArguments.model_validate(call.arguments)
                if self.requires_approval(call):
                    raise PermissionError("host test execution requires approval")
                return run_tests(
                    self.repo_root,
                    self.test_command,
                    self.test_timeout_seconds,
                    execution_mode=self.execution_mode,
                    docker_image=self.docker_image,
                )
            else:
                raise ValueError(f"unknown tool: {call.name}")

            return ToolResult(
                tool_name=call.name,
                ok=True,
                stdout=output or "(no output)",
                duration_ms=_elapsed_ms(started),
            )
        except ValidationError as exc:
            return ToolResult(
                tool_name=call.name,
                ok=False,
                stderr=str(exc),
                duration_ms=_elapsed_ms(started),
                error_type="validation",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=call.name,
                ok=False,
                stderr=str(exc),
                duration_ms=_elapsed_ms(started),
                error_type=type(exc).__name__,
            )

    @staticmethod
    def _build_specs() -> list[ToolSpec]:
        return [
            _spec("list_files", "\u5217\u51fa\u4ed3\u5e93\u5185\u7684\u6587\u4ef6\u3002", ListFilesArguments),
            _spec("search_code", "\u5728\u4ed3\u5e93\u6587\u672c\u4e2d\u641c\u7d22\u6307\u5b9a\u5b57\u7b26\u4e32\uff0c\u5148\u6839\u636e\u7ed3\u679c\u9009\u62e9\u5019\u9009\u6587\u4ef6\u3002", SearchCodeArguments),
            _spec("read_file", "\u8bfb\u53d6\u5019\u9009\u6587\u4ef6\u7684\u9650\u5b9a\u884c\u6bb5\uff0c\u7528\u7b80\u4f53\u4e2d\u6587\u8bf4\u660e\u8bfb\u53d6\u7406\u7531\u3002", ReadFileArguments),
            _spec("apply_patch", "\u5728\u6587\u4ef6\u4e2d\u7cbe\u786e\u66ff\u6362\u552f\u4e00\u5339\u914d\u7684\u6587\u672c\u5757\u3002", ApplyPatchArguments),
            _spec("run_tests", "\u8fd0\u884c\u4efb\u52a1\u914d\u7f6e\u7684 pytest \u6d4b\u8bd5\u547d\u4ee4\u3002", NoArguments),
            _spec("git_diff", "\u67e5\u770b\u5f53\u524d Git \u5dee\u5f02\u3002", NoArguments),
        ]


def _spec(name: str, description: str, arguments: type[BaseModel]) -> ToolSpec:
    return ToolSpec(
        function=FunctionSpec(
            name=name,
            description=description,
            parameters=arguments.model_json_schema(),
            strict=False,
        )
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
