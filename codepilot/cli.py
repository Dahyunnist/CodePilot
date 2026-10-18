"""Command-line entry point for one repository repair task."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from codepilot.agent import Agent, ModelLike
from codepilot.config import ModelConfig
from codepilot.model import ModelClient
from codepilot.report import format_run_report
from codepilot.schemas import Task
from codepilot.tools.registry import ToolRegistry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codepilot")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run one repository task")
    run_parser.add_argument("--repo", required=True, type=Path)
    run_parser.add_argument("--task", required=True)
    run_parser.add_argument("--test-command", required=True)
    run_parser.add_argument("--max-steps", type=int, default=12)
    run_parser.add_argument("--test-timeout", type=float, default=30)
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

    try:
        task = Task(
            repo_path=repo,
            instruction=args.task,
            test_command=shlex.split(args.test_command, posix=False),
            max_steps=args.max_steps,
        )
        model = model_client or ModelClient(ModelConfig.from_env())
        tools = ToolRegistry(
            repo,
            task.test_command,
            test_timeout_seconds=args.test_timeout,
        )
    except (ValidationError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    result = Agent(model, tools).run(task)
    print(format_run_report(result))
    return 0 if result.status == "success" else 1


def entrypoint() -> None:
    raise SystemExit(main())

