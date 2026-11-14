import json
from pathlib import Path

import pytest

from evals.cp2_benchmark import (
    DEFAULT_SELECTION,
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
