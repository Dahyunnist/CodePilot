import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "evals" / "skills" / "cp4-paired-protocol-2026-11-15.json"


def _canonical_sha256(value: dict[str, object]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_cp4_v1_archive_is_frozen_and_not_executed():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    recorded_protocol_hash = protocol.pop("protocol_sha256")

    assert _canonical_sha256(protocol) == recorded_protocol_hash
    assert protocol["status"] == "frozen-not-executed"
    assert protocol["model_calls"] == 0
    assert protocol["claims_skill_improvement"] is False
    assert protocol["pairing"]["dimension"] == "skill"

    assert protocol["frozen_inputs_sha256"]
    assert all(len(value) == 64 for value in protocol["frozen_inputs_sha256"].values())


def test_cp4_protocol_pairs_each_case_with_only_its_matching_skill():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    fixture = json.loads(
        (ROOT / "evals" / "skills" / "paired-smoke.json").read_text(encoding="utf-8")
    )
    pairs = protocol["pairing"]["pairs"]

    assert [(pair["case_id"], pair["baseline_skill_id"]) for pair in pairs] == [
        (entry["case_id"], "none") for entry in fixture["cases"]
    ]
    assert [pair["treatment_skill_id"] for pair in pairs] == [
        "pytest-failure-triage",
        "api-contract-check",
    ]
    assert "model and provider endpoint" in protocol["pairing"]["hold_constant"]
    assert "execution mode and pinned Docker image digest" in protocol["pairing"]["hold_constant"]


def test_cp4_freeze_drift_audit_records_archived_and_current_hashes():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    audit = (ROOT / "docs/learning/cp4-freeze-drift-audit-2026-11-15.md").read_text(
        encoding="utf-8"
    )

    for relative_path in ("codepilot/agent.py", "evals/live_runner.py"):
        archived = protocol["frozen_inputs_sha256"][relative_path]
        current = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert f"`{relative_path}` | `{archived}` | `{current}` |" in audit
        assert current != archived
