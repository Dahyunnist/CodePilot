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
from codepilot.context_selector import ContextSelector


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

def test_same_task_paired_clipping_keeps_cross_file_and_unfinished_test():
    from evals.context_selector_offline import measure_duplicate_pair
    report=measure_duplicate_pair(3,4000)
    assert report["sample_count"]==3
    assert report["model_calls"]==0
    assert report["median_redundant_chars_removed"]>0
    assert all(row["cross_file_retained"] for row in report["runs"])
    assert all(row["unfinished_test_retained"] for row in report["runs"])
    assert all(row["within_budget"] for row in report["runs"])


def test_duplicate_sha_compaction_keeps_latest_full_evidence_and_replaces_older():
    content = "caller in service.py:42\n" + ("evidence " * 40)
    messages = [
        ChatMessage(role="tool", tool_call_id="old", content=content),
        ChatMessage(role="tool", tool_call_id="new", content=content),
    ]
    replaced = ContextSelector.deduplicate_history(messages)
    assert replaced == 1
    assert "重复工具证据已去重" in messages[0].content
    assert "caller in service.py:42" in messages[1].content
    assert content not in messages[0].content


def test_cp1_budget_truncation_and_duplicate_sha_contract():
    import hashlib

    from codepilot.agent import (
        _bounded_tool_result,
        _context_chars,
        _fit_context,
        _future_output_reservations,
        _protected_future_tokens,
        _tool_observation,
    )
    from codepilot.schemas import ChatMessage, ToolResult

    assert _future_output_reservations() == (512, 1_024, 512)
    assert _protected_future_tokens(9_000, (), needs_test=True) == 2_048
    assert _protected_future_tokens(9_000, (), needs_test=False) == 0

    raw_output = "BEGIN_SOURCE\n" + ("payload " * 600) + "\nEND_SOURCE"
    original = ToolResult(tool_name="read_file", ok=True, stdout=raw_output)
    bounded = _bounded_tool_result(original, 512)
    assert original.stdout == raw_output
    assert len(bounded.stdout) + len(bounded.stderr) <= 512
    assert bounded.truncation_reason == "agent_context_observation_limit"
    assert bounded.original_chars == len(raw_output)
    assert bounded.retained_chars == len(bounded.stdout) + len(bounded.stderr)
    assert "已截断" in bounded.stdout
    assert f"原文共 {len(raw_output)} 字符" in bounded.stdout
    assert "BEGIN_SOURCE" in bounded.stdout and "END_SOURCE" in bounded.stdout

    observation = _tool_observation("read_file", bounded, ())
    repeated = [
        ChatMessage(role="tool", tool_call_id=call_id, content=observation)
        for call_id in ("source-a", "source-b")
    ]
    expected_sha = hashlib.sha256(observation.encode("utf-8")).hexdigest()

    _fit_context(repeated, 4_000)

    assert _context_chars(repeated) <= 4_000
    assert "重复工具证据已去重" in (repeated[0].content or "")
    assert f"SHA-256: {expected_sha}" in (repeated[0].content or "")
    assert repeated[1].content == observation

