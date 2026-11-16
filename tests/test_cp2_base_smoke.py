import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from scripts.run_cp2_base_smoke import _safe_log, run_smoke


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, str, str, str]:
    task_id = "example__repo-1"
    commit = "a" * 40
    tree = "b" * 40
    image_digest = "sha256:" + "c" * 64
    case_dir = tmp_path / "cases" / task_id
    test_path = case_dir / "visible_tests" / "tests" / "test_example.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_fails_on_base(): pass\n", encoding="utf-8")
    test_hash = hashlib.sha256(test_path.read_bytes()).hexdigest()
    source_manifest = {"case_id": task_id, "files": {}}
    source_path = case_dir / "source-files.json"
    _write_json(source_path, source_manifest)
    case = {
        "case_id": task_id,
        "source_commit": commit,
        "source_tree_sha": tree,
        "source_file_manifest_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "test_command": ["python", "-m", "pytest", "tests/test_example.py"],
        "docker_image": "example/image:latest",
        "docker_image_config_digest": image_digest,
        "docker_python": "/venv/bin/python",
        "visible_test_files": ["tests/test_example.py"],
        "visible_test_sha256": test_hash,
        "baseline_expected_failure": True,
        "test_timeout_seconds": 4,
    }
    _write_json(case_dir / "case.json", case)
    subset = {
        "schema_version": 1,
        "task_count": 1,
        "tasks": [{"task_id": task_id, "base_commit": commit,
                   "docker_image_config_digest": image_digest}],
    }
    canonical = json.dumps(subset, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    subset["subset_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    subset_path = tmp_path / "subset.json"
    _write_json(subset_path, subset)
    return subset_path, tmp_path / "cases", commit, tree, image_digest


def test_smoke_records_expected_base_failure_with_network_disabled(tmp_path: Path) -> None:
    subset, cases, commit, tree, image_digest = _fixture(tmp_path)
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs):
        calls.append(command)
        if command[1:3] == ["image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=image_digest + "\n", stderr="")
        if any("rev-parse HEAD" in argument for argument in command):
            return SimpleNamespace(returncode=0, stdout=f"{commit}\n{tree}\n", stderr="")
        return SimpleNamespace(returncode=1, stdout="one expected failure\n", stderr="")

    report = run_smoke(subset, cases, runner=runner)

    assert report["status"] == "completed"
    assert report["expected_baseline_failure_count"] == 1
    assert report["blocked_count"] == report["unexpected_count"] == 0
    assert report["model_calls"] == 0
    assert report["network_enabled"] is False
    assert report["agent_repair_attempted"] is False
    assert report["results"][0]["status"] == "expected_baseline_failure"
    run_commands = [command for command in calls if "run" in command]
    assert len(run_commands) == 2
    assert all("--pull=never" in command and "--network" in command for command in run_commands)
    assert all(command[command.index("--network") + 1] == "none" for command in run_commands)
    assert "--mount" in run_commands[-1]
    serialized = json.dumps(report)
    assert tmp_path.as_posix() not in serialized
    assert "[REDACTED_LOCAL_PATH]" in serialized


def test_smoke_fails_closed_on_image_digest_mismatch(tmp_path: Path) -> None:
    subset, cases, _commit, _tree, _image_digest = _fixture(tmp_path)
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="sha256:" + "d" * 64, stderr="")

    report = run_smoke(subset, cases, runner=runner)

    assert report["status"] == "blocked"
    assert report["results"][0]["reason"] == "local image digest differs from frozen benchmark"
    assert len(calls) == 1


def test_smoke_marks_docker_start_failure_blocked(tmp_path: Path) -> None:
    subset, cases, _commit, _tree, image_digest = _fixture(tmp_path)

    def runner(command: list[str], **kwargs):
        if command[1:3] == ["image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=image_digest, stderr="")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    report = run_smoke(subset, cases, runner=runner)

    assert report["status"] == "blocked"
    assert report["blocked_count"] == 1
    assert report["results"][0]["reason"] == "container base revision check failed"


def test_smoke_blocks_visible_test_hash_drift_before_docker(tmp_path: Path) -> None:
    subset, cases, *_ = _fixture(tmp_path)
    test = cases / "example__repo-1" / "visible_tests" / "tests" / "test_example.py"
    test.write_text("def changed(): pass\n", encoding="utf-8")
    calls = 0

    def runner(command: list[str], **kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    report = run_smoke(subset, cases, runner=runner)

    assert report["blocked_count"] == 1
    assert "visible test hash mismatch" in report["results"][0]["reason"]
    assert calls == 0


def test_log_sanitizer_removes_keys_paths_and_secret_assignments() -> None:
    safe = _safe_log("key=sk-AbCdEf0123456789 C:\\Users\\person\\secret.txt token=hidden")

    assert "sk-AbCdEf0123456789" not in safe
    assert "C:\\Users\\person" not in safe
    assert "hidden" not in safe
