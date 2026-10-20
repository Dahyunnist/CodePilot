import json

import subprocess

from evals.live_runner import _stage_generated_version_files, _trace_usage


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
