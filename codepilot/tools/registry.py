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
    reason: str = Field(min_length=1, max_length=240)
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
        self.specs = self._build_specs()

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
                    output = "Duplicate read omitted; use a new line range or search result."
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
            _spec("list_files", "List files inside the repository.", ListFilesArguments),
            _spec("search_code", "Search repository text for an exact string.", SearchCodeArguments),
            _spec("read_file", "Read a bounded line range from one candidate file. Give a short reason tied to task evidence.", ReadFileArguments),
            _spec("apply_patch", "Replace one exact text block in one file.", ApplyPatchArguments),
            _spec("run_tests", "Run the task's configured pytest command.", NoArguments),
            _spec("git_diff", "Show the current Git diff.", NoArguments),
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
