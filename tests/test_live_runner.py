import json

import subprocess
import shutil
from types import SimpleNamespace
from pathlib import Path

import pytest

from evals.live_runner import (
    _accepted_for_benchmark,
    _baseline_test_observation,
    _benchmark_environment_issue,
    _apply_hidden_test_patch,
    _directory_sha256,
    _prepare_independent_workspace,
    _post_budget_verification_status,
    _percentile,
    _stage_generated_version_files,
    _trace_usage,
    _worst_case_live_cost_usd,
    _wilson_interval,
    _write_run_manifest,
    _write_summary,
    _safe_endpoint,
    run_live_evaluation,
)
from codepilot.config import ModelConfig
from codepilot.schemas import ToolResult
from evals.compare_live_runs import compare_runs


def test_live_budget_worst_case_fits_six_cent_reserve():
    worst_case = _worst_case_live_cost_usd(
        max_input_tokens_per_request=22_000,
        max_completion_tokens=512,
        max_steps=8,
    )

    assert worst_case == pytest.approx(0.0577152)
    assert worst_case <= 0.06


def test_live_runner_rejects_multi_case_reserve_before_model(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        ModelConfig,
        "from_env",
        classmethod(lambda cls: ModelConfig(model="deepseek-v4-flash", api_key="test")),
    )
    monkeypatch.setattr(
        "evals.live_runner.load_cases",
        lambda _root: [SimpleNamespace(case_id="fresh-a"), SimpleNamespace(case_id="fresh-b")],
    )

    with pytest.raises(ValueError, match="未发送模型请求"):
        run_live_evaluation(
            tmp_path / "cases",
            tmp_path / "out",
            tmp_path / "work",
            {"fresh-a", "fresh-b"},
            execution="docker",
            approve_host_tests=False,
            docker_image="unused",
            max_total_tokens=20_000,
            max_elapsed=180,
            context_budget_chars=8_000,
            max_steps=8,
            max_input_tokens_per_request=22_000,
            max_completion_tokens=512,
            max_cost_reserve_usd=0.06,
        )


def test_trace_usage_sums_model_and_context_read_metrics(tmp_path):
    trace = tmp_path / "trace.jsonl"
    events = [
        {"event": "model_finished", "input_tokens": 100, "cached_input_tokens": 30, "output_tokens": 20},
        {"event": "tool_finished", "tool": "read_file", "stdout_chars": 1200},
        {"event": "tool_finished", "tool": "search_code", "stdout_chars": 80},
        {"event": "tool_finished", "tool": "read_file", "stdout_chars": 500},
        {"event": "model_finished", "input_tokens": 50, "cached_input_tokens": 80, "output_tokens": 10},
    ]
    trace.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")

    usage = _trace_usage(trace, "other-provider-model")

    assert usage == {
        "input_tokens": 150,
        "cached_input_tokens": 80,
        "output_tokens": 30,
        "cost_usd_estimate": "",
        "pricing_period": "unknown",
        "tool_calls": 3,
        "read_file_calls": 2,
        "read_file_output_chars": 1700,
        "search_code_calls": 1,
        "run_tests_calls": 0,
        "unsafe_actions": 0,
    }


def test_trace_usage_counts_denied_policy_actions(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        json.dumps({"event": "tool_finished", "tool": "read_file", "error_type": "PathPolicyError"}),
        encoding="utf-8",
    )

    assert _trace_usage(trace, "other-provider-model")["unsafe_actions"] == 1


def test_baseline_observation_redacts_secrets_and_bounds_output():
    result = ToolResult(
        tool_name="run_tests",
        ok=False,
        exit_code=1,
        error_type="test_failure",
        duration_ms=42,
        stdout='API_KEY="sk-1234567890abcdefghijkl"\n' + "x" * 5000,
    )

    observation = _baseline_test_observation(result, limit=600)

    assert "状态：失败" in observation
    assert "错误类型：test_failure" in observation
    assert "sk-1234567890abcdefghijkl" not in observation
    assert "[REDACTED" in observation
    assert "基线输出已截断" in observation
    assert len(observation) < 800


def test_run_manifest_pins_model_agent_and_case_hashes(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "case.json").write_text('{"case_id":"one"}\n', encoding="utf-8")
    case = type(
        "Case",
        (),
        {
            "case_dir": case_dir,
            "case_id": "one",
            "source_commit": "abc123",
            "source_tree_sha": "tree-sha",
            "archive_sha256": "archive-sha",
            "compiled_extensions_sha256": "extensions-sha",
                "hidden_test_patch": None,
                "docker_image": None,
        },
    )()
    output = tmp_path / "run_manifest.json"
    config = ModelConfig(model="test-model", api_key="test-key")

    _write_run_manifest(
        output,
        [case],
        config,
        execution="docker",
        docker_image="runner:test",
        max_total_tokens=12_000,
        max_elapsed=120,
        context_budget_chars=9_000,
        max_steps=8,
        context_selector=True,
        skill_id="api-contract-check",
    )
    manifest = json.loads(output.read_text(encoding="utf-8"))

    assert len(manifest["agent_git_sha"]) == 40
    assert manifest["model"] == "test-model"
    assert manifest["docker_image"] == "runner:test"
    assert manifest["cases"][0]["source_commit"] == "abc123"
    assert len(manifest["cases"][0]["repo_tree_sha256"]) == 64
    assert len(manifest["cases"][0]["metadata_sha256"]) == 64
    assert len(manifest["cases"][0]["hidden_tests_sha256"]) == 64
    assert manifest["cases"][0]["compiled_extensions_sha256"] == "extensions-sha"
    assert "agent_worktree_diff_sha256" in manifest
    assert manifest["skill_id"] == "api-contract-check"
    assert manifest["context_selector_version"] == "layered-context-v1"


def test_manifest_endpoint_and_test_hashes_do_not_expose_secrets(tmp_path):
    tests = tmp_path / "hidden_tests"
    tests.mkdir()
    (tests / "test_hidden.py").write_text("assert True\n", encoding="utf-8")
    digest = _directory_sha256(tests)

    assert len(digest) == 64
    assert _safe_endpoint("https://user:secret@example.test/v1?token=secret") == (
        "https://example.test/v1"
    )


def test_hidden_test_patch_applies_only_to_independent_workspace(tmp_path):
    repo = tmp_path / "repo"
    tests = repo / "tests"
    tests.mkdir(parents=True)
    source = repo / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    test_file = tests / "test_module.py"
    test_file.write_text("def test_old(): assert True\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], cwd=repo, check=True)
    patch_path = tmp_path / "hidden.patch"
    patch_path.write_text(
        "diff --git a/tests/test_module.py b/tests/test_module.py\n"
        "index 62ca3b0..a4f2a6e 100644\n"
        "--- a/tests/test_module.py\n+++ b/tests/test_module.py\n"
        "@@ -1 +1,2 @@\n def test_old(): assert True\n+def test_hidden(): assert False\n",
        encoding="utf-8",
    )
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    private_patch = case_dir / "hidden.patch"
    shutil.copyfile(patch_path, private_patch)
    case = type("Case", (), {"case_dir": case_dir, "hidden_test_patch": "hidden.patch"})()
    verification = tmp_path / "verification"
    shutil.copytree(repo, verification, ignore=shutil.ignore_patterns(".git"))

    _apply_hidden_test_patch(case, verification)

    assert (verification / ".git").is_dir()
    assert "test_hidden" not in test_file.read_text(encoding="utf-8")
    assert "test_hidden" in (verification / "tests" / "test_module.py").read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_hidden_test_patch_rejects_production_paths(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "hidden.patch").write_text(
        "diff --git a/module.py b/module.py\n--- a/module.py\n+++ b/module.py\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    case = type("Case", (), {"case_dir": case_dir, "hidden_test_patch": "hidden.patch"})()

    try:
        _apply_hidden_test_patch(case, workspace)
    except ValueError as exc:
        assert "non-test path" in str(exc)
    else:
        raise AssertionError("production-file patch must be rejected")


def test_hidden_test_patch_rejects_path_escape(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (tmp_path / "hidden.patch").write_text("", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    case = type(
        "Case", (), {"case_dir": case_dir, "hidden_test_patch": "../hidden.patch"}
    )()

    try:
        _apply_hidden_test_patch(case, workspace)
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("path escape must be rejected")


def test_benchmark_statistics_report_small_sample_uncertainty(tmp_path):
    low, high = _wilson_interval(1, 1)
    summary = tmp_path / "summary.md"
    _write_summary(
        summary,
        [{
            "accepted": True,
            "tokens": 100,
            "cost_usd_estimate": "0.001",
            "evaluation_elapsed_ms": 1_000,
            "elapsed_ms": 500,
            "patch_sha256": "patch",
            "failure_type": "",
            "unsafe_actions": 0,
        }],
        "test-model",
    )

    assert low < 1 and high == 1
    assert _percentile([2, 1], .5) == 1
    report = summary.read_text(encoding="utf-8")
    assert "Wilson 95% CI" in report
    assert "p50/p95" in report
    assert "预算失败" in report


def test_paired_comparison_requires_same_cases_and_reports_exact_test(tmp_path):
    enabled = tmp_path / "enabled"
    baseline = tmp_path / "baseline"
    enabled.mkdir()
    baseline.mkdir()
    shared_manifest = {
        "model": "model-x",
        "api_endpoint": "https://api.example.test/v1",
        "temperature": "provider_default_unspecified",
        "agent_git_sha": "a" * 40,
        "agent_worktree_diff_sha256": "b" * 64,
        "execution": "docker",
        "docker_image": "runner:test",
        "max_total_tokens": 20_000,
        "max_elapsed_seconds": 120,
        "context_budget_chars": 8_000,
        "max_steps": 8,
        "max_input_tokens_per_request": 22_000,
        "max_completion_tokens": 512,
        "max_cost_reserve_usd": 0.06,
        "skill_id": "none",
        "cases": [{"case_id": "a", "metadata_sha256": "same"}],
    }
    for directory, accepted, cost, enabled_selector in (
        (enabled, True, "0.002", True),
        (baseline, False, "0.001", False),
    ):
        (directory / "run_manifest.json").write_text(
            json.dumps({
                **shared_manifest,
                "context_selector_enabled": enabled_selector,
                "context_selector_version": (
                    "layered-context-v1" if enabled_selector else "baseline"
                ),
            }),
            encoding="utf-8",
        )
        with (directory / "results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            import csv
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "case_id", "context_selector_variant", "skill_id", "accepted", "status", "failure_type",
                    "post_budget_verification", "agent_test_ok",
                    "independent_visible_ok", "hidden_ok", "cost_usd_estimate",
                    "evaluation_elapsed_ms",
                ],
            )
            writer.writeheader()
            writer.writerow({
                "case_id": "a",
                "context_selector_variant": "enabled" if accepted else "baseline",
                "skill_id": "none",
                "accepted": accepted,
                "status": "success" if accepted else "budget_exceeded",
                "failure_type": "" if accepted else "budget",
                "post_budget_verification": "not_run" if accepted else "passed_after_budget_stop",
                "agent_test_ok": accepted,
                "independent_visible_ok": True,
                "hidden_ok": True,
                "cost_usd_estimate": cost,
                "evaluation_elapsed_ms": 2_000,
            })

    result = compare_runs(enabled / "results.csv", baseline / "results.csv")

    assert result["paired_cases"] == 1
    assert result["selector_wins"] == 1
    assert result["baseline_wins"] == 0
    assert result["mcnemar_exact_p"] == 1.0
    assert result["median_cost_delta_usd"] == .001
    assert result["failure_attribution_pairs"] == {
        "selector=strict_success;baseline=budget:budget_exceeded:post_budget_passed_after_budget_stop": 1
    }
    detail = result["details"][0]
    assert detail["selector_hidden_tests_passed"] is True
    assert detail["baseline_accepted"] is False


def test_paired_comparison_rejects_mismatched_selector_mode_or_budget(tmp_path):
    enabled = tmp_path / "enabled"
    baseline = tmp_path / "baseline"
    enabled.mkdir()
    baseline.mkdir()
    common = {
        "api_endpoint": "https://api.example.test/v1",
        "temperature": "provider_default_unspecified",
        "agent_git_sha": "a" * 40,
        "agent_worktree_diff_sha256": "b" * 64,
        "execution": "docker",
        "docker_image": "runner:test",
        "max_elapsed_seconds": 120,
        "context_budget_chars": 8_000,
        "max_steps": 8,
        "max_input_tokens_per_request": 22_000,
        "max_completion_tokens": 512,
        "max_cost_reserve_usd": 0.06,
        "skill_id": "none",
        "cases": [{"case_id": "a", "metadata_sha256": "same"}],
    }
    for directory, enabled_selector, token_budget in (
        (enabled, True, 20_000),
        (baseline, False, 12_000),
    ):
        (directory / "run_manifest.json").write_text(
            json.dumps({
                "model": "model-x",
                **common,
                "context_selector_enabled": enabled_selector,
                "context_selector_version": (
                    "layered-context-v1" if enabled_selector else "baseline"
                ),
                "max_total_tokens": token_budget,
            }),
            encoding="utf-8",
        )
        (directory / "results.csv").write_text(
            f"case_id,context_selector_variant,accepted\na,{'enabled' if enabled_selector else 'baseline'},false\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="same max_total_tokens"):
        compare_runs(enabled / "results.csv", baseline / "results.csv")


def test_paired_comparison_rejects_missing_cost_or_latency(tmp_path):
    selector = tmp_path / "selector"
    baseline = tmp_path / "baseline"
    selector.mkdir()
    baseline.mkdir()
    manifest = {
        "model": "model-x",
        "api_endpoint": "https://api.example.test/v1",
        "temperature": "provider_default_unspecified",
        "agent_git_sha": "a" * 40,
        "agent_worktree_diff_sha256": "b" * 64,
        "execution": "docker",
        "docker_image": "runner:test",
        "max_total_tokens": 20_000,
        "max_elapsed_seconds": 120,
        "context_budget_chars": 8_000,
        "max_steps": 8,
        "max_input_tokens_per_request": 22_000,
        "max_completion_tokens": 512,
        "max_cost_reserve_usd": 0.06,
        "skill_id": "none",
        "cases": [{"case_id": "a", "metadata_sha256": "same"}],
    }
    for directory, enabled_selector in ((selector, True), (baseline, False)):
        (directory / "run_manifest.json").write_text(
            json.dumps({
                **manifest,
                "context_selector_enabled": enabled_selector,
                "context_selector_version": (
                    "layered-context-v1" if enabled_selector else "baseline"
                ),
            }),
            encoding="utf-8",
        )
        header = "case_id,context_selector_variant,skill_id,accepted,evaluation_elapsed_ms"
        variant = "enabled" if enabled_selector else "baseline"
        (directory / "results.csv").write_text(
            f"{header}\na,{variant},none,false,100\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="missing metric cost_usd_estimate"):
        compare_runs(selector / "results.csv", baseline / "results.csv")


def test_paired_comparison_supports_skill_enabled_vs_disabled_offline_harness(tmp_path):
    skill_run = tmp_path / "skill-enabled"
    baseline_run = tmp_path / "skill-disabled"
    skill_run.mkdir()
    baseline_run.mkdir()
    shared_manifest = {
        "model": "offline-scripted",
        "api_endpoint": "https://api.example.test/v1",
        "temperature": "provider_default_unspecified",
        "agent_git_sha": "a" * 40,
        "agent_worktree_diff_sha256": "b" * 64,
        "execution": "docker",
        "docker_image": "runner:test",
        "max_total_tokens": 20_000,
        "max_elapsed_seconds": 120,
        "context_budget_chars": 8_000,
        "max_steps": 8,
        "max_input_tokens_per_request": 22_000,
        "max_completion_tokens": 512,
        "max_cost_reserve_usd": 0.06,
        "context_selector_enabled": True,
        "context_selector_version": "layered-context-v1",
        "cases": [{"case_id": "case-1", "metadata_sha256": "same"}],
    }
    for directory, skill_id, accepted, cost, elapsed in (
        (skill_run, "api-contract-check", True, "0.002", "2100"),
        (baseline_run, "none", False, "0.001", "1800"),
    ):
        (directory / "run_manifest.json").write_text(
            json.dumps({**shared_manifest, "skill_id": skill_id}), encoding="utf-8"
        )
        with (directory / "results.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            import csv

            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "case_id", "context_selector_variant", "skill_id", "accepted",
                    "status", "failure_type", "post_budget_verification",
                    "agent_test_ok", "independent_visible_ok", "hidden_ok",
                    "cost_usd_estimate", "evaluation_elapsed_ms",
                ],
            )
            writer.writeheader()
            writer.writerow({
                "case_id": "case-1",
                "context_selector_variant": "enabled",
                "skill_id": skill_id,
                "accepted": accepted,
                "status": "success" if accepted else "budget_exceeded",
                "failure_type": "" if accepted else "budget",
                "post_budget_verification": "not_run",
                "agent_test_ok": accepted,
                "independent_visible_ok": True,
                "hidden_ok": True,
                "cost_usd_estimate": cost,
                "evaluation_elapsed_ms": elapsed,
            })

    result = compare_runs(
        skill_run / "results.csv",
        baseline_run / "results.csv",
        dimension="skill",
    )

    assert result["dimension"] == "skill"
    assert result["selector_variant"] == "skill:api-contract-check"
    assert result["baseline_variant"] == "skill:none"
    assert result["selector_wins"] == 1
    assert result["median_cost_delta_usd"] == pytest.approx(0.001)
    assert result["median_elapsed_delta_ms"] == 300


def test_skill_pair_rejects_context_selector_mismatch(tmp_path):
    skill_run = tmp_path / "skill-enabled"
    baseline_run = tmp_path / "skill-disabled"
    skill_run.mkdir()
    baseline_run.mkdir()
    shared_manifest = {
        "model": "offline-scripted",
        "api_endpoint": "https://api.example.test/v1",
        "temperature": "provider_default_unspecified",
        "agent_git_sha": "a" * 40,
        "agent_worktree_diff_sha256": "b" * 64,
        "execution": "docker",
        "docker_image": "runner:test",
        "max_total_tokens": 20_000,
        "max_elapsed_seconds": 120,
        "context_budget_chars": 8_000,
        "max_steps": 8,
        "max_input_tokens_per_request": 22_000,
        "max_completion_tokens": 512,
        "max_cost_reserve_usd": 0.06,
        "cases": [{"case_id": "case-1", "metadata_sha256": "same"}],
    }
    for directory, skill_id, selector_enabled, selector_version in (
        (skill_run, "api-contract-check", True, "layered-context-v1"),
        (baseline_run, "none", False, "baseline"),
    ):
        (directory / "run_manifest.json").write_text(
            json.dumps({
                **shared_manifest,
                "skill_id": skill_id,
                "context_selector_enabled": selector_enabled,
                "context_selector_version": selector_version,
            }),
            encoding="utf-8",
        )
        (directory / "results.csv").write_text(
            "case_id,context_selector_variant,skill_id\n"
            f"case-1,{'enabled' if selector_enabled else 'baseline'},{skill_id}\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="same ContextSelector setting"):
        compare_runs(
            skill_run / "results.csv",
            baseline_run / "results.csv",
            dimension="skill",
        )


def test_live_runner_stages_generated_version_file_ignored_by_source_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src" / "urllib3").mkdir(parents=True)
    (repo / ".gitignore").write_text("src/urllib3/_version.py\n", encoding="utf-8")
    version_file = repo / "src" / "urllib3" / "_version.py"
    version_file.write_text("__version__ = '2.5.0'\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)

    _stage_generated_version_files(repo)

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "src/urllib3/_version.py"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0


def test_budget_stopped_patch_verifies_from_clean_copy_and_frozen_tests(tmp_path):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "src").mkdir()
    (baseline / "src" / "repair.py").write_text("VALUE = 1\n", encoding="utf-8")
    (baseline / "pytest.ini").write_text("[pytest]\naddopts = -q\n", encoding="utf-8")
    (baseline / "tests").mkdir()
    (baseline / "tests" / "test_repair.py").write_text(
        "def test_frozen(): assert True\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=baseline, check=True)
    subprocess.run(["git", "config", "user.email", "evals@example.invalid"], cwd=baseline, check=True)
    subprocess.run(["git", "config", "user.name", "CodePilot Test"], cwd=baseline, check=True)
    subprocess.run(["git", "add", "."], cwd=baseline, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=baseline, check=True)

    agent_workspace = tmp_path / "agent-workspace"
    shutil.copytree(baseline, agent_workspace)
    (agent_workspace / "src" / "repair.py").write_text("VALUE = 2\n", encoding="utf-8")
    (agent_workspace / "pytest.ini").write_text("[pytest]\naddopts = --ignore=tests\n", encoding="utf-8")
    (agent_workspace / "tests" / "test_repair.py").write_text(
        "def test_frozen(): assert False\n", encoding="utf-8"
    )

    verification = _prepare_independent_workspace(
        baseline, agent_workspace, tmp_path / "verification"
    )

    assert (verification / "src" / "repair.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert (verification / "pytest.ini").read_text(encoding="utf-8") == "[pytest]\naddopts = -q\n"
    assert (verification / "tests" / "test_repair.py").read_text(encoding="utf-8") == (
        "def test_frozen(): assert True\n"
    )
    assert verification != agent_workspace


def test_post_budget_verification_never_changes_agent_acceptance():
    assert _post_budget_verification_status(
        failure_type="budget",
        patch_available=True,
        visible_ok=True,
        hidden_ok=True,
    ) == "passed_after_budget_stop"
    assert not _accepted_for_benchmark(
        baseline_failed=True,
        agent_status="budget_exceeded",
        agent_test_ok=False,
        visible_ok=True,
        hidden_ok=True,
    )


def test_benchmark_accepts_clean_baseline_for_hidden_only_public_task():
    assert _accepted_for_benchmark(
        baseline_failed=False,
        baseline_expected_failure=False,
        agent_status="success",
        agent_test_ok=True,
        visible_ok=True,
        hidden_ok=True,
    )
    assert not _accepted_for_benchmark(
        baseline_failed=False,
        baseline_expected_failure=True,
        agent_status="success",
        agent_test_ok=True,
        visible_ok=True,
        hidden_ok=True,
    )


def test_live_runner_rejects_images_without_pytest_before_model_call():
    case = type("Case", (), {"hidden_test_command": ["python", "-m", "pytest"]})()
    result = ToolResult(
        tool_name="run_tests",
        ok=False,
        error_type="test_failure",
        stdout="/opt/python: No module named pytest",
    )

    assert "未提供 pytest" in _benchmark_environment_issue(case, result)


def test_live_runner_rejects_hidden_commands_that_exceed_windows_limit():
    case = type(
        "Case",
        (),
        {"hidden_test_command": ["python", "-m", "pytest", "node" * 30_100]},
    )()
    result = ToolResult(tool_name="run_tests", ok=False, error_type="test_failure")

    issue = _benchmark_environment_issue(case, result)

    assert issue is not None
    assert "超过当前平台安全上限" in issue
