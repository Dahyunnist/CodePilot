"""MCP stdio server for the repository's allowlisted, policy-checked tools."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import uuid
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from codepilot.schemas import ToolCall
from codepilot.tools.registry import ToolRegistry


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


class ToolOutcome(BaseModel):
    tool_name: str
    ok: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error_type: str | None = None
    duration_ms: int = 0


def create_server(
    repo_root: Path,
    test_command: list[str],
    *,
    execution_mode: str = "docker",
    docker_image: str = "codepilot-runner:0.1",
    test_timeout_seconds: float = 30,
    host_tests_approved: bool = False,
    allow_test_run: bool = True,
) -> MCPServer:
    """Expose only read and test tools; all calls pass through ToolRegistry."""
    registry = ToolRegistry(
        repo_root,
        test_command,
        test_timeout_seconds=test_timeout_seconds,
        execution_mode=execution_mode,
        docker_image=docker_image,
        host_tests_approved=host_tests_approved,
    )
    server = MCPServer(
        "CodePilot Repository Tools",
        instructions="只提供受限仓库读取、差异查看和测试工具。补丁写回必须由宿主 Agent 审批。",
    )
    internal_names = {
        "repo_search": "search_code",
        "repo_read": "read_file",
        "repo_diff": "git_diff",
        "test_status": "test_status",
        "run_tests": "run_tests",
    }

    def call_tool(name: str, arguments: dict[str, Any]) -> ToolOutcome:
        call = ToolCall(id=f"mcp-{uuid.uuid4().hex}", name=internal_names[name], arguments=arguments)
        result = registry.execute(call)
        outcome = ToolOutcome(
            tool_name=name,
            ok=result.ok,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            error_type=result.error_type,
            duration_ms=result.duration_ms,
        )
        if not result.ok:
            raise ToolError(outcome.model_dump_json())
        return outcome

    @server.tool(name="repo_search", description="在目标仓库中搜索代码；路径由 ToolRegistry 限制。", annotations=READ_ONLY)
    def repo_search(query: str, path: str = ".", max_results: int = 50) -> ToolOutcome:
        return call_tool("repo_search", {"query": query, "path": path, "max_results": max_results})

    @server.tool(name="repo_read", description="读取目标仓库文件的指定行段；敏感文件和仓库外路径会被拒绝。", annotations=READ_ONLY)
    def repo_read(path: str, reason: str, start_line: int = 1, end_line: int | None = None) -> ToolOutcome:
        return call_tool("repo_read", {"path": path, "reason": reason, "start_line": start_line, "end_line": end_line})

    @server.tool(name="repo_diff", description="读取当前工作副本中的 Git 差异。", annotations=READ_ONLY)
    def repo_diff() -> ToolOutcome:
        return call_tool("repo_diff", {})

    @server.tool(name="test_status", description="读取本次 MCP 服务会话最近一次测试状态。", annotations=READ_ONLY)
    def test_status() -> ToolOutcome:
        return call_tool("test_status", {})

    if allow_test_run and (execution_mode == "docker" or host_tests_approved):
        @server.tool(
            name="run_tests",
            description="运行仓库配置的 pytest 命令；Docker 模式使用受限测试容器。",
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False),
        )
        def test_run() -> ToolOutcome:
            return call_tool("run_tests", {})

    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codepilot-mcp", description="CodePilot 仓库 MCP 服务")
    parser.add_argument("--repo", required=True, type=Path, help="仓库或隔离工作副本路径")
    command_group = parser.add_mutually_exclusive_group(required=True)
    command_group.add_argument("--test-command", help="pytest 命令")
    command_group.add_argument("--test-command-json", help="pytest 参数数组的 JSON")
    parser.add_argument("--execution", choices=("docker", "host"), default="docker")
    parser.add_argument("--docker-image", default="codepilot-runner:0.1")
    parser.add_argument("--test-timeout", type=float, default=30)
    parser.add_argument("--approve-host-tests", action="store_true", help="批准该 MCP 服务在主机运行 pytest")
    parser.add_argument("--no-test-run", action="store_true", help="不向 MCP 客户端暴露测试执行工具")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir():
        print("错误：--repo 必须指向已有目录", file=sys.stderr)
        return 2
    if args.execution == "host" and not args.approve_host_tests and not args.no_test_run:
        print("错误：主机模式暴露 test_run 前必须使用 --approve-host-tests", file=sys.stderr)
        return 2
    if args.test_command_json:
        try:
            test_command = json.loads(args.test_command_json)
        except json.JSONDecodeError:
            print("错误：--test-command-json 不是有效 JSON", file=sys.stderr)
            return 2
        if not isinstance(test_command, list) or not all(
            isinstance(part, str) for part in test_command
        ):
            print("错误：--test-command-json 必须是字符串数组", file=sys.stderr)
            return 2
    else:
        test_command = shlex.split(args.test_command, posix=False)
    server = create_server(
        repo,
        test_command,
        execution_mode=args.execution,
        docker_image=args.docker_image,
        test_timeout_seconds=args.test_timeout,
        host_tests_approved=args.approve_host_tests,
        allow_test_run=not args.no_test_run,
    )
    server.run("stdio")
    return 0


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
