import importlib.util
from pathlib import Path

MODULE = Path(__file__).parents[1] / "evals" / "public_issues" / "validate_manifest.py"
spec = importlib.util.spec_from_file_location("validate_manifest", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
base = {"id":"x", "repository":"a/b", "issue_url":"https://example.com", "status":"pending_reproduction"}

def test_pending_candidate_accepts_empty_repro_fields():
    assert module.validate(base) == []

def test_frozen_without_reproduction_is_rejected():
    item = {**base, "status":"frozen"}
    assert "missing:base_sha" in module.validate(item)
    assert "missing:reproduction_passed" in module.validate(item)

def test_frozen_without_license_rejected():
    item = {**base, "status":"frozen", "base_sha":"a", "fix_sha":"b", "test_commands":["pytest"], "reproduction_passed":True}
    assert "missing:license" in module.validate(item)

def test_frozen_without_test_commands_rejected():
    item = {**base, "status":"frozen", "license":"MIT", "base_sha":"a", "fix_sha":"b", "reproduction_passed":True}
    assert "missing:test_commands" in module.validate(item)
