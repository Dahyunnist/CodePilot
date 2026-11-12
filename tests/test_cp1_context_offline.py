import json
from pathlib import Path
from scripts.evaluate_cp1_context_offline import evaluate

FIXTURE=Path("evals/context_selector_fixture.json")

def test_fixture_has_three_frozen_task_ids():
    data=json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(data["tasks"])==3
    assert {t["task_id"] for t in data["tasks"]}=={"django__django-10924","pytest-dev__pytest-5103","pydata__xarray-3364"}

def test_duplicate_sha_reduces_mechanism_token_count():
    report=evaluate(json.loads(FIXTURE.read_text(encoding="utf-8")))
    first=report["tasks"][0]
    assert first["input_tokens"]==1300 and first["deduplicated_tokens"]==900
    assert first["deduplicated_items"]==1

def test_reserves_and_truncation_respect_budget_and_flag_impossible_reserve():
    report=evaluate(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert all(not row["budget_violation"] for row in report["tasks"][:2])
    assert report["tasks"][2]["budget_violation"]
    assert report["tasks"][2]["truncated_tokens"]==400
    assert report["model_calls"]==0 and report["mechanism_only"]

