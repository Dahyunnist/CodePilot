"""Run the frozen CP-2 three-case base smoke without network or model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUBSET = ROOT / "evals/public_cases/cp2/budget-subset-3-v1.json"
DEFAULT_CASES = ROOT / "evals/public_cases/cp2/cases"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _safe_log(text: str, limit: int = 1800) -> str:
    text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED_KEY]", text)
    text = re.sub(r"(?i)\b[A-Z]:[\\/][^\s\"']+", "[REDACTED_PATH]", text)
    text = re.sub(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-20:])[-limit:]


def _safe_visible_test(case_dir: Path, case: dict[str, Any]) -> tuple[Path, str]:
    files = case.get("visible_test_files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], str):
        raise ValueError("smoke case must freeze exactly one visible test file")
    relative = PurePosixPath(files[0])
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("unsafe visible test path")
    path = case_dir.joinpath("visible_tests", *relative.parts)
    if path.is_symlink():
        raise ValueError("visible test must not be a symlink")
    resolved = path.resolve(strict=True)
    resolved.relative_to((case_dir / "visible_tests").resolve(strict=True))
    expected = case.get("visible_test_sha256")
    actual = _sha256(resolved)
    if not isinstance(expected, str) or actual != expected:
        raise ValueError("visible test hash mismatch")
    return resolved, relative.as_posix()


def _call(
    command: list[str], timeout: float, runner: Callable[..., subprocess.CompletedProcess[str]]
) -> dict[str, Any]:
    start = time.monotonic()
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
        elapsed = time.monotonic() - start
        return {
            "exit_code": result.returncode,
            "elapsed_seconds": round(elapsed, 3),
            "stdout_tail": _safe_log(result.stdout),
            "stderr_tail": _safe_log(result.stderr),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        return {
            "exit_code": None,
            "elapsed_seconds": round(elapsed, 3),
            "stdout_tail": _safe_log(exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""),
            "stderr_tail": _safe_log(exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""),
            "timed_out": True,
        }
    except OSError as exc:
        elapsed = time.monotonic() - start
        return {
            "exit_code": None,
            "elapsed_seconds": round(elapsed, 3),
            "stdout_tail": "",
            "stderr_tail": _safe_log(f"{type(exc).__name__}: {exc}"),
            "timed_out": False,
        }


def run_smoke(
    subset_path: Path = DEFAULT_SUBSET,
    cases_root: Path = DEFAULT_CASES,
    docker: str = "docker",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    subset = _json(subset_path)
    subset_hash = subset.get("subset_sha256")
    hash_payload = {key: value for key, value in subset.items() if key != "subset_sha256"}
    canonical = json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    calculated_subset_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if subset_hash != calculated_subset_hash:
        raise ValueError("frozen budget subset hash mismatch")
    tasks = subset.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("frozen budget subset has no tasks")

    results: list[dict[str, Any]] = []
    for task in tasks:
        task_id = task.get("task_id") if isinstance(task, dict) else None
        row: dict[str, Any] = {"task_id": task_id, "status": "blocked"}
        try:
            if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", task_id):
                raise ValueError("unsafe task ID")
            case_dir = cases_root / task_id
            if case_dir.is_symlink():
                raise ValueError("case directory must not be a symlink")
            case_dir.resolve(strict=True).relative_to(cases_root.resolve(strict=True))
            case_path = case_dir / "case.json"
            if case_path.is_symlink():
                raise ValueError("case metadata must not be a symlink")
            case = _json(case_path)
            if case.get("case_id") != task_id or case.get("source_commit") != task.get("base_commit"):
                raise ValueError("case ID/base commit differs from frozen budget subset")
            source_manifest_path = case_dir / "source-files.json"
            if source_manifest_path.is_symlink():
                raise ValueError("source file manifest must not be a symlink")
            source_manifest_hash = _sha256(source_manifest_path)
            if source_manifest_hash != case.get("source_file_manifest_sha256"):
                raise ValueError("source file manifest hash mismatch")
            source_manifest = _json(source_manifest_path)
            if source_manifest.get("case_id") != task_id:
                raise ValueError("source file manifest case ID mismatch")
            command = case.get("test_command")
            image = case.get("docker_image")
            expected_digest = task.get("docker_image_config_digest")
            commit = task.get("base_commit")
            if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
                raise ValueError("invalid frozen test command")
            if (
                not isinstance(image, str)
                or not image
                or not isinstance(expected_digest, str)
                or case.get("docker_image_config_digest") != expected_digest
            ):
                raise ValueError("missing frozen image reference or digest")
            visible_path, visible_relative = _safe_visible_test(case_dir, case)
            row.update({
                "command": command,
                "image": image,
                "expected_image_config_digest": expected_digest,
                "base_commit": commit,
                "source_manifest_sha256": source_manifest_hash,
                "visible_test_sha256": _sha256(visible_path),
                "visible_test_path": visible_relative,
            })

            inspect = _call(
                [docker, "image", "inspect", image, "--format", "{{.Id}}"], 30, runner
            )
            row["image_inspect"] = inspect
            if inspect["exit_code"] != 0 or inspect["timed_out"]:
                row["reason"] = "docker image is unavailable or inspect failed; no pull attempted"
                results.append(row)
                continue
            actual_digest = inspect["stdout_tail"].strip()
            row["actual_image_config_digest"] = actual_digest
            if actual_digest != expected_digest:
                row["reason"] = "local image digest differs from frozen benchmark"
                results.append(row)
                continue

            base_check = _call(
                [docker, "run", "--pull=never", "--rm", "--network", "none",
                 "--entrypoint", "bash", image, "-lc",
                 "git -C /testbed rev-parse HEAD; git -C /testbed rev-parse HEAD^{tree}"],
                45,
                runner,
            )
            row["base_check"] = base_check
            base_lines = base_check["stdout_tail"].splitlines()
            if base_check["exit_code"] != 0 or base_check["timed_out"] or len(base_lines) < 2:
                row["reason"] = "container base revision check failed"
                results.append(row)
                continue
            actual_commit, tree_sha = base_lines[-2:]
            row["actual_base_commit"] = actual_commit
            row["base_tree_sha"] = tree_sha
            if actual_commit != commit:
                row["reason"] = "container HEAD differs from frozen base commit"
                results.append(row)
                continue
            expected_tree = case.get("source_tree_sha")
            if expected_tree and tree_sha != expected_tree:
                row["reason"] = "container base tree differs from frozen source tree"
                results.append(row)
                continue

            mount = f"type=bind,source={visible_path.as_posix()},target=/testbed/{visible_relative},readonly"
            test_command = [
                docker, "run", "--pull=never", "--rm", "--network", "none",
                "--workdir", "/testbed", "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--mount", mount, "--entrypoint", case.get("docker_python", command[0]),
                image, *command[1:],
            ]
            redacted_command = list(test_command)
            mount_index = redacted_command.index("--mount") + 1
            redacted_command[mount_index] = (
                f"type=bind,source=[REDACTED_LOCAL_PATH],"
                f"target=/testbed/{visible_relative},readonly"
            )
            row["executed_command_redacted"] = redacted_command
            test = _call(test_command, float(case.get("test_timeout_seconds", 120)) + 20, runner)
            row["test"] = test
            if test["timed_out"] or test["exit_code"] in (None, 125, 126, 127):
                row["status"] = "blocked"
                row["reason"] = "Docker runtime failed or test timed out; test outcome is unknown"
            elif test["exit_code"] == 0:
                row["status"] = "unexpected_base_pass"
                row["reason"] = "frozen base passed a test expected to fail"
            elif case.get("baseline_expected_failure") is True:
                row["status"] = "expected_baseline_failure"
            else:
                row["status"] = "unexpected_baseline_failure"
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            row["reason"] = _safe_log(f"{type(exc).__name__}: {exc}", 500)
        results.append(row)

    blocked = sum(row["status"] == "blocked" for row in results)
    unexpected = sum(row["status"] in {"unexpected_base_pass", "unexpected_baseline_failure"} for row in results)
    return {
        "schema_version": 2,
        "run_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "subset_path": subset_path.name,
        "subset_sha256": _sha256(subset_path),
        "task_count": len(results),
        "expected_baseline_failure_count": sum(row["status"] == "expected_baseline_failure" for row in results),
        "blocked_count": blocked,
        "unexpected_count": unexpected,
        "model_calls": 0,
        "network_enabled": False,
        "agent_repair_attempted": False,
        "status": "blocked" if blocked else "completed_with_unexpected" if unexpected else "completed",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset", type=Path, default=DEFAULT_SUBSET)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--docker", default="docker")
    args = parser.parse_args()
    report = run_smoke(args.subset, args.cases, args.docker)
    output = args.output or ROOT / "reports" / f"cp2-base-smoke-{report['run_id']}.json"
    output = output.resolve()
    output.relative_to(ROOT.resolve())
    if output.exists():
        raise FileExistsError(f"refusing to overwrite smoke report: {output.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "run_id", "status", "task_count", "expected_baseline_failure_count", "blocked_count", "unexpected_count", "model_calls"
    )}, ensure_ascii=False))
    return 2 if report["blocked_count"] else 1 if report["unexpected_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
