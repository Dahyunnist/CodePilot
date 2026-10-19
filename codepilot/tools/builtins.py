"""Built-in repository tools and their argument schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from codepilot.schemas import ToolResult
from codepilot.tools.base import Tool, ToolContext
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
    reason: str = Field(
        min_length=1,
        max_length=240,
        description="用简体中文说明读取原因，并关联任务或测试证据。",
    )
    start_line: int = Field(default=1, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class ApplyPatchArguments(ToolArguments):
    path: str
    old_text: str = Field(min_length=1)
    new_text: str


class NoArguments(ToolArguments):
    pass


class ListFilesTool(Tool[ListFilesArguments]):
    name = "list_files"
    description = "列出仓库内的文件。"
    arguments_model = ListFilesArguments

    def run(self, arguments: ListFilesArguments) -> str:
        return list_files(
            self.context.repo_root, arguments.path, arguments.max_files
        )


class SearchCodeTool(Tool[SearchCodeArguments]):
    name = "search_code"
    description = "在仓库文本中搜索指定字符串，先根据结果选择候选文件。"
    arguments_model = SearchCodeArguments

    def run(self, arguments: SearchCodeArguments) -> str:
        return search_code(
            self.context.repo_root,
            arguments.query,
            arguments.path,
            arguments.max_results,
        )


class ReadFileTool(Tool[ReadFileArguments]):
    name = "read_file"
    description = "读取候选文件的限定行段，用简体中文说明读取理由。"
    arguments_model = ReadFileArguments

    def run(self, arguments: ReadFileArguments) -> str:
        key = (
            arguments.path.replace("\\", "/"),
            arguments.start_line,
            arguments.end_line,
        )
        if key in self.context.read_cache:
            return "已省略重复读取；请使用新的行范围或根据搜索结果读取其他位置。"
        output = read_file(
            self.context.repo_root,
            arguments.path,
            arguments.start_line,
            arguments.end_line,
        )
        self.context.read_cache[key] = output
        return output


class ApplyPatchTool(Tool[ApplyPatchArguments]):
    name = "apply_patch"
    description = "在文件中精确替换唯一匹配的文本块。"
    arguments_model = ApplyPatchArguments

    def run(self, arguments: ApplyPatchArguments) -> str:
        output = apply_patch(
            self.context.repo_root,
            arguments.path,
            arguments.old_text,
            arguments.new_text,
        )
        normalized_path = arguments.path.replace("\\", "/")
        self.context.read_cache = {
            key: value
            for key, value in self.context.read_cache.items()
            if key[0] != normalized_path
        }
        return output


class RunTestsTool(Tool[NoArguments]):
    name = "run_tests"
    description = "运行任务配置的 pytest 测试命令。"
    arguments_model = NoArguments
    approval_policy = "host_tests"

    def run(self, arguments: NoArguments) -> ToolResult:
        return run_tests(
            self.context.repo_root,
            self.context.test_command,
            self.context.test_timeout_seconds,
            execution_mode=self.context.execution_mode,
            docker_image=self.context.docker_image,
        )


class GitDiffTool(Tool[NoArguments]):
    name = "git_diff"
    description = "查看当前 Git 差异。"
    arguments_model = NoArguments

    def run(self, arguments: NoArguments) -> str:
        return git_diff(self.context.repo_root)


BUILTIN_TOOL_TYPES: tuple[type[Tool], ...] = (
    ListFilesTool,
    SearchCodeTool,
    ReadFileTool,
    ApplyPatchTool,
    RunTestsTool,
    GitDiffTool,
)
