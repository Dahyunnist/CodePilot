"""Run selected repair cases through the configured live model."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Sequence

from codepilot.agent import Agent
from codepilot.config import ModelConfig
from codepilot.model import ModelClient
from codepilot.schemas import Task
from codepilot.tools.execute import run_tests
from codepilot.tools.registry import ToolRegistry
from codepilot.tracing import TraceLogger
from codepilot.workspace import WorkspaceManager
from evals.runner import load_cases


def run_live_evaluation(
    cases_root: Path,
    output_root: Path,
    work_root: Path,
    case_ids: set[str],
    *,
    execution: str,
    approve_host_tests: bool,
    docker_image: str,
    max_total_tokens: int,
    max_elapsed: float,
) -> list[dict[str, object]]:
    """Run clean, isolated copies and independently verify every repair."""
    if execution == "host" and not approve_host_tests:
        raise ValueError("host execution requires --approve-host-tests")

    config = ModelConfig.from_env()
    run_group = uuid.uuid4().hex[:12]
    run_root = work_root.resolve() / run_group
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    cases = [case for case in load_cases(cases_root) if case.case_id in case_ids]
    if not cases:
        raise ValueError("no matching cases selected")

    for case in cases:
        assert case.case_dir is not None
        base = run_root / "bases" / case.case_id
        base.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            case.case_dir / "repo",
            base,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
        )
        _git(base, ["init", "-q"])
        _git(base, ["config", "user.email", "evals@example.invalid"])
        _git(base, ["config", "user.name", "CodePilot Live Eval"])
        _git(base, ["add", "."])
        _git(base, ["commit", "-q", "-m", f"baseline {case.case_id}"])

        baseline = run_tests(
            base,
            case.test_command,
            execution_mode=execution,
            docker_image=docker_image,
        )
        baseline_failed = baseline.error_type == "test_failure" and not baseline.ok
        if not baseline.ok and not baseline_failed:
            row = {
                "case_id": case.case_id,
                "run_id": "",
                "model": config.model,
                "base_url": config.base_url or "https://api.openai.com/v1",
                "temperature": "provider_default_unspecified",
                "execution": execution,
                "status": "failed",
                "accepted": False,
                "failure_type": "baseline_execution",
                "error": baseline.stderr[:500],
                "baseline_failed": False,
                "agent_test_ok": False,
                "independent_visible_ok": False,
                "hidden_ok": False,
                "steps": 0,
                "tokens": 0,
                "elapsed_ms": baseline.duration_ms,
                "patch_sha256": "",
                "trace_file": "",
            }
            rows.append(row)
            print(f"{case.case_id}: skipped; baseline execution failed")
            continue
        run_id = f"{run_group}-{case.case_id}-{uuid.uuid4().hex[:8]}"
        workspace = WorkspaceManager(run_root / "workspaces").prepare(base, run_id)
        trace = TraceLogger(output_root / f"{run_id}.jsonl", run_id)
        result = Agent(
            ModelClient(config),
            ToolRegistry(
                workspace.path,
                case.test_command,
                execution_mode=execution,
                docker_image=docker_image,
                host_tests_approved=approve_host_tests,
            ),
            tracer=trace,
            run_id=run_id,
        ).run(
            Task(
                task_id=case.case_id,
                repo_path=workspace.path,
                instruction=case.instruction,
                test_command=case.test_command,
                max_steps=10,
                max_test_attempts=3,
                max_elapsed_seconds=max_elapsed,
                max_total_tokens=max_total_tokens,
            )
        )

        patch_hash = hashlib.sha256(result.diff.encode()).hexdigest() if result.diff else ""
        visible = None
        hidden = None
        if result.diff:
            visible = run_tests(
                workspace.path,
                case.test_command,
                execution_mode=execution,
                docker_image=docker_image,
            )
            hidden_command = [
                "python",
                "-m",
                "pytest",
                "/hidden" if execution == "docker" else str(case.case_dir / "hidden_tests"),
                "-q",
            ]
            hidden = run_tests(
                workspace.path,
                hidden_command,
                execution_mode=execution,
                docker_image=docker_image,
                additional_mounts=(
                    ((case.case_dir / "hidden_tests", "/hidden"),)
                    if execution == "docker"
                    else ()
                ),
            )

        accepted = (
            baseline_failed
            and result.status == "success"
            and bool(result.test_result and result.test_result.ok)
            and bool(visible and visible.ok)
            and bool(hidden and hidden.ok)
        )
        row: dict[str, object] = {
            "case_id": case.case_id,
            "run_id": run_id,
            "model": config.model,
            "base_url": config.base_url or "https://api.openai.com/v1",
            "temperature": "provider_default_unspecified",
            "execution": execution,
            "status": result.status,
            "accepted": accepted,
            "failure_type": result.failure_type or "",
            "error": result.error or "",
            "baseline_failed": not baseline.ok,
            "agent_test_ok": bool(result.test_result and result.test_result.ok),
            "independent_visible_ok": bool(visible and visible.ok),
            "hidden_ok": bool(hidden and hidden.ok),
            "steps": result.steps,
            "tokens": result.tokens,
            "elapsed_ms": result.elapsed_ms,
            "patch_sha256": patch_hash,
            "trace_file": str(trace.path),
        }
        test_log = output_root / "test-logs" / f"{case.case_id}.txt"
        test_log.parent.mkdir(parents=True, exist_ok=True)
        test_results = {
            "baseline": baseline,
            "agent": result.test_result,
            "independent_visible": visible,
            "hidden": hidden,
        }
        log_sections = []
        for name, test_result in test_results.items():
            if test_result is None:
                continue
            log_sections.append(
                f"[{name}]\nok={test_result.ok}\n"
                f"exit_code={test_result.exit_code}\n"
                f"error_type={test_result.error_type or ''}\n"
                f"stdout:\n{test_result.stdout}\nstderr:\n{test_result.stderr}\n"
            )
        test_log.write_text("\n".join(log_sections), encoding="utf-8")
        row["test_log"] = str(test_log)
        rows.append(row)
        (output_root / f"{case.case_id}.json").write_text(
            json.dumps(
                {**row, "patch": result.diff, "final_text": result.final_text},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            f"{case.case_id}: status={result.status}, accepted={accepted}, "
            f"tokens={result.tokens}, patch_sha256={patch_hash}"
        )

    csv_path = output_root / "results.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV: {csv_path.resolve()}")
    return rows


def _git(repo: Path, arguments: list[str]) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
        shell=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.live_runner")
    parser.add_argument("--cases", type=Path, default=Path("evals/cases"))
    parser.add_argument("--case-ids", nargs="+", default=["parse-config", "parse-port", "timeout-config"])
    parser.add_argument("--output-root", type=Path, default=Path("reports/live-model"))
    parser.add_argument("--work-root", type=Path, default=Path(".tmp/live-model"))
    parser.add_argument("--execution", choices=("docker", "host"), default="docker")
    parser.add_argument("--approve-host-tests", action="store_true")
    parser.add_argument("--docker-image", default="codepilot-runner:0.1")
    parser.add_argument("--max-total-tokens", type=int, default=15000)
    parser.add_argument("--max-elapsed", type=float, default=180)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = run_live_evaluation(
        args.cases,
        args.output_root,
        args.work_root,
        set(args.case_ids),
        execution=args.execution,
        approve_host_tests=args.approve_host_tests,
        docker_image=args.docker_image,
        max_total_tokens=args.max_total_tokens,
        max_elapsed=args.max_elapsed,
    )
    accepted = sum(row["accepted"] is True for row in rows)
    print(f"Live model evaluation: {accepted}/{len(rows)} accepted")
    return 0 if accepted == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
