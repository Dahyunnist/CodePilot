import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from codepilot.config import ModelConfig
from codepilot.tracing import TraceLogger
from evals.live_runner import (
    _finalize_manifest_on_error,
    _finalize_shared_live_manifest,
    _validate_shared_live_manifest,
    _write_run_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "evals/manifests/live_run_manifest_v1.schema.json"


def _write_initial_manifest(tmp_path):
    case_dir = tmp_path / "case"
    (case_dir / "repo").mkdir(parents=True)
    (case_dir / "visible_tests").mkdir()
    (case_dir / "case.json").write_text('{"case_id":"case-1"}\n', encoding="utf-8")
    case = SimpleNamespace(
        case_dir=case_dir,
        case_id="case-1",
        source_commit="a" * 40,
        source_tree_sha="b" * 64,
        archive_sha256="c" * 64,
        docker_image=None,
        docker_python="python",
        baseline_expected_failure=True,
        test_timeout_seconds=30,
        compiled_extensions_sha256=None,
        hidden_test_patch=None,
    )
    output = tmp_path / "out" / "run_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_run_manifest(
        output,
        [case],
        ModelConfig(model="deepseek-test", api_key="must-not-serialize"),
        execution="docker",
        docker_image="runner:mutable-tag",
        max_total_tokens=12_000,
        max_elapsed=120,
        context_budget_chars=9_000,
        max_steps=8,
        context_selector=True,
        run_id="run-group-1",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    return output


def test_live_manifest_schema_and_identity_follow_trace_without_payload(tmp_path):
    output = _write_initial_manifest(tmp_path)
    trace = TraceLogger(output.parent / "run-group-1-case-1.jsonl", "run-group-1-case-1", "run-group-1")
    trace.event("evaluation_started", 0, case_id="case-1")
    trace.event("model_budget_reserved", 1, span_id="span-a", estimated_input_tokens=100)
    trace.event("model_finished", 1, span_id="span-a", input_tokens=90, cached_input_tokens=10, output_tokens=20)
    trace.event("tool_schema_loaded", 0, tool_schema_sha256="d" * 64)
    trace.event("evaluation_finished", 0, status="completed", accepted=True)

    _finalize_shared_live_manifest(
        output,
        status="success",
        rows=[{"accepted": True, "cost_usd_estimate": "0.01"}],
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    shared = report["shared_run_manifest_v1"]
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert set(shared) == set(schema["required"])
    assert shared["status"] == "success"
    assert shared["run_id"] == shared["trace_id"] == "run-group-1"
    assert shared["tool_schema_sha"] == "d" * 64
    assert shared["request_attempt_count"] == shared["response_count"] == 1
    assert shared["failed_request_count"] == 0
    assert shared["completed_case_count"] == 1
    assert shared["failed_case_count"] == 0
    assert shared["cost_usd_estimate"] == 0.01
    assert shared["cost_certainty"] == "estimated_from_reported_usage"
    assert shared["runtime_digest"] is None
    assert "must-not-serialize" not in output.read_text(encoding="utf-8")
    _validate_shared_live_manifest(shared)


def test_failed_request_records_partial_run_and_unknown_cost(tmp_path):
    output = _write_initial_manifest(tmp_path)
    trace = TraceLogger(output.parent / "run-group-1-case-1.jsonl", "run-group-1-case-1", "run-group-1")
    trace.event("evaluation_started", 0, case_id="case-1")
    trace.event("model_budget_reserved", 1, span_id="span-a", estimated_input_tokens=100)
    trace.event("model_failed", 1, span_id="span-a", error="redacted")
    trace.event("evaluation_finished", 0, status="completed", accepted=False)

    _finalize_shared_live_manifest(output, status="failed")
    shared = json.loads(output.read_text(encoding="utf-8"))["shared_run_manifest_v1"]

    assert shared["status"] == "failed"
    assert shared["request_attempt_count"] == 1
    assert shared["response_count"] == 0
    assert shared["failed_request_count"] == 1
    assert shared["completed_case_count"] == 1
    assert shared["failed_case_count"] == 1
    assert shared["cost_usd_estimate"] is None
    assert shared["cost_certainty"] == "unknown"
    _validate_shared_live_manifest(shared)


def test_zero_request_run_records_zero_cost(tmp_path):
    output = _write_initial_manifest(tmp_path)

    _finalize_shared_live_manifest(output, status="success")
    shared = json.loads(output.read_text(encoding="utf-8"))["shared_run_manifest_v1"]

    assert shared["request_attempt_count"] == 0
    assert shared["response_count"] == 0
    assert shared["cost_usd_estimate"] == 0.0
    assert shared["cost_certainty"] == "observed_zero_requests"
    _validate_shared_live_manifest(shared)


def test_unexpected_exception_seals_initialized_manifest(tmp_path):
    output = tmp_path / "out" / "run_manifest.json"
    output.parent.mkdir()

    @_finalize_manifest_on_error
    def fail_after_initial_manifest(cases_root, output_root):
        _write_initial_manifest(tmp_path)
        raise RuntimeError("private error text must not enter manifest")

    try:
        fail_after_initial_manifest(tmp_path / "cases", output.parent)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected test failure")

    shared = json.loads(output.read_text(encoding="utf-8"))["shared_run_manifest_v1"]
    assert shared["status"] == "failed"
    assert shared["ended_at"] is not None
    assert shared["request_attempt_count"] == 0
    assert "private error text" not in output.read_text(encoding="utf-8")
    _validate_shared_live_manifest(shared)
