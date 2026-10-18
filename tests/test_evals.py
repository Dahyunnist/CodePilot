from pathlib import Path

from evals.runner import MODEL_NAME, ScriptedRepairModel, load_cases


def test_fixed_eval_set_has_five_distinct_cases() -> None:
    cases = load_cases(Path("evals/cases"))

    assert len(cases) == 5
    assert len({case.case_id for case in cases}) == 5
    assert len({case.category for case in cases}) == 5
    assert MODEL_NAME == "scripted-oracle"


def test_scripted_model_starts_with_search_and_ends_with_text() -> None:
    case = load_cases(Path("evals/cases"))[0]
    model = ScriptedRepairModel(case)

    assert model.replies[0].tool_calls[0].name == "search_code"
    assert model.replies[-1].text
