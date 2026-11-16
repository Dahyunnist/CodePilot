import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "evals/skills/cp4-paired-protocol-v2-2026-11-15.json"


def _canonical_hash(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_cp4_v2_prereg_is_immutable_blocked_and_has_zero_calls():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    recorded = protocol.pop("protocol_sha256")

    assert _canonical_hash(protocol) == recorded
    assert protocol["schema_version"] == 2
    assert protocol["status"] == "preregistered-blocked-not-executed"
    assert protocol["model_calls"] == 0
    assert protocol["claims_skill_improvement"] is False
    assert re.fullmatch(r"[0-9a-f]{40}", protocol["source_revision"])
    assert protocol["model_configuration"]["model_id"] is None
    assert protocol["runtime_configuration"]["runtime_digest"] is None
    budget = protocol["budget_configuration"]
    assert budget["authorized_campaign_cap_usd"] == "0.50"
    assert budget["campaign_reserve_usd"] is None
    assert budget["status"].startswith("blocked_")
    assert protocol["budget_configuration_sha256"] == _canonical_hash(budget)


def test_cp4_v2_frozen_inputs_and_pairing_are_verifiable():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    for relative, expected in protocol["frozen_inputs_sha256"].items():
        path = (ROOT / relative).resolve(strict=True)
        path.relative_to(ROOT.resolve(strict=True))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    pairs = protocol["pairing"]["pairs"]
    assert [(p["baseline_skill_id"], p["treatment_skill_id"]) for p in pairs] == [
        ("none", "pytest-failure-triage"),
        ("none", "api-contract-check"),
    ]
