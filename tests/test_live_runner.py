import json
from pathlib import Path

from evals.live_runner import _trace_usage


def test_trace_usage_sums_prompt_cache_output_and_estimated_offpeak_cost(tmp_path: Path, monkeypatch) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        "\n".join(
            json.dumps(event)
            for event in [
                {"event": "model_finished", "input_tokens": 100, "cached_input_tokens": 70, "output_tokens": 10},
                {"event": "model_finished", "input_tokens": 50, "cached_input_tokens": 40, "output_tokens": 5},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("evals.live_runner._deepseek_pricing_period", lambda: "off-peak")

    usage = _trace_usage(trace, "deepseek-v4-flash")

    assert usage["input_tokens"] == 150
    assert usage["cached_input_tokens"] == 110
    assert usage["output_tokens"] == 15
    assert usage["cost_usd_estimate"] == "0.000015"
    assert usage["pricing_period"] == "off-peak"
