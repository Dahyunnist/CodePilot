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
