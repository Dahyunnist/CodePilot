"""Run selected repair cases through the configured live model."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
import hashlib
import json
import math
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Sequence
from urllib.parse import urlsplit

from codepilot.agent import Agent
from codepilot.config import ModelConfig
from codepilot.context_selector import ContextSelector
from codepilot.model import ModelClient
from codepilot.security import redact_sensitive_text
from codepilot.schemas import Task, ToolResult
from codepilot.tools.execute import run_tests
from codepilot.tools.registry import ToolRegistry
from codepilot.tracing import TraceLogger
from codepilot.workspace import WorkspaceManager
from evals.runner import load_cases


LIVE_EVAL_HARD_COST_CEILING_USD = 0.06


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
    max_input_tokens_per_request: int = 22_000,
    max_completion_tokens: int = 512,
    max_cost_reserve_usd: float = LIVE_EVAL_HARD_COST_CEILING_USD,
    context_selector: bool = True,
    skill_id: str | None = None,
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
    if "deepseek" not in config.model.casefold():
        raise ValueError("费用硬上限仅按已核实的 DeepSeek 费率开放")
    if max_input_tokens_per_request < 1:
        raise ValueError("每请求输入 Token 硬上限必须为正数")
    if not 1 <= max_completion_tokens <= 512:
        raise ValueError("每请求输出 Token 硬上限必须在 1 到 512 之间")
    if not 0 < max_cost_reserve_usd <= LIVE_EVAL_HARD_COST_CEILING_USD:
        raise ValueError("本轮费用预留必须大于 0 且不超过 $0.06")
    worst_case_per_case = _worst_case_live_cost_usd(
        max_input_tokens_per_request, max_completion_tokens, max_steps
    )
    worst_case_total = worst_case_per_case * len(cases)
    if worst_case_total > max_cost_reserve_usd:
        raise ValueError(
            f"最坏费用预留 ${worst_case_total:.6f} 超过上限 "
            f"${max_cost_reserve_usd:.2f}；未发送模型请求"
        )
    config.max_completion_tokens = min(
        config.max_completion_tokens, max_completion_tokens
    )
    _write_run_manifest(
        output_root / "run_manifest.json",
        cases,
        config,
        execution=execution,
        docker_image=docker_image,
        max_total_tokens=max_total_tokens,
        max_elapsed=max_elapsed,
        context_budget_chars=context_budget_chars,
        max_steps=max_steps,
        max_input_tokens_per_request=max_input_tokens_per_request,
        max_completion_tokens=max_completion_tokens,
        max_cost_reserve_usd=max_cost_reserve_usd,
        worst_case_total_budget_usd=worst_case_total,
        context_selector=context_selector,
        skill_id=skill_id,
    )

    for case in cases:
        case_started = time.perf_counter()
        assert case.case_dir is not None
        case_docker_image = case.docker_image or docker_image
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
            timeout_seconds=case.test_timeout_seconds,
            execution_mode=execution,
            docker_image=case_docker_image,
            docker_python=case.docker_python,
        )
        environment_issue = _benchmark_environment_issue(case, baseline)
        baseline_failed = (
            baseline.error_type == "test_failure"
            and not baseline.ok
            and environment_issue is None
        )
        if environment_issue or (not baseline.ok and not baseline_failed):
            row = {
                "case_id": case.case_id,
                "run_id": "",
                "model": config.model,
                "context_selector_variant": "enabled" if context_selector else "baseline",
                "skill_id": skill_id or "none",
                "source_url": case.source_url or "",
                "source_release": case.source_release or "",
                "source_exclusions": ";".join(case.source_exclusions),
                "source_commit": case.source_commit or "",
                "source_tree_sha": case.source_tree_sha or "",
                "docker_image": case_docker_image,
                "issue_url": case.issue_url or "",
                "pull_request_url": case.pull_request_url or "",
                "archive_sha256": case.archive_sha256 or "",
                "base_url": _safe_endpoint(config.base_url or "https://api.openai.com/v1"),
                "temperature": "provider_default_unspecified",
                "execution": execution,
                "status": "failed",
                "accepted": False,
                "failure_type": "baseline_execution",
                "error": (environment_issue or baseline.stderr or baseline.stdout)[:500],
                "baseline_failed": False,
                "agent_test_ok": False,
                "independent_visible_ok": False,
                "hidden_ok": False,
                "post_budget_verification": "not_run",
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
                "unsafe_actions": 0,
                "cost_usd_estimate": "",
                "pricing_period": "unknown",
                "elapsed_ms": baseline.duration_ms,
                "evaluation_elapsed_ms": round((time.perf_counter() - case_started) * 1000),
                "patch_sha256": "",
                "trace_file": "",
                "verification_workspace": "",
            }
            rows.append(row)
            print(f"{case.case_id}：跳过；基线测试无法执行")
            continue
        if baseline.ok and case.baseline_expected_failure:
            invalid = {
                "case_id": case.case_id,
                "run_id": "",
                "model": config.model,
                "context_selector_variant": "enabled" if context_selector else "baseline",
                "skill_id": skill_id or "none",
                "source_url": case.source_url or "",
                "source_release": case.source_release or "",
                "source_exclusions": ";".join(case.source_exclusions),
                "source_commit": case.source_commit or "",
                "source_tree_sha": case.source_tree_sha or "",
                "docker_image": case_docker_image,
                "issue_url": case.issue_url or "",
                "pull_request_url": case.pull_request_url or "",
                "archive_sha256": case.archive_sha256 or "",
                "base_url": _safe_endpoint(config.base_url or "https://api.openai.com/v1"),
                "temperature": "provider_default_unspecified",
                "execution": execution,
                "status": "failed",
                "accepted": False,
                "failure_type": "baseline_unexpected_pass",
                "error": "原有基线失败型案例的测试意外通过",
                "baseline_failed": False,
                "baseline_expected_failure": True,
                "agent_test_ok": False,
                "independent_visible_ok": False,
                "hidden_ok": False,
                "post_budget_verification": "not_run",
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
                "unsafe_actions": 0,
                "cost_usd_estimate": "",
                "pricing_period": "unknown",
                "elapsed_ms": baseline.duration_ms,
                "evaluation_elapsed_ms": round((time.perf_counter() - case_started) * 1000),
                "patch_sha256": "",
                "trace_file": "",
                "verification_workspace": "",
            }
            rows.append(invalid)
            print(f"{case.case_id}：跳过；失败型任务基线测试意外通过")
            continue
        run_id = f"{run_group}-{case.case_id}-{uuid.uuid4().hex[:8]}"
        workspace = WorkspaceManager(run_root / "workspaces").prepare(base, run_id)
        trace = TraceLogger(output_root / f"{run_id}.jsonl", run_id)
        result = Agent(
            ModelClient(
                config,
                max_input_tokens_per_request=max_input_tokens_per_request,
            ),
            ToolRegistry(
                workspace.path,
                case.test_command,
                test_timeout_seconds=case.test_timeout_seconds,
                execution_mode=execution,
                docker_image=case_docker_image,
                docker_python=case.docker_python,
                host_tests_approved=approve_host_tests,
            ),
            tracer=trace,
            run_id=run_id,
            context_selection_enabled=context_selector,
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
                baseline_test_observation=_baseline_test_observation(baseline),
                skill_id=skill_id,
            )
        )

        patch_hash = hashlib.sha256(result.diff.encode()).hexdigest() if result.diff else ""
        usage = _trace_usage(trace.path, config.model)
        visible = None
        hidden = None
        verification_workspace = None
        if result.diff:
            verification_workspace = _prepare_independent_workspace(
                base,
                workspace.path,
                run_root / "verification" / run_id,
            )
            visible = run_tests(
                verification_workspace,
                case.test_command,
                timeout_seconds=case.test_timeout_seconds,
                execution_mode=execution,
                docker_image=case_docker_image,
                docker_python=case.docker_python,
            )
            if case.hidden_test_patch:
                _apply_hidden_test_patch(case, verification_workspace)
            hidden_command = case.hidden_test_command or [
                "python", "-m", "pytest",
                "/hidden" if execution == "docker" else str(case.case_dir / "hidden_tests"),
                "-q",
            ]
            hidden = run_tests(
                verification_workspace,
                hidden_command,
                timeout_seconds=case.test_timeout_seconds,
                execution_mode=execution,
                docker_image=case_docker_image,
                docker_python=case.docker_python,
                additional_mounts=(
                    ((case.case_dir / "hidden_tests", "/hidden"),)
                    if execution == "docker" and not case.hidden_test_patch
                    else ()
                ),
            )

        accepted = _accepted_for_benchmark(
            baseline_failed=baseline_failed,
            baseline_expected_failure=case.baseline_expected_failure,
            agent_status=result.status,
            agent_test_ok=bool(result.test_result and result.test_result.ok),
            visible_ok=bool(visible and visible.ok),
            hidden_ok=bool(hidden and hidden.ok),
        )
        post_budget_verification = _post_budget_verification_status(
            failure_type=result.failure_type,
            patch_available=bool(result.diff),
            visible_ok=visible.ok if visible is not None else None,
            hidden_ok=hidden.ok if hidden is not None else None,
        )
        row: dict[str, object] = {
            "case_id": case.case_id,
            "run_id": run_id,
            "model": config.model,
            "context_selector_variant": "enabled" if context_selector else "baseline",
            "skill_id": skill_id or "none",
            "source_url": case.source_url or "",
            "source_release": case.source_release or "",
            "source_exclusions": ";".join(case.source_exclusions),
            "source_commit": case.source_commit or "",
            "source_tree_sha": case.source_tree_sha or "",
            "docker_image": case_docker_image,
            "issue_url": case.issue_url or "",
            "pull_request_url": case.pull_request_url or "",
            "archive_sha256": case.archive_sha256 or "",
            "base_url": _safe_endpoint(config.base_url or "https://api.openai.com/v1"),
            "temperature": "provider_default_unspecified",
            "execution": execution,
            "status": result.status,
            "accepted": accepted,
            "failure_type": result.failure_type or "",
            "error": result.error or "",
            "baseline_failed": not baseline.ok,
            "baseline_expected_failure": case.baseline_expected_failure,
            "agent_test_ok": bool(result.test_result and result.test_result.ok),
            "independent_visible_ok": bool(visible and visible.ok),
            "hidden_ok": bool(hidden and hidden.ok),
            "post_budget_verification": post_budget_verification,
            "verification_workspace": (
                str(verification_workspace) if verification_workspace else ""
            ),
            "steps": result.steps,
            "tokens": result.tokens,
            **usage,
            "max_input_tokens_per_request": max_input_tokens_per_request,
            "max_completion_tokens": max_completion_tokens,
            "max_cost_reserve_usd": f"{max_cost_reserve_usd:.6f}",
            "worst_case_total_budget_usd": f"{worst_case_total:.6f}",
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
    unsafe_actions = 0
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
                if event.get("error_type") in {"PathPolicyError", "policy"}:
                    unsafe_actions += 1
    cached_tokens = min(cached_tokens, input_tokens)
    tool_usage = {
        "tool_calls": sum(tool_counts.values()),
        "read_file_calls": tool_counts.get("read_file", 0),
        "read_file_output_chars": read_file_output_chars,
        "search_code_calls": tool_counts.get("search_code", 0),
        "run_tests_calls": tool_counts.get("run_tests", 0),
        "unsafe_actions": unsafe_actions,
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
    ci_low, ci_high = _wilson_interval(accepted, len(rows))
    elapsed = [int(row.get("evaluation_elapsed_ms", 0)) / 1000 for row in rows]
    costs = [float(row.get("cost_usd_estimate") or 0) for row in rows]
    budget_failures = sum(row.get("failure_type") == "budget" for row in rows)
    patches_returned = sum(bool(row.get("patch_sha256")) for row in rows)
    unsafe_actions = sum(int(row.get("unsafe_actions", 0)) for row in rows)
    failures = Counter(str(row.get("failure_type") or "success") for row in rows)
    lines = [
        "# 真实模型评测报告", "",
        f"- 模型：`{model}`", f"- 验收：{accepted}/{len(rows)}",
        f"- 成功：{accepted}，失败：{len(rows) - accepted}",
        f"- Strict accepted / pass@1：{accepted}/{len(rows)}（Wilson 95% CI：{ci_low:.1%}–{ci_high:.1%}）",
        f"- 补丁产出：{patches_returned}/{len(rows)}；预算失败：{budget_failures}；安全策略拒绝调用：{unsafe_actions}",
        f"- 失败分类：{json.dumps(dict(sorted(failures.items())), ensure_ascii=False)}",
        f"- 总 Token：{total_tokens:,}", f"- 估算费用：${total_cost:.6f} USD",
        f"- 案例累计耗时：{total_ms / 1000:.1f} 秒；全流程 p50/p95：{_percentile(elapsed, .50):.1f}/{_percentile(elapsed, .95):.1f} 秒",
        f"- 单题费用 p50/p95：${_percentile(costs, .50):.6f}/${_percentile(costs, .95):.6f} USD",
        "- 费用为按 API usage Token 与 DeepSeek 官方费率估算；实际账单以平台为准。",
        "- 费率时段依据运行时 UTC 时段判断；中国法定节假日可能按非高峰计价。",
        "", "| 案例 | Skill | 验收 | 预算后独立验证 | 输入 | 缓存输入 | 输出 | 费用 USD | Agent 秒 | 全流程秒 | 步数 | 工具调用 | 读文件 | 读取字符 | 搜索 | 测试 |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('case_id')} | {row.get('skill_id', 'none')} | "
            f"{'通过' if row.get('accepted') else '失败'} | "
            f"{row.get('post_budget_verification', 'not_run')} | "
            f"{row.get('input_tokens', 0)} | {row.get('cached_input_tokens', 0)} | "
            f"{row.get('output_tokens', 0)} | {row.get('cost_usd_estimate', '')} | "
            f"{int(row.get('elapsed_ms', 0)) / 1000:.1f} | "
            f"{int(row.get('evaluation_elapsed_ms', 0)) / 1000:.1f} | "
            f"{row.get('steps', 0)} | {row.get('tool_calls', 0)} | "
            f"{row.get('read_file_calls', 0)} | {row.get('read_file_output_chars', 0)} | "
            f"{row.get('search_code_calls', 0)} | {row.get('run_tests_calls', 0)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))]


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def _write_run_manifest(
    path: Path,
    cases: Sequence[object],
    config: ModelConfig,
    *,
    execution: str,
    docker_image: str,
    max_total_tokens: int,
    max_elapsed: float,
    context_budget_chars: int,
    max_steps: int,
    context_selector: bool,
    skill_id: str | None = None,
    max_input_tokens_per_request: int = 22_000,
    max_completion_tokens: int = 512,
    max_cost_reserve_usd: float = LIVE_EVAL_HARD_COST_CEILING_USD,
    worst_case_total_budget_usd: float = 0.0,
) -> None:
    case_records = []
    for case in cases:
        metadata_path = case.case_dir / "case.json"
        raw = metadata_path.read_bytes()
        case_records.append(
            {
                "case_id": case.case_id,
                "metadata_sha256": hashlib.sha256(raw).hexdigest(),
                "source_commit": case.source_commit,
                "source_tree_sha": case.source_tree_sha,
                "archive_sha256": case.archive_sha256,
                "docker_image": getattr(case, "docker_image", None),
                "docker_python": getattr(case, "docker_python", "python"),
                "baseline_expected_failure": getattr(case, "baseline_expected_failure", True),
                "test_timeout_seconds": getattr(case, "test_timeout_seconds", 30),
                "compiled_extensions_sha256": getattr(case, "compiled_extensions_sha256", None),
                "repo_tree_sha256": _directory_sha256(case.case_dir / "repo"),
                "visible_tests_sha256": _directory_sha256(case.case_dir / "visible_tests"),
                "hidden_tests_sha256": (
                    hashlib.sha256((case.case_dir / case.hidden_test_patch).read_bytes()).hexdigest()
                    if case.hidden_test_patch
                    else _directory_sha256(case.case_dir / "hidden_tests")
                ),
            }
        )
    working_diff = subprocess.run(
        ["git", "diff", "HEAD", "--binary"],
        capture_output=True,
        check=True,
        shell=False,
    ).stdout
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        check=True,
        shell=False,
    ).stdout
    git_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    ).stdout.strip()
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "agent_git_sha": git_sha,
        "agent_worktree_diff_sha256": hashlib.sha256(working_diff).hexdigest(),
        "agent_worktree_dirty": bool(status.strip()),
        "model": config.model,
        "api_endpoint": _safe_endpoint(config.base_url or "https://api.openai.com/v1"),
        "temperature": "provider_default_unspecified",
        "execution": execution,
        "docker_image": docker_image,
        "max_total_tokens": max_total_tokens,
        "max_elapsed_seconds": max_elapsed,
        "context_budget_chars": context_budget_chars,
        "max_steps": max_steps,
        "max_input_tokens_per_request": max_input_tokens_per_request,
        "max_completion_tokens": max_completion_tokens,
        "max_cost_reserve_usd": max_cost_reserve_usd,
        "worst_case_total_budget_usd": worst_case_total_budget_usd,
        "context_selector_enabled": context_selector,
        "context_selector_version": (
            ContextSelector.VERSION if context_selector else "baseline"
        ),
        "skill_id": skill_id or "none",
        "cases": case_records,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _directory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        return digest.hexdigest()
    files = sorted(
        item for item in root.rglob("*") if item.is_file() and not item.is_symlink()
    )
    for item in files:
        digest.update(item.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(item.read_bytes()).digest())
    return digest.hexdigest()


def _safe_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return "configured"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}{parsed.path}"


def _worst_case_live_cost_usd(
    max_input_tokens_per_request: int,
    max_completion_tokens: int,
    max_steps: int,
) -> float:
    """Peak-price bound; charge every input token uncached and allow no retries."""
    if min(max_input_tokens_per_request, max_completion_tokens, max_steps) < 1:
        raise ValueError("Token 和步数上限必须为正数")
    return max_steps * (
        max_input_tokens_per_request * 0.30
        + max_completion_tokens * 1.20
    ) / 1_000_000


def _baseline_test_observation(result: ToolResult, limit: int = 1_200) -> str:
    """Share bounded, redacted visible-test baseline evidence with the model."""
    status = "通过" if result.ok else "失败"
    details = [
        f"状态：{status}；退出码：{result.exit_code}；错误类型：{result.error_type or '无'}；耗时：{result.duration_ms} ms。"
    ]
    output = "\n".join(
        section
        for section in (
            f"stdout:\n{result.stdout}" if result.stdout else "",
            f"stderr:\n{result.stderr}" if result.stderr else "",
        )
        if section
    )
    output = redact_sensitive_text(output)
    if not output:
        output = "（无文本输出）"
    if len(output) > limit:
        marker = f"\n…基线输出已截断，原文 {len(output)} 字符…\n"
        remaining = max(0, limit - len(marker))
        head = min(600, remaining // 3)
        tail = remaining - head
        output = f"{output[:head]}{marker}{output[-tail:] if tail else ''}"
    details.append("不可信日志开始\n" + output + "\n不可信日志结束")
    return "\n".join(details)


def _benchmark_environment_issue(case: object, baseline: ToolResult) -> str | None:
    """Reject missing test runtimes and impossible Windows CLI payloads pre-LLM."""
    output = f"{baseline.stdout}\n{baseline.stderr}".casefold()
    if any(
        marker in output
        for marker in (
            "no module named pytest",
            "pytest: command not found",
            "pytest is not recognized",
        )
    ):
        return "基准镜像未提供 pytest；该任务环境不兼容"

    hidden_command = getattr(case, "hidden_test_command", None)
    if hidden_command:
        command_line = subprocess.list2cmdline(hidden_command)
        limit = 30_000 if os.name == "nt" else 100_000
        if len(command_line) > limit:
            return (
                f"隐藏测试命令长度 {len(command_line)} 超过当前平台安全上限 {limit}；"
                "该任务无法可靠运行"
            )
    return None


def _apply_hidden_test_patch(case: object, workspace: Path) -> None:
    """Apply test-only oracle patch in independent verifier, outside Agent workspace."""
    assert case.case_dir is not None and case.hidden_test_patch
    private_root = case.case_dir.resolve(strict=True)
    relative_patch = PurePosixPath(case.hidden_test_patch)
    candidate = private_root.joinpath(*relative_patch.parts)
    if (
        relative_patch.is_absolute()
        or ".." in relative_patch.parts
        or "\\" in case.hidden_test_patch
        or candidate.is_symlink()
    ):
        raise ValueError("hidden test patch path escapes case directory")
    patch_path = candidate.resolve(strict=True)
    if not patch_path.is_relative_to(private_root):
        raise ValueError("hidden test patch path escapes case directory")
    if patch_path.stat().st_size > 10_000_000:
        raise ValueError("hidden test patch exceeds 10 MB limit")
    patch_text = patch_path.read_text(encoding="utf-8")
    touched = []
    for line in patch_text.splitlines():
        if not line.startswith("diff --git a/"):
            continue
        relative = line.split(" b/", 1)[0].removeprefix("diff --git a/")
        parts = PurePosixPath(relative).parts
        if (
            PurePosixPath(relative).is_absolute()
            or ".." in parts
            or not (
                any(part.casefold() in {"test", "tests", "testing"} for part in parts)
                or PurePosixPath(relative).name.casefold().startswith("test_")
                or PurePosixPath(relative).name.casefold().endswith("_test.py")
            )
        ):
            raise ValueError(f"hidden test patch touches non-test path: {relative}")
        touched.append(relative)
    if not touched:
        raise ValueError("hidden test patch has no recognized test files")
    if not (workspace / ".git").exists():
        _git(workspace, ["init", "-q"])
    for flag in ("--check", ""):
        command = ["git", "apply", "--whitespace=nowarn"]
        if flag:
            command.append(flag)
        command.append(str(patch_path))
        subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
            shell=False,
        )


def _git(repo: Path, arguments: list[str], *, timeout_seconds: float = 120) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=True,
        shell=False,
    )


def _prepare_independent_workspace(
    baseline: Path, agent_workspace: Path, destination: Path
) -> Path:
    """Copy trusted baseline, then overlay production changes only."""
    baseline = baseline.resolve(strict=True)
    agent_workspace = agent_workspace.resolve(strict=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite verification copy: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        baseline,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc"),
    )

    changed = subprocess.run(
        ["git", "diff", "HEAD", "--name-only", "-z"],
        cwd=agent_workspace,
        capture_output=True,
        check=True,
        shell=False,
    ).stdout
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=agent_workspace,
        capture_output=True,
        check=True,
        shell=False,
    ).stdout
    candidates = {
        item.decode("utf-8", errors="surrogateescape")
        for item in changed.split(b"\0") + untracked.split(b"\0")
        if item
    }
    for relative in sorted(candidates):
        git_path = PurePosixPath(relative)
        if (
            git_path.is_absolute()
            or ".." in git_path.parts
            or "\\" in relative
            or not _is_verification_source_path(git_path)
        ):
            continue
        source = agent_workspace.joinpath(*git_path.parts)
        target = destination.joinpath(*git_path.parts)
        if source.is_symlink():
            continue
        if not source.exists():
            if target.is_file() and not target.is_symlink():
                target.unlink()
            continue
        if not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def _is_verification_source_path(path: PurePosixPath) -> bool:
    excluded_directories = {
        "test",
        "tests",
        "testing",
        "benchmark_tests",
        "visible_tests",
        "hidden_tests",
    }
    excluded_files = {
        ".pytest.ini",
        "pytest.ini",
        "tox.ini",
        "pyproject.toml",
        "setup.cfg",
        "conftest.py",
        "sitecustomize.py",
        "usercustomize.py",
    }
    folded = tuple(part.casefold() for part in path.parts)
    return not (
        any(part in excluded_directories for part in folded)
        or path.name.casefold() in excluded_files
        or path.name.casefold().startswith("test_")
        or path.name.casefold().endswith("_test.py")
    )


def _post_budget_verification_status(
    *,
    failure_type: str | None,
    patch_available: bool,
    visible_ok: bool | None,
    hidden_ok: bool | None,
) -> str:
    """Report independent verification without changing Agent acceptance."""
    if failure_type != "budget":
        return "not_applicable"
    if not patch_available or visible_ok is None or hidden_ok is None:
        return "not_run"
    if visible_ok and hidden_ok:
        return "passed_after_budget_stop"
    return "failed_after_budget_stop"


def _accepted_for_benchmark(
    *,
    baseline_failed: bool,
    baseline_expected_failure: bool = True,
    agent_status: str,
    agent_test_ok: bool,
    visible_ok: bool,
    hidden_ok: bool,
) -> bool:
    """Accept a complete repair when baseline behavior matches its case type."""
    return (
        (baseline_failed or not baseline_expected_failure)
        and agent_status == "success"
        and agent_test_ok
        and visible_ok
        and hidden_ok
    )


def _stage_generated_version_files(repo: Path) -> None:
    """Keep generated src package versions in clean evaluation workspaces."""
    for path in sorted(repo.glob("src/**/_version.py")):
        _git(repo, ["add", "-f", str(path.relative_to(repo))])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.live_runner", description="使用真实模型运行修复评测")
    parser.add_argument("--cases", type=Path, default=Path("evals/cases"))
    parser.add_argument("--case-ids", nargs="+", default=["parse-config"])
    parser.add_argument("--output-root", type=Path, default=Path("reports/live-model"))
    parser.add_argument("--work-root", type=Path, default=Path(".tmp/live-model"))
    parser.add_argument("--execution", choices=("docker", "host"), default="docker")
    parser.add_argument("--approve-host-tests", action="store_true")
    parser.add_argument("--docker-image", default="codepilot-runner:0.1")
    parser.add_argument("--max-total-tokens", type=int, default=20_000)
    parser.add_argument("--context-budget-chars", type=int, default=8_000)
    parser.add_argument("--max-elapsed", type=float, default=180)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--max-input-tokens-per-request", type=int, default=22_000)
    parser.add_argument("--max-completion-tokens", type=int, default=512)
    parser.add_argument("--max-cost-reserve-usd", type=float, default=0.06)
    parser.add_argument("--skill", choices=("pytest-failure-triage", "api-contract-check"))
    parser.add_argument(
        "--context-selector",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="关闭可作为旧逻辑配对基线",
    )
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
        max_input_tokens_per_request=args.max_input_tokens_per_request,
        max_completion_tokens=args.max_completion_tokens,
        max_cost_reserve_usd=args.max_cost_reserve_usd,
        context_selector=args.context_selector,
        skill_id=args.skill,
    )
    accepted = sum(row["accepted"] is True for row in rows)
    print(f"真实模型评测：{accepted}/{len(rows)} 项通过验收")
    return 0 if accepted == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
