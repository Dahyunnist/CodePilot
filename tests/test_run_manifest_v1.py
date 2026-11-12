from copy import deepcopy
import json
from pathlib import Path
from evals.manifests.validate_run_manifest import validate
EXAMPLE=Path("evals/manifests/cp1_fixture_run_v1.json")
def test_offline_example_manifest_validates():
    assert validate(json.loads(EXAMPLE.read_text(encoding="utf-8"))) == []
def test_manifest_rejects_missing_identity_and_bad_sha():
    data=json.loads(EXAMPLE.read_text(encoding="utf-8")); data.pop("dataset_id"); data["git_sha"]="bad"
    errors=validate(data)
    assert "missing:dataset_id" in errors and "invalid:git_sha" in errors
def test_manifest_rejects_sensitive_fields():
    data=json.loads(EXAMPLE.read_text(encoding="utf-8")); data["api_key"]="must-not-serialize"
    assert "sensitive_field:api_key" in validate(data)
