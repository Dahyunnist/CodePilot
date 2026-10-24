import hashlib
import json

import pytest

from evals.public_cases import freeze_cp3_holdout


def _dataset_bytes(*, non_test_path: bool = False) -> bytes:
    rows = []
    for selection in freeze_cp3_holdout.TASK_SELECTIONS:
        path = "src/module.py" if non_test_path else "tests/test_module.py"
        rows.append(
            {
                "instance_id": selection["task_id"],
                "repo": {
                    "django__django-16379": "django/django",
                    "pytest-dev__pytest-7168": "pytest-dev/pytest",
                    "pydata__xarray-5131": "pydata/xarray",
                    "scikit-learn__scikit-learn-14087": "scikit-learn/scikit-learn",
                }[selection["task_id"]],
                "base_commit": "a" * 40,
                "image": "example/runner:test",
                "created_at": "2020-01-01T00:00:00Z",
                "problem_statement": "A public issue statement.",
                "test_patch": (
                    f"diff --git a/{path} b/{path}\n"
                    f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n"
                    "+HIDDEN_TEST_SENTINEL\n"
                ),
                "patch": "GOLD_PATCH_SENTINEL",
                "FAIL_TO_PASS": ["tests/test_module.py::test_target"],
                "PASS_TO_PASS": ["tests/test_module.py::test_regression"],
            }
        )
    return json.dumps(rows).encode("utf-8")


def test_cp3_freeze_pins_fresh_multirepo_cases_without_oracle_content(tmp_path, monkeypatch):
    raw = _dataset_bytes()
    source = tmp_path / "dataset.json"
    source.write_bytes(raw)
    output = tmp_path / "holdout.json"
    monkeypatch.setattr(
        freeze_cp3_holdout, "DATASET_SOURCE_SHA256", hashlib.sha256(raw).hexdigest()
    )

    manifest = freeze_cp3_holdout.freeze(source, output)

    serialized = output.read_text(encoding="utf-8")
    assert manifest["task_count"] == 4
    assert manifest["repository_count"] == 4
    assert manifest["defect_mechanism_count"] == 4
    assert manifest["real_model_authorized"] is False
    assert manifest["limits"]["worst_case_cost_usd_per_task"] < 0.06
    assert "GOLD_PATCH_SENTINEL" not in serialized
    assert "HIDDEN_TEST_SENTINEL" not in serialized
    assert all("gold_patch_sha256" in task for task in manifest["tasks"])
    assert all("hidden_test_patch_sha256" in task for task in manifest["tasks"])
    assert "urllib3-3653" in manifest["excluded_seen_task_ids"]


def test_cp3_freeze_rejects_s16_s21_exposure(tmp_path, monkeypatch):
    raw = _dataset_bytes()
    source = tmp_path / "dataset.json"
    source.write_bytes(raw)
    monkeypatch.setattr(
        freeze_cp3_holdout, "DATASET_SOURCE_SHA256", hashlib.sha256(raw).hexdigest()
    )

    with pytest.raises(ValueError, match="曾用于模型评测"):
        freeze_cp3_holdout.freeze(
            source,
            tmp_path / "holdout.json",
            selections=(
                {"task_id": "urllib3-3636", "defect_mechanism": "previously exposed"},
                *freeze_cp3_holdout.TASK_SELECTIONS[1:],
            ),
        )


def test_cp3_freeze_rejects_hidden_patch_outside_test_paths(tmp_path, monkeypatch):
    raw = _dataset_bytes(non_test_path=True)
    source = tmp_path / "dataset.json"
    source.write_bytes(raw)
    monkeypatch.setattr(
        freeze_cp3_holdout, "DATASET_SOURCE_SHA256", hashlib.sha256(raw).hexdigest()
    )

    with pytest.raises(ValueError, match="非测试路径"):
        freeze_cp3_holdout.freeze(source, tmp_path / "holdout.json")
