"""Run selected repair cases through the configured live model."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
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
    context_budget_chars: int,
    max_steps: int,
) -> list[dict[str, object]]:
    """Run clean, isolated copies and independently verify every repair."""
    if execution == "host" and not approve_host_tests:
        raise ValueError("主机测试必须显式使用 --approve-host-tests 批准")

    config = ModelConfig.from_env()
    run_group = uuid.uuid4().hex[:12]
    run_root = work_root.resolve() / run_group
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    cases = [case for case in load_cases(cases_root) if case.case_id in case_ids]
    if not cases:
        raise ValueError("没有找到匹配的评测案例")

    for case in cases:
        case_started = time.perf_counter()
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
        _stage_generated_version_files(base)
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
                "source_url": case.source_url or "",
                "source_release": case.source_release or "",
                "source_exclusions": ";".join(case.source_exclusions),
                "source_commit": case.source_commit or "",
                "source_tree_sha": case.source_tree_sha or "",
                "issue_url": case.issue_url or "",
                "pull_request_url": case.pull_request_url or "",
                "archive_sha256": case.archive_sha256 or "",
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
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "tool_calls": 0,
                "read_file_calls": 0,
                "read_file_output_chars": 0,
                "search_code_calls": 0,
                "run_tests_calls": 0,
                "cost_usd_estimate": "",
                "pricing_period": "unknown",
                "elapsed_ms": baseline.duration_ms,
                "evaluation_elapsed_ms": round((time.perf_counter() - case_started) * 1000),
                "patch_sha256": "",
                "trace_file": "",
            }
            rows.append(row)
            print(f"{case.case_id}：跳过；基线测试无法执行")
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
                max_steps=max_steps,
                max_test_attempts=3,
                max_elapsed_seconds=max_elapsed,
                max_total_tokens=max_total_tokens,
                max_context_chars=context_budget_chars,
            )
        )

        patch_hash = hashlib.sha256(result.diff.encode()).hexdigest() if result.diff else ""
        usage = _trace_usage(trace.path, config.model)
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
            "source_url": case.source_url or "",
            "source_release": case.source_release or "",
            "source_exclusions": ";".join(case.source_exclusions),
            "source_commit": case.source_commit or "",
            "source_tree_sha": case.source_tree_sha or "",
            "issue_url": case.issue_url or "",
            "pull_request_url": case.pull_request_url or "",
            "archive_sha256": case.archive_sha256 or "",
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
            **usage,
            "elapsed_ms": result.elapsed_ms,
            "evaluation_elapsed_ms": round((time.perf_counter() - case_started) * 1000),
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
            f"{case.case_id}：状态={result.status}，验收通过={accepted}，"
            f"Token 数={result.tokens}，补丁 SHA-256={patch_hash}"
        )

    csv_path = output_root / "results.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _write_summary(output_root / "summary.md", rows, config.model)
    print(f"结果文件：{csv_path.resolve()}")
    return rows


def _trace_usage(trace_path: Path, model: str) -> dict[str, object]:
    input_tokens = cached_tokens = output_tokens = 0
    tool_counts: dict[str, int] = {}
    read_file_output_chars = 0
    if trace_path.exists():
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "model_finished":
                request_input = int(event.get("input_tokens", 0))
                input_tokens += request_input
                cached_tokens += min(
                    int(event.get("cached_input_tokens", 0)), request_input
                )
                output_tokens += int(event.get("output_tokens", 0))
            elif event.get("event") == "tool_finished":
                tool = str(event.get("tool", "unknown"))
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
                if tool == "read_file":
                    read_file_output_chars += int(event.get("stdout_chars", 0))
    cached_tokens = min(cached_tokens, input_tokens)
    tool_usage = {
        "tool_calls": sum(tool_counts.values()),
        "read_file_calls": tool_counts.get("read_file", 0),
        "read_file_output_chars": read_file_output_chars,
        "search_code_calls": tool_counts.get("search_code", 0),
        "run_tests_calls": tool_counts.get("run_tests", 0),
    }
    if "deepseek" not in model.casefold():
        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_tokens,
            "output_tokens": output_tokens,
            "cost_usd_estimate": "",
            "pricing_period": "unknown",
            **tool_usage,
        }
    period = _deepseek_pricing_period()
    rates = {
        "off-peak": (0.003, 0.15, 0.60),
        "peak": (0.006, 0.30, 1.20),
    }
    cached_rate, input_rate, output_rate = rates[period]
    cost = (
        cached_tokens * cached_rate
        + (input_tokens - cached_tokens) * input_rate
        + output_tokens * output_rate
    ) / 1_000_000
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "cost_usd_estimate": f"{cost:.6f}",
        "pricing_period": period,
        **tool_usage,
    }


def _deepseek_pricing_period() -> str:
    now = datetime.now(timezone.utc)
    peak = now.weekday() < 5 and (
        1 <= now.hour < 4 or 6 <= now.hour < 10
    )
    return "peak" if peak else "off-peak"


def _write_summary(path: Path, rows: list[dict[str, object]], model: str) -> None:
    accepted = sum(row.get("accepted") is True for row in rows)
    total_tokens = sum(int(row.get("tokens", 0)) for row in rows)
    total_cost = sum(float(row.get("cost_usd_estimate") or 0) for row in rows)
    total_ms = sum(int(row.get("evaluation_elapsed_ms", 0)) for row in rows)
    lines = [
        "# 真实模型评测报告", "",
        f"- 模型：`{model}`", f"- 验收：{accepted}/{len(rows)}",
        f"- 成功：{accepted}，失败：{len(rows) - accepted}",
        f"- 总 Token：{total_tokens:,}", f"- 估算费用：${total_cost:.6f} USD",
        f"- 案例累计耗时：{total_ms / 1000:.1f} 秒",
        "- 费用为按 API usage Token 与 DeepSeek 官方费率估算；实际账单以平台为准。",
        "- 费率时段依据运行时 UTC 时段判断；中国法定节假日可能按非高峰计价。",
        "", "| 案例 | 验收 | 输入 | 缓存输入 | 输出 | 费用 USD | Agent 秒 | 全流程秒 | 步数 | 工具调用 | 读文件 | 读取字符 | 搜索 | 测试 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('case_id')} | {'通过' if row.get('accepted') else '失败'} | "
            f"{row.get('input_tokens', 0)} | {row.get('cached_input_tokens', 0)} | "
            f"{row.get('output_tokens', 0)} | {row.get('cost_usd_estimate', '')} | "
            f"{int(row.get('elapsed_ms', 0)) / 1000:.1f} | "
            f"{int(row.get('evaluation_elapsed_ms', 0)) / 1000:.1f} | "
            f"{row.get('steps', 0)} | {row.get('tool_calls', 0)} | "
            f"{row.get('read_file_calls', 0)} | {row.get('read_file_output_chars', 0)} | "
            f"{row.get('search_code_calls', 0)} | {row.get('run_tests_calls', 0)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def _stage_generated_version_files(repo: Path) -> None:
    """Keep generated src package versions in clean evaluation workspaces."""
    for path in sorted(repo.glob("src/**/_version.py")):
        _git(repo, ["add", "-f", str(path.relative_to(repo))])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.live_runner", description="使用真实模型运行修复评测")
    parser.add_argument("--cases", type=Path, default=Path("evals/cases"))
    parser.add_argument("--case-ids", nargs="+", default=["parse-config", "parse-port", "timeout-config"])
    parser.add_argument("--output-root", type=Path, default=Path("reports/live-model"))
    parser.add_argument("--work-root", type=Path, default=Path(".tmp/live-model"))
    parser.add_argument("--execution", choices=("docker", "host"), default="docker")
    parser.add_argument("--approve-host-tests", action="store_true")
    parser.add_argument("--docker-image", default="codepilot-runner:0.1")
    parser.add_argument("--max-total-tokens", type=int, default=15000)
    parser.add_argument("--context-budget-chars", type=int, default=30_000)
    parser.add_argument("--max-elapsed", type=float, default=180)
    parser.add_argument("--max-steps", type=int, default=10)
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
        context_budget_chars=args.context_budget_chars,
        max_steps=args.max_steps,
    )
    accepted = sum(row["accepted"] is True for row in rows)
    print(f"真实模型评测：{accepted}/{len(rows)} 项通过验收")
    return 0 if accepted == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
