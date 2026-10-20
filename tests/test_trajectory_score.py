import json

from evals.trajectory_score import load_splits, score_row


def test_frozen_splits_reject_case_leakage(tmp_path):
    path = tmp_path / "splits.json"
    path.write_text(
        json.dumps({"train": ["a"], "validation": ["a"], "test": []}),
        encoding="utf-8",
    )

    try:
        load_splits(path)
    except ValueError as exc:
        assert "multiple splits" in str(exc)
    else:
        raise AssertionError("overlapping case split must be rejected")


def test_accepted_run_gets_completion_reward_and_efficiency_penalties():
    row = score_row(
        {
            "case_id": "case-a",
            "run_id": "run-a",
            "status": "success",
            "accepted": "True",
            "tokens": "10000",
            "evaluation_elapsed_ms": "30000",
        },
        "train",
    )

    assert row["reward"] == 99.0
    assert row["accepted"] is True


def test_budget_and_independent_test_failures_are_penalized(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        json.dumps({"event": "tool_finished", "error_type": "PathPolicyError"}) + "\n",
        encoding="utf-8",
    )
    row = score_row(
        {
            "case_id": "case-a",
            "status": "budget_exceeded",
            "accepted": "False",
            "agent_test_ok": "False",
            "independent_visible_ok": "False",
            "hidden_ok": "False",
            "tokens": "0",
            "evaluation_elapsed_ms": "0",
            "trace_file": str(trace),
        },
        "test",
    )

    assert row["path_policy_denials"] == 1
    assert row["reward"] == -180.0
