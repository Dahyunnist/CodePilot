from pathlib import Path

from evals.runner import MODEL_NAME, ScriptedRepairModel, load_cases


def test_eval_set_has_distinct_cases_and_a_cross_module_repair() -> None:
    cases = load_cases(Path("evals/cases"))

    assert len(cases) == 9
    assert len({case.case_id for case in cases}) == 9
    assert len({case.category for case in cases}) == 9
    multi_file = next(case for case in cases if case.case_id == "multi-file-discount")
    assert len(multi_file.patches) == 2
    assert {patch.path for patch in multi_file.patches} == {
        "commerce/request.py",
        "commerce/pricing.py",
    }
    invoice = next(case for case in cases if case.case_id == "multi-bug-invoice")
    assert len(invoice.patches) == 3
    assert len({patch.path for patch in invoice.patches}) == 3
    performance = next(
        case for case in cases if case.case_id == "notification-batch-performance"
    )
    assert performance.category == "query-complexity-and-idempotency"
    assert len(performance.patches) == 2
    bulk_write = next(
        case for case in cases if case.case_id == "bulk-audit-write-performance"
    )
    assert bulk_write.category == "bulk-write-and-idempotency"
    assert len(bulk_write.patches) == 2
    assert MODEL_NAME == "scripted-oracle"


def test_scripted_model_starts_with_search_and_ends_with_text() -> None:
    case = load_cases(Path("evals/cases"))[0]
    model = ScriptedRepairModel(case)

    assert model.replies[0].tool_calls[0].name == "search_code"
    assert model.replies[-1].text


def test_scripted_model_reads_and_patches_every_file_in_multi_file_case() -> None:
    case = next(
        case
        for case in load_cases(Path("evals/cases"))
        if case.case_id == "multi-file-discount"
    )
    model = ScriptedRepairModel(case)

    read_calls = model.replies[1].tool_calls
    patch_calls = model.replies[3].tool_calls
    assert [call.arguments["path"] for call in read_calls] == [
        "commerce/request.py",
        "commerce/pricing.py",
    ]
    assert [call.arguments["path"] for call in patch_calls] == [
        "commerce/request.py",
        "commerce/pricing.py",
    ]


def test_scripted_model_covers_cross_module_multi_bug_and_performance_cases() -> None:
    cases = {case.case_id: case for case in load_cases(Path("evals/cases"))}
    for case_id, expected_paths in {
        "multi-bug-invoice": [
            "billing/request.py",
            "billing/pricing.py",
            "billing/invoice.py",
        ],
        "notification-batch-performance": [
            "notify/store.py",
            "notify/dispatch.py",
        ],
        "bulk-audit-write-performance": [
            "audit/store.py",
            "audit/writer.py",
        ],
    }.items():
        model = ScriptedRepairModel(cases[case_id])
        assert [call.arguments["path"] for call in model.replies[1].tool_calls] == expected_paths
        assert [call.arguments["path"] for call in model.replies[3].tool_calls] == expected_paths
