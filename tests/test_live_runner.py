import json

from evals.live_runner import _trace_usage


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
