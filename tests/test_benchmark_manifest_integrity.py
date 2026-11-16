import json
from pathlib import Path

ROOT = Path(__file__).parents[1]

def test_swebench_frozen_selection_declares_scope_without_claiming_execution():
    manifest = json.loads((ROOT / "evals/public_cases/cp2/frozen-selection.json").read_text(encoding="utf-8"))
    assert manifest["repository_count"] == 5
    assert manifest["task_count"] == 20
    assert sum(manifest["tasks_per_repository"].values()) == manifest["task_count"]
    assert set(manifest["tasks_per_repository"]) == {
        "django/django", "mwaskom/seaborn", "pydata/xarray",
        "pytest-dev/pytest", "scikit-learn/scikit-learn",
    }
    assert "real_model_authorized" not in manifest or manifest["real_model_authorized"] is False


def test_cp4_pilot_is_pending_preflight_and_has_model_budget_ceiling():
    manifest = json.loads((ROOT / "evals/public_cases/cp4/three-repository-skill-pilot-2026-10-23.json").read_text(encoding="utf-8"))
    assert manifest["preflight_status"] == "pending_materialization_and_visible_hidden_baselines"
    assert manifest["real_model_authorized"] is True
    assert manifest["limits"]["authorized_total_ceiling_usd"] == 0.50
    assert manifest["limits"]["run_count"] == 6
