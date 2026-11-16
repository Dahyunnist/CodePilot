from datetime import datetime, timezone

import pytest

from evals.runner import build_run_manifest, dataset_manifest_sha, validate_run_manifest, write_run_manifest


def sample_manifest():
    now = datetime.now(timezone.utc).isoformat()
    return build_run_manifest(
        run_id="run-synthetic", trace_id="run-synthetic", git_sha="a" * 40,
        dataset_sha256="b" * 64, started_at=now, ended_at=now, status="success",
    )


def test_scripted_run_manifest_is_valid_and_explicit(tmp_path):
    manifest = sample_manifest()
    validate_run_manifest(manifest)
    assert manifest["model_id"] == "scripted-oracle"
    assert manifest["cost_usd_estimate"] == 0
    assert manifest["runtime_digest"] is None
    output = tmp_path / "run_manifest.json"
    write_run_manifest(output, manifest)
    assert output.exists()


@pytest.mark.parametrize("mutation", ["missing_hash", "unknown_field"])
def test_invalid_manifest_fails_before_report_file_creation(tmp_path, mutation):
    manifest = sample_manifest()
    if mutation == "missing_hash":
        manifest["git_sha"] = "bad"
    else:
        manifest["secret"] = "unexpected"
    output = tmp_path / "new-run" / "run_manifest.json"
    with pytest.raises(ValueError):
        write_run_manifest(output, manifest)
    assert not output.exists()
    assert not output.parent.exists()


def test_dataset_sha_covers_canonical_case_content_and_ids_are_shared(tmp_path):
    case_dir = tmp_path / "one"
    case_dir.mkdir()
    metadata = case_dir / "case.json"
    metadata.write_text('{"case_id":"one","instruction":"fix A"}', encoding="utf-8")
    before = dataset_manifest_sha(tmp_path)
    metadata.write_text('{"case_id":"one","instruction":"fix B"}', encoding="utf-8")
    assert dataset_manifest_sha(tmp_path) != before
    run = build_run_manifest(run_id="batch-1", trace_id="batch-1", git_sha="a"*40,
        dataset_sha256=dataset_manifest_sha(tmp_path), started_at=datetime.now(timezone.utc).isoformat(),
        ended_at=datetime.now(timezone.utc).isoformat(), status="success")
    row = {"evaluation_run_id": "batch-1", "trace_id": "batch-1"}
    assert row["evaluation_run_id"] == run["run_id"] == run["trace_id"]
