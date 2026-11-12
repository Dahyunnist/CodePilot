from evals.context_selector_offline import measure_pair


def test_offline_pair_measures_retention_without_model_calls():
    report = measure_pair(7_000)

    assert report["model_requests"] == 0
    assert report["model_cost_usd"] == 0
    assert report["model_efficacy_claimed"] is False
    assert report["baseline"]["test_result_intact"] is True
    assert report["selector"]["test_result_intact"] is True
    assert report["selector"]["test_evidence_retained_chars"] > report["baseline"]["test_evidence_retained_chars"]
    assert report["delta"]["test_evidence_retention_ratio"] > 1

import copy
import statistics
from codepilot.agent import _context_chars, _fit_context
from codepilot.schemas import ChatMessage, ToolCall


def test_three_task_same_sha_pair_reduces_redundancy_and_keeps_cross_file_evidence():
    results = []
    for i in range(3):
        shared = f"sha:{i}:" + ("dependency evidence " * 80)
        fixture = [
            ChatMessage(role="assistant", tool_calls=[
                ToolCall(id=f"read-{i}-a", name="read_file", arguments={}),
                ToolCall(id=f"read-{i}-b", name="read_file", arguments={}),
                ToolCall(id=f"read-{i}-c", name="find_references", arguments={}),
            ]),
            ChatMessage(role="tool", tool_call_id=f"read-{i}-a", content=shared),
            ChatMessage(role="tool", tool_call_id=f"read-{i}-b", content=shared),
            ChatMessage(role="tool", tool_call_id=f"read-{i}-c", content="CROSS_FILE_CALLER: caller.py:21"),
        ]
        baseline = copy.deepcopy(fixture)
        selected = copy.deepcopy(fixture)
        _fit_context(baseline, 20_000, deduplicate=False, prioritize_layers=False)
        _fit_context(selected, 20_000, deduplicate=True, prioritize_layers=True)
        baseline_tokens = _context_chars(baseline)
        selected_tokens = _context_chars(selected)
        selected_text = "\n".join(m.content or "" for m in selected if m.role == "tool")
        assert "CROSS_FILE_CALLER: caller.py:21" in selected_text
        assert selected_tokens < baseline_tokens
        results.append(baseline_tokens - selected_tokens)
    median = statistics.median(results)
    assert len(results) == 3 and median > 0
