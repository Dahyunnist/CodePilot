from datetime import datetime, timezone

import pytest

from evals.runner import build_run_manifest, validate_run_manifest, write_run_manifest


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
