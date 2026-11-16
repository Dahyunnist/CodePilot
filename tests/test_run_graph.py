from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from codepilot import run_graph
from codepilot.cli import _print_pending_approval
from codepilot.schemas import RunResult, Task, ToolCall, ToolResult
from codepilot.tracing import TraceLogger
from codepilot.workspace import Workspace


def test_pending_approval_output_shows_expiration(tmp_path, capsys):
    state = {
        "__interrupt__": [
            SimpleNamespace(
                value={
                    "base_commit": "a" * 40,
                    "patch_sha256": "b" * 64,
                    "expires_at": "2030-01-01T00:30:00+00:00",
                    "source": "repository",
                }
            )
        ]
    }

    _print_pending_approval(state, "run-approval", tmp_path / "state.sqlite")

    assert "审批有效期至：2030-01-01T00:30:00+00:00" in capsys.readouterr().out


def test_expired_durable_approval_never_writes_back_and_keeps_trace_link(tmp_path, monkeypatch):
    run_id = "approval-expiry-offline"
    state_db = tmp_path / "reports" / "state.sqlite"
    trace_path = tmp_path / "reports" / "trace.jsonl"
    patch_text = "diff --git a/app.py b/app.py\n+"
    apply_calls = []

    request_trace = TraceLogger(trace_path, run_id, trace_id="trace-expiry")

    class SuccessfulAgent:
        def run(self, task, *, progress_callback=None, resume_data=None):
            request_trace.event("run_started", 0)
            for step, call in enumerate(
                (
                    ToolCall(
                        id="read-call",
                        name="read_file",
                        arguments={"path": "app.py", "reason": "Inspect code."},
                    ),
                    ToolCall(
                        id="patch-call",
                        name="apply_patch",
                        arguments={
                            "path": "app.py",
                            "old_text": "old",
                            "new_text": "SENSITIVE_PATCH_TEXT",
                        },
                    ),
                    ToolCall(id="test-call", name="run_tests", arguments={}),
                ),
                1,
            ):
                model_span = f"model-{step}"
                request_trace.event("model_budget_reserved", step, span_id=model_span)
                request_trace.event("model_finished", step, span_id=model_span)
                request_trace.tool_started(step, call)
                result = ToolResult(
                    tool_name=call.name,
                    ok=True,
                    stdout="SENSITIVE_TOOL_OUTPUT" if call.name == "read_file" else "",
                )
                if call.name == "apply_patch":
                    request_trace.patch_started(call)
                    request_trace.patch_finished(call, result)
                request_trace.tool_finished(step, result, call.id)
            request_trace.event("run_finished", 3, status="success")
            return RunResult(
                status="success",
                run_id=run_id,
                diff=patch_text,
                test_result=ToolResult(tool_name="run_tests", ok=True, exit_code=0),
            )

    class FakeWorkspaceManager:
        def apply_changes(self, workspace):
            apply_calls.append(workspace)
            return True

    def agent_factory(task, current_run_id, runtime):
        return SuccessfulAgent()

    monkeypatch.setattr(run_graph, "_git_patch", lambda workspace, base: patch_text.encode())
    task = Task(
        task_id=run_id,
        repo_path=tmp_path,
        instruction="Repair the test case.",
        test_command=["python", "-m", "pytest"],
    )
    workspace = Workspace(
        source=tmp_path / "source",
        path=tmp_path / "workspace",
        base_commit="a" * 40,
    )
    pending = run_graph.start_durable_run(
        database=state_db,
        manager=FakeWorkspaceManager(),
        agent_factory=agent_factory,
        task=task,
        workspace=workspace,
        run_id=run_id,
        apply_to_repo=True,
        runtime={"execution_mode": "host", "host_tests_approved": True},
        tracer=request_trace,
    )
    assert "__interrupt__" in pending
    window = run_graph._load_approval_window(state_db, run_id)
    assert window is not None

    expires_at = run_graph.datetime.fromisoformat(window["expires_at"])
    monkeypatch.setattr(
        run_graph,
        "_utc_now",
        lambda: expires_at + timedelta(seconds=1),
    )
    decision_trace = TraceLogger(trace_path, run_id, trace_id="trace-expiry")
    completed = run_graph.resume_durable_run(
        database=state_db,
        manager=FakeWorkspaceManager(),
        agent_factory=agent_factory,
        run_id=run_id,
        approved=True,
        tracer=decision_trace,
    )

    assert completed["delivery"] == "approval_expired"
    assert completed["result"]["status"] == "failed"
    assert "已过期" in completed["result"]["error"]
    assert apply_calls == []
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    requested = [event for event in events if event["event"] == "writeback_approval_requested"]
    decided = [event for event in events if event["event"] == "writeback_approval_decided"]
    assert len(requested) == len(decided) == 1
    assert requested[0]["span_id"] == decided[0]["span_id"] == window["approval_span_id"]
    assert requested[0]["parent_span_id"] == decided[0]["parent_span_id"]
    assert {event["trace_id"] for event in events} == {"trace-expiry"}
    read_tool = next(event for event in events if event["event"] == "tool_started" and event["tool"] == "read_file")
    patch_tool = next(event for event in events if event["event"] == "tool_started" and event["tool"] == "apply_patch")
    patch_span = next(event for event in events if event["event"] == "patch_started")
    test_tool = next(event for event in events if event["event"] == "tool_started" and event["tool"] == "run_tests")
    prior_models = [event for event in events if event["event"] == "model_finished"]
    assert read_tool["parent_span_id"] == prior_models[0]["span_id"]
    assert patch_tool["parent_span_id"] == prior_models[1]["span_id"]
    assert patch_span["parent_span_id"] == patch_tool["span_id"]
    assert test_tool["parent_span_id"] == prior_models[2]["span_id"]
    assert requested[0]["parent_span_id"] == prior_models[2]["span_id"]
    serialized_trace = trace_path.read_text(encoding="utf-8")
    assert "SENSITIVE_PATCH_TEXT" not in serialized_trace
    assert "SENSITIVE_TOOL_OUTPUT" not in serialized_trace
    assert any(event["event"] == "approval_expired" for event in events)
    assert any(
        event["event"] == "writeback_finished"
        and event.get("outcome") == "approval_expired"
        for event in events
    )


def test_valid_approval_revalidates_then_applies_once(tmp_path, monkeypatch):
    run_id = "approval-once-offline"
    state_db = tmp_path / "state.sqlite"
    patch_text = "diff --git a/app.py b/app.py\n"
    applied = []

    class SuccessfulAgent:
        def run(self, task, *, progress_callback=None, resume_data=None):
            return RunResult(
                status="success",
                run_id=run_id,
                diff=patch_text,
                test_result=ToolResult(tool_name="run_tests", ok=True, exit_code=0),
            )

    class FakeWorkspaceManager:
        def apply_changes(self, workspace):
            applied.append(workspace)
            return True

    def agent_factory(task, current_run_id, runtime):
        return SuccessfulAgent()

    monkeypatch.setattr(run_graph, "_git_patch", lambda workspace, base: patch_text.encode())
    monkeypatch.setattr(
        run_graph.ToolRegistry,
        "execute",
        lambda self, call: ToolResult(tool_name="run_tests", ok=True, exit_code=0),
    )
    task = Task(
        task_id=run_id,
        repo_path=tmp_path,
        instruction="Repair the test case.",
        test_command=["python", "-m", "pytest"],
    )
    workspace = Workspace(
        source=tmp_path / "source",
        path=tmp_path / "workspace",
        base_commit="a" * 40,
    )
    workspace.path.mkdir()
    manager = FakeWorkspaceManager()
    trace = TraceLogger(tmp_path / "trace.jsonl", run_id)
    pending = run_graph.start_durable_run(
        database=state_db,
        manager=manager,
        agent_factory=agent_factory,
        task=task,
        workspace=workspace,
        run_id=run_id,
        apply_to_repo=True,
        runtime={"execution_mode": "host", "host_tests_approved": True},
        tracer=trace,
    )
    assert "__interrupt__" in pending

    completed = run_graph.resume_durable_run(
        database=state_db,
        manager=manager,
        agent_factory=agent_factory,
        run_id=run_id,
        approved=True,
        tracer=trace,
    )

    assert completed["delivery"] == "applied"
    assert completed["result"]["status"] == "success"
    assert len(applied) == 1
    try:
        run_graph.resume_durable_run(
            database=state_db,
            manager=manager,
            agent_factory=agent_factory,
            run_id=run_id,
            approved=True,
            tracer=trace,
        )
    except ValueError as exc:
        assert "拒绝重复恢复" in str(exc)
    else:
        raise AssertionError("completed writeback checkpoint accepted duplicate approval")
    assert len(applied) == 1
