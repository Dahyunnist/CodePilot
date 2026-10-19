from pathlib import Path

from evals.runner import MODEL_NAME, ScriptedRepairModel, load_cases


def test_eval_set_has_distinct_cases_and_a_cross_module_repair() -> None:
    cases = load_cases(Path("evals/cases"))

    assert len(cases) == 6
    assert len({case.case_id for case in cases}) == 6
    assert len({case.category for case in cases}) == 6
    multi_file = next(case for case in cases if case.case_id == "multi-file-discount")
    assert len(multi_file.patches) == 2
    assert {patch.path for patch in multi_file.patches} == {
        "commerce/request.py",
        "commerce/pricing.py",
    }
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
