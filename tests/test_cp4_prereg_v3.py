import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "evals/skills/cp4-paired-protocol-v3-2026-11-16.json"
ARCHIVES = {
    "cp4-paired-protocol-2026-11-15.json": "v1",
    "cp4-paired-protocol-v2-2026-11-15.json": "v2",
}


def _canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_cp4_v3_is_blocked_and_archives_v1_v2_unchanged():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    recorded = protocol.pop("protocol_sha256")
    assert _canonical_hash(protocol) == recorded
    assert protocol["schema_version"] == 3
    assert protocol["status"] == "preregistered-blocked-not-executed"
    assert protocol["model_calls"] == 0
    assert protocol["claims_skill_improvement"] is False
    assert protocol["model_configuration"]["model_id"] is None
    assert protocol["runtime_configuration"]["runtime_digest"] is None
    assert protocol["budget_configuration"]["campaign_reserve_usd"] is None
    for filename, label in ARCHIVES.items():
        archived = json.loads((ROOT / "evals/skills" / filename).read_text(encoding="utf-8"))
        assert protocol["archive_protocol_sha256"][filename] == archived["protocol_sha256"]
        assert label in {"v1", "v2"}


def test_cp4_v3_current_evaluation_inputs_match_frozen_hashes():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert set(protocol["evaluation_input_paths"]) == set(protocol["frozen_inputs_sha256"])
    assert "tests/test_cp4_prereg_v3.py" not in protocol["evaluation_input_paths"]
    for relative, expected in protocol["frozen_inputs_sha256"].items():
        path = (ROOT / relative).resolve(strict=True)
        path.relative_to(ROOT.resolve(strict=True))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
