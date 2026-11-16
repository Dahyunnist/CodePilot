"""Measure layered context retention without making model requests."""

from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path

from codepilot.agent import _context_chars, _fit_context
from codepilot.schemas import ChatMessage, ToolCall


def _fixture() -> list[ChatMessage]:
    return [
        ChatMessage(
            role="assistant",
            tool_calls=[
                ToolCall(id=f"call-{name}", name=name, arguments={"path": f"src/{name}.py"})
                for name in ("read_file", "search_code", "run_tests")
            ],
        ),
        ChatMessage(
            role="tool",
            tool_call_id="call-run_tests",
            content="TEST_RESULT_COMPLETE: 42 passed, 0 failed\n" + "detail " * 500,
        ),
        ChatMessage(
            role="tool",
            tool_call_id="call-read_file",
            content="SOURCE_EVIDENCE\n" + "source " * 1_600,
        ),
        ChatMessage(
            role="tool",
            tool_call_id="call-search_code",
            content="SEARCH_EVIDENCE\n" + "search " * 800,
        ),
    ]


def _measure(*, enabled: bool, budget: int) -> dict[str, object]:
    messages = copy.deepcopy(_fixture())
    start = time.perf_counter_ns()
    compacted = _fit_context(
        messages,
        budget,
        deduplicate=enabled,
        prioritize_layers=enabled,
    )
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    tool_evidence = {
        message.tool_call_id: message.content or ""
        for message in messages
        if message.role == "tool"
    }
    return {
        "variant": "layered_selector" if enabled else "chronological_baseline",
        "context_budget_chars": budget,
        "retained_context_chars": _context_chars(messages),
        "compaction_operations": compacted,
        "elapsed_ms": round(elapsed_ms, 4),
        "test_result_intact": "TEST_RESULT_COMPLETE: 42 passed, 0 failed"
        in tool_evidence["call-run_tests"],
        "test_output_compacted": len(tool_evidence["call-run_tests"])
        < len(_fixture()[1].content or ""),
        "source_evidence_retained_chars": len(tool_evidence["call-read_file"]),
        "search_evidence_retained_chars": len(tool_evidence["call-search_code"]),
        "test_evidence_retained_chars": len(tool_evidence["call-run_tests"]),
    }


def measure_pair(budget: int = 4_000) -> dict[str, object]:
    selector = _measure(enabled=True, budget=budget)
    baseline = _measure(enabled=False, budget=budget)
    return {
        "benchmark_type": "synthetic_context_algorithm_replay",
        "model_requests": 0,
        "model_efficacy_claimed": False,
        "model_cost_usd": 0,
        "context_selector_version": "layered-context-v1",
        "baseline": baseline,
        "selector": selector,
        "delta": {
            "retained_context_chars": selector["retained_context_chars"]
            - baseline["retained_context_chars"],
            "test_evidence_retained_chars": selector["test_evidence_retained_chars"]
            - baseline["test_evidence_retained_chars"],
            "test_evidence_retention_ratio": round(
                selector["test_evidence_retained_chars"]
                / max(1, baseline["test_evidence_retained_chars"]),
                3,
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=4_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = measure_pair(args.budget)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

def measure_duplicate_pair(repeats: int = 3, budget: int = 1_500) -> dict[str, object]:
    """Same-task deterministic synthetic pair; uses _context_chars for both arms."""
    import statistics
    deltas=[]
    retained=[]
    for trial in range(repeats):
        digest="sha256:shared-source-evidence"
        repeated=f"{digest} source evidence " + "detail " * 240
        fixture=[
            ChatMessage(role="assistant",tool_calls=[
                ToolCall(id=f"src-{trial}-{i}",name="read_file",arguments={}) for i in range(3)
            ]+[ToolCall(id=f"xref-{trial}",name="find_references",arguments={}),ToolCall(id=f"pending-{trial}",name="run_tests",arguments={})]),
            *(ChatMessage(role="tool",tool_call_id=f"src-{trial}-{i}",content=repeated) for i in range(3)),
            ChatMessage(role="tool",tool_call_id=f"xref-{trial}",content="CROSS_FILE_COMPLEMENT: client.py:88 calls service.fetch"),
            ChatMessage(role="tool",tool_call_id=f"pending-{trial}",content="TEST_INCOMPLETE: 3 passed, 1 still running"),
        ]
        baseline=copy.deepcopy(fixture); selected=copy.deepcopy(fixture)
        _fit_context(baseline,budget,deduplicate=False,prioritize_layers=False)
        _fit_context(selected,budget,deduplicate=True,prioritize_layers=True)
        before=_context_chars(baseline); after=_context_chars(selected)
        text="\n".join(m.content or "" for m in selected if m.role=="tool")
        deltas.append(before-after)
        retained.append({"trial":trial+1,"input_chars":_context_chars(fixture),"baseline_chars":before,"selector_chars":after,"redundant_chars_removed":before-after,"cross_file_retained":"CROSS_FILE_COMPLEMENT" in text,"unfinished_test_retained":"TEST_INCOMPLETE" in text,"within_budget":after<=budget})
    gains=[x["redundant_chars_removed"] for x in retained]
    return {"kind":"synthetic_same_task_context_pair","model_calls":0,"token_counter":"codepilot.agent._context_chars (serialized chars; not model tokens)","sample_count":repeats,"budget_chars":budget,"median_redundant_chars_removed":statistics.median(gains),"runs":retained}
