import json

import subprocess
import shutil
from pathlib import Path

from evals.live_runner import (
    _accepted_for_benchmark,
    _prepare_independent_workspace,
    _post_budget_verification_status,
    _stage_generated_version_files,
    _trace_usage,
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
    }


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
