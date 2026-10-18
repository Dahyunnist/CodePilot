import json

from codepilot.schemas import ToolCall, ToolResult
from codepilot.tracing import TraceLogger


def test_trace_records_metadata_without_argument_values(tmp_path) -> None:
    path = tmp_path / "trace.jsonl"
    trace = TraceLogger(path, "run-1")
    call = ToolCall(
        id="call-1",
        name="apply_patch",
        arguments={
            "path": "app.py",
            "old_text": "API_KEY=secret-value",
            "new_text": "API_KEY=other-secret",
        },
    )

    trace.tool_started(2, call)
    trace.tool_finished(2, ToolResult(tool_name="apply_patch", ok=True))

    content = path.read_text(encoding="utf-8")
    events = [json.loads(line) for line in content.splitlines()]
    assert [event["event"] for event in events] == ["tool_started", "tool_finished"]
    assert events[0]["arguments"]["path"] == "app.py"
    assert "secret-value" not in content
    assert "other-secret" not in content
