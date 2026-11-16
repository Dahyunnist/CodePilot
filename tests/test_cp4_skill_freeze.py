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


def test_cp4_protocol_and_all_evaluation_inputs_are_frozen():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    recorded_protocol_hash = protocol.pop("protocol_sha256")

    assert _canonical_sha256(protocol) == recorded_protocol_hash
    assert protocol["status"] == "frozen-not-executed"
    assert protocol["model_calls"] == 0
    assert protocol["claims_skill_improvement"] is False
    assert protocol["pairing"]["dimension"] == "skill"

    for relative_path, expected_hash in protocol["frozen_inputs_sha256"].items():
        path = (ROOT / relative_path).resolve(strict=True)
        path.relative_to(ROOT.resolve(strict=True))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash


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
