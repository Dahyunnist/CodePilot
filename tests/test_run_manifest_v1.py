import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evals.manifests.validate_run_manifest import REQUIRED, validate
from evals.runner import RUN_MANIFEST_FIELDS, build_run_manifest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "evals/manifests/cp1_fixture_run_v1.json"


def _example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_offline_example_manifest_validates():
    assert validate(_example()) == []


def test_shared_schema_matches_builder_and_validator_fields():
    schema = json.loads((ROOT / "evals/manifests/run_manifest_v1.schema.json").read_text(encoding="utf-8"))
    assert set(schema["required"]) == RUN_MANIFEST_FIELDS == REQUIRED
    assert schema["additionalProperties"] is False


def test_runner_output_validates_against_shared_contract():
    stamp = datetime.now(timezone.utc).isoformat()
    manifest = build_run_manifest(
        run_id="run-1", trace_id="trace-1", git_sha="a" * 40,
        dataset_sha256="b" * 64, started_at=stamp, ended_at=stamp, status="success",
    )
    assert validate(manifest) == []


def test_manifest_rejects_missing_identity_bad_sha_and_unknown_fields():
    data = _example()
    data.pop("dataset_id")
    data["git_sha"] = "bad"
    data["extra"] = "not allowed"
    errors = validate(data)
    assert "missing:dataset_id" in errors
    assert "invalid:git_sha" in errors
    assert "unsupported:extra" in errors


def test_manifest_rejects_sensitive_fields():
    data = _example()
    data["api_key"] = "must-not-serialize"
    assert "sensitive_field:api_key" in validate(data)


@pytest.mark.parametrize("field, value, expected", [
    ("project", "other", "invalid:project"),
    ("model_id", "remote-model", "invalid:model_id"),
    ("max_steps", True, "invalid:max_steps"),
    ("max_tokens", -1, "invalid:max_tokens"),
    ("cost_usd_estimate", 0.1, "scripted_oracle_cost_must_be_zero"),
    ("status", "unknown", "invalid:status"),
])
def test_manifest_rejects_invalid_shared_values(field, value, expected):
    data = _example()
    data[field] = value
    assert expected in validate(data)
