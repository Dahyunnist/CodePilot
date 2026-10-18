"""Command-line entry point for one repository repair task."""

from __future__ import annotations

import argparse
import shlex
import sys
import uuid
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from codepilot.agent import Agent, ModelLike
from codepilot.config import ModelConfig
from codepilot.model import ModelClient
from codepilot.report import format_run_report, write_markdown_report
from codepilot.schemas import Task, ToolCall
from codepilot.tools.registry import ToolRegistry
from codepilot.tracing import TraceLogger
from codepilot.workspace import WorkspaceError, WorkspaceManager


class AlwaysApprove:
    def approve(self, call: ToolCall) -> bool:
        return True


class ConsoleApproval:
    def approve(self, call: ToolCall) -> bool:
        answer = input(f"Approve host execution for {call.name}? [y/N] ")
        return answer.strip().lower() in {"y", "yes"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codepilot")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run one repository task")
    run_parser.add_argument("--repo", required=True, type=Path)
    run_parser.add_argument("--task", required=True)
    run_parser.add_argument("--test-command", required=True)
    run_parser.add_argument("--max-steps", type=int, default=12)
    run_parser.add_argument("--max-test-attempts", type=int, default=3)
    run_parser.add_argument("--max-elapsed", type=float, default=300)
    run_parser.add_argument("--max-tokens", type=int)
    run_parser.add_argument("--test-timeout", type=float, default=30)
    run_parser.add_argument(
        "--execution", choices=("docker", "host"), default="docker"
    )
    run_parser.add_argument("--docker-image", default="codepilot-runner:0.1")
    run_parser.add_argument("--approve-host-tests", action="store_true")
    run_parser.add_argument("--workspace-root", type=Path, default=Path(".tmp/workspaces"))
    run_parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    model_client: ModelLike | None = None,
) -> int:
    """Parse arguments, run the agent, print its report, and return an exit code."""
    args = build_parser().parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir() or not (repo / ".git").exists():
        print("Error: --repo must be a Git repository", file=sys.stderr)
        return 2

    run_id = uuid.uuid4().hex
    try:
        workspace = WorkspaceManager(args.workspace_root).prepare(repo, run_id)
        task = Task(
            repo_path=workspace.path,
            instruction=args.task,
            test_command=shlex.split(args.test_command, posix=False),
            max_steps=args.max_steps,
            max_test_attempts=args.max_test_attempts,
            max_elapsed_seconds=args.max_elapsed,
            max_total_tokens=args.max_tokens,
        )
        model = model_client or ModelClient(ModelConfig.from_env())
        tools = ToolRegistry(
            workspace.path,
            task.test_command,
            test_timeout_seconds=args.test_timeout,
            execution_mode=args.execution,
            docker_image=args.docker_image,
            host_tests_approved=args.approve_host_tests,
        )
        trace = TraceLogger(args.reports_root / "traces" / f"{run_id}.jsonl", run_id)
        trace.event(
            "workspace_prepared",
            0,
            base_commit=workspace.base_commit,
            execution_mode=args.execution,
        )
    except (ValidationError, ValueError, OSError, WorkspaceError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    approval = None
    if args.execution == "host":
        if args.approve_host_tests:
            approval = AlwaysApprove()
        elif sys.stdin.isatty():
            approval = ConsoleApproval()
    result = Agent(
        model,
        tools,
        approval=approval,
        tracer=trace,
        run_id=run_id,
    ).run(task)
    report_path = args.reports_root / "runs" / f"{run_id}.md"
    result.report_file = write_markdown_report(result, report_path)
    print(format_run_report(result))
    return 0 if result.status == "success" else 1


def entrypoint() -> None:
    raise SystemExit(main())

