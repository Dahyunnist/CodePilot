import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
CP2 = ROOT / "evals/public_cases/cp2"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pytest_8365_supplemental_case_binds_public_sources_and_results():
    task_id = "pytest-dev__pytest-8365"
    case = _read_json(CP2 / "cases" / task_id / "case.json")
    manifest = _read_json(CP2 / "supplemental-public-cases-v1.json")
    report = _read_json(CP2 / "reproductions/pytest_8365/reproduction.json")

    assert case["case_scope"] == "public_development_case"
    assert case["blind_holdout"] is False
    assert case["base_commit"] == case["image_parent_base_commit"]
    assert case["base_commit_verified_in_image"] is True
    assert case["docker_image_config_digest"].startswith("sha256:")
    assert len(case["official_fix_commit_sha"]) == 40
    assert len(case["official_pr_head_sha"]) == 40
    assert case["official_patch_url"].endswith("/pull/8365.patch")
    assert len(case["official_patch_sha256"]) == 64
    assert len(case["visible_test_sha256"]) == 64

    assert manifest["frozen_selection_modified"] is False
    assert manifest["blind_holdout"] is False
    assert manifest["hidden_tests_included"] is False
    assert manifest["task_count"] == 1
    assert manifest["tasks"][0]["task_id"] == task_id
    assert manifest["tasks"][0]["base_visible_result"] == "failed_exit_1"
    assert manifest["tasks"][0]["official_fix_visible_result"] == "passed_exit_0"

    frozen = _read_json(CP2 / "benchmark-v1.json")
    assert frozen["task_count"] == 15
    assert task_id not in {task["task_id"] for task in frozen["tasks"]}

    assert report["evidence_status"] == "verified_public_base_failure_and_official_fix_pass"
    assert report["environment"]["base_commit_match"] is True
    assert report["visible_test"]["base"]["exit_code"] == 1
    assert report["visible_test"]["official_fix"]["exit_code"] == 0
    assert report["scope"]["agent_runs"] == 0
    assert report["scope"]["model_calls"] == 0
    assert report["scope"]["hidden_tests_read_or_run"] is False
