import json
from pathlib import Path

import pytest

from evals.cp2_benchmark import (
    DEFAULT_SELECTION,
    DEFAULT_SOURCE_PROVENANCE,
    _current_artifact_hashes,
    _canonical_hash,
    freeze_manifest,
    plan,
)


def test_cp2_manifest_freezes_selected_scope_and_artifacts():
    manifest = freeze_manifest(DEFAULT_SELECTION)

    assert manifest["task_count"] == 15
    assert manifest["repository_count"] == 5
    assert manifest["dataset"]["gold_policy"] == "SHA-256 only; no patch content in agent workspace"
    assert manifest["model_sha256"] == _canonical_hash(manifest["model"])
    assert all("gold_patch" not in task for task in manifest["tasks"])
    assert all(task["gold_source"].endswith("gold content not read or exposed") for task in manifest["tasks"])


def test_cp2_freeze_rejects_missing_selected_task(tmp_path: Path):
    selection = json.loads(DEFAULT_SELECTION.read_text(encoding="utf-8"))
    selection["tasks"] = [task for task in selection["tasks"] if task["task_id"] != "django__django-10924"]
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection), encoding="utf-8")

    with pytest.raises(ValueError, match="selection lacks selected tasks"):
        freeze_manifest(selection_path)


def test_cp2_plan_blocks_unverified_budget_and_missing_runtime(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    ledger = {
        "account_usage_reconciled": False,
        "estimated_remaining_usd": "0.01",
    }

    blockers, reserve = plan(manifest, ledger, tmp_path / "cases")

    assert reserve > 0
    assert any("not provider-reconciled" in item for item in blockers)
    assert any("worst-case reserve" in item for item in blockers)
    assert any("runtime image digest missing" in item for item in blockers)
    assert any("visible test baseline is not verified" in item for item in blockers)


def test_cp2_plan_rejects_model_manifest_tampering(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    manifest["model"]["configured_model_alias"] = "tampered"
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(manifest, ledger, tmp_path / "cases")

    assert "model manifest hash mismatch" in blockers


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("public_reference", None, "source PR link missing, invalid, or inconsistent"),
        ("license", None, "license metadata or exact-base evidence missing"),
        ("license_file_sha256", None, "license metadata or exact-base evidence missing"),
        ("docker_image_config_digest", None, "runtime image digest missing"),
        ("visible_test_sha256", None, "materialized visible test hash missing or invalid"),
    ],
)
def test_cp2_plan_stays_blocked_when_source_license_digest_or_test_hash_missing(
    tmp_path: Path, field: str, value: object, expected: str
):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    target = next(item for item in manifest["tasks"] if item["task_id"] == "pytest-dev__pytest-5103")
    target[field] = value
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(manifest, ledger, tmp_path / "cases")

    assert any(expected in blocker for blocker in blockers)


def test_cp2_plan_rejects_missing_or_drifted_evaluator_hash(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    manifest["artifacts"]["paired_driver_sha256"] = "0" * 64
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(manifest, ledger, tmp_path / "cases")

    assert "frozen artifact hash differs from current source: paired_driver_sha256" in blockers


def test_frozen_manifest_records_current_evaluator_hashes():
    manifest = freeze_manifest(DEFAULT_SELECTION)

    assert manifest["artifacts"] == _current_artifact_hashes()


def test_source_provenance_covers_frozen_tasks_and_matches_pull_request_links():
    manifest = freeze_manifest(DEFAULT_SELECTION)
    provenance = json.loads(DEFAULT_SOURCE_PROVENANCE.read_text(encoding="utf-8"))
    rows = {item["task_id"]: item for item in provenance["tasks"]}

    assert set(rows) == {item["task_id"] for item in manifest["tasks"]}
    for task in manifest["tasks"]:
        source = rows[task["task_id"]]
        assert source["repo"] == task["repo"]
        assert source["source_pr_url"] == task["public_reference"]
        assert source["pr_status"] == "merged"
        assert source["linked_issues"]


def test_cp2_plan_blocks_when_issue_pr_provenance_is_missing(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    provenance = json.loads(DEFAULT_SOURCE_PROVENANCE.read_text(encoding="utf-8"))
    first = provenance["tasks"][0]
    first["linked_issues"] = []
    provenance_path = tmp_path / "provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(
        manifest, ledger, tmp_path / "cases", source_provenance_path=provenance_path
    )

    assert f"{first['task_id']}: linked issue provenance missing" in blockers


def test_cp2_plan_blocks_when_provenance_file_is_absent(tmp_path: Path):
    manifest = freeze_manifest(DEFAULT_SELECTION)
    ledger = {"account_usage_reconciled": True, "estimated_remaining_usd": "100"}

    blockers, _ = plan(
        manifest, ledger, tmp_path / "cases",
        source_provenance_path=tmp_path / "missing-provenance.json",
    )

    assert "source provenance manifest missing or invalid" in blockers


def test_cp2_visible_test_and_runtime_status_remain_fail_closed():
    manifest = freeze_manifest(DEFAULT_SELECTION)

    assert len(manifest["tasks"]) == 15
    assert all(
        task["visible_test_status"] == "spec_frozen_test_not_materialized_or_run"
        for task in manifest["tasks"]
    )
    missing_images = [
        task["task_id"] for task in manifest["tasks"]
        if task["docker_image_config_digest"] is None
    ]
    assert missing_images == ["pydata__xarray-4493"]
