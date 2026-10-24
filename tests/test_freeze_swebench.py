import json

import pytest

from evals.public_cases.freeze_swebench_lite import TASK_IDS, freeze


def make_rows():
    rows = []
    for index, task_id in enumerate(TASK_IDS):
        repo = task_id.rsplit("-", 1)[0].replace("__", "/")
        rows.append(
            {
                "instance_id": task_id,
                "repo": repo,
                "base_commit": f"commit-{index}",
                "problem_statement": f"Issue description {task_id}",
                "issue_url": f"https://example.test/issues/{index}",
                "pr_url": "",
                "image": f"example/image-{index}",
                "test_patch": (
                    "diff --git a/tests/test_case.py b/tests/test_case.py\n"
                    "--- a/tests/test_case.py\n+++ b/tests/test_case.py\n"
                    "@@ -1 +1 @@\n-assert True\n+assert False\n"
                ),
                "patch": f"gold patch {index}",
                "FAIL_TO_PASS": ["tests/test_case.py::test_case"],
                "PASS_TO_PASS": [],
            }
        )
    return rows


def test_freezer_records_hashes_but_never_gold_patch_contents(tmp_path):
    source = tmp_path / "dataset.json"
    rows = make_rows()
    rows[1]["problem_statement"] += "\nExposed api_key=secretvalue"
    source.write_text(json.dumps(rows), encoding="utf-8")
    output = tmp_path / "selection.json"

    manifest = freeze(source, output)

    serialized = output.read_text(encoding="utf-8")
    assert manifest["task_count"] == 20
    assert manifest["repository_count"] == 5
    assert "gold patch 0" not in serialized
    assert len(manifest["tasks"][0]["gold_patch_sha256"]) == 64
    assert "Issue description django__django-10924" in manifest["tasks"][0]["problem_statement"]
    assert manifest["tasks"][0]["pull_request_url"].startswith("https://github.com/django/django/pull/")
    assert "secretvalue" not in serialized
    assert manifest["tasks_per_repository"] == {
        "django/django": 4,
        "mwaskom/seaborn": 4,
        "pydata/xarray": 4,
        "pytest-dev/pytest": 4,
        "scikit-learn/scikit-learn": 4,
    }


def test_freezer_rejects_test_patch_touching_source_file(tmp_path):
    rows = make_rows()
    rows[0]["test_patch"] = "diff --git a/package/module.py b/package/module.py\n"
    source = tmp_path / "dataset.json"
    source.write_text(json.dumps(rows), encoding="utf-8")

    with pytest.raises(ValueError, match="non-test path"):
        freeze(source, tmp_path / "selection.json")


def test_freezer_refuses_to_overwrite_frozen_manifest(tmp_path):
    source = tmp_path / "dataset.json"
    source.write_text(json.dumps(make_rows()), encoding="utf-8")
    output = tmp_path / "selection.json"
    output.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError):
        freeze(source, output)

    assert output.read_text(encoding="utf-8") == "preserve"
