"""Run the seven scripted CLI writeback E2E cases in a disposable temp root."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "test_cli_can_apply_successful_patch_to_external_repository",
    "test_cli_missing_checkpoint_does_not_emit_checkpoint_resume",
    "test_cli_rejects_writeback_after_restart",
    "test_cli_invalidates_approval_if_patch_changes_while_paused",
    "test_cli_refuses_to_apply_when_external_repository_is_dirty",
    "test_cli_revalidates_tests_after_writeback_approval_resume",
    "test_cli_rejects_writeback_when_review_diff_is_truncated",
)
NODE_IDS = tuple(f"tests/test_cli_e2e.py::{name}" for name in TESTS)


def _failure_class(text: str) -> str:
    if "NtCreateDirectoryObject" in text or "0xC0000022" in text:
        return "host_acl_blocked"
    if "PermissionError" in text or "Access is denied" in text:
        return "host_acl_blocked"
    return "test_failure"


def run() -> int:
    with tempfile.TemporaryDirectory(prefix="codepilot-cp3-e2e-") as temp:
        temp_root = Path(temp).resolve(strict=True)
        base = temp_root / "pytest"
        xml_path = temp_root / "results.xml"
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        command = [
            sys.executable, "-m", "pytest", "-q", "-v", "--tb=short",
            f"--basetemp={base}", f"--junitxml={xml_path}", *NODE_IDS,
        ]
        try:
            result = subprocess.run(
                command, cwd=ROOT, env=env, capture_output=True, text=True,
                errors="replace", timeout=600, check=False,
            )
        except subprocess.TimeoutExpired:
            print(json.dumps({
                "exit_code": None,
                "temporary_workspace_only": True,
                "model_calls": 0,
                "tests": [{"test": name, "status": "timeout_or_blocked"} for name in TESTS],
                "stdout_or_stderr": "redacted; not emitted",
            }, ensure_ascii=False, indent=2))
            return 124
        cases: list[dict[str, str]] = []
        if xml_path.is_file():
            root = ET.parse(xml_path).getroot()
            for case in root.iter("testcase"):
                outcome = "passed"
                failure = case.find("failure")
                if failure is None:
                    failure = case.find("error")
                if failure is not None:
                    details = (
                        failure.attrib.get("message", "")
                        + (failure.text or "")
                        + result.stdout
                        + result.stderr
                    )
                    outcome = _failure_class(details)
                skipped = case.find("skipped")
                if skipped is not None:
                    outcome = "skipped"
                cases.append({"test": case.attrib.get("name", "unknown"), "status": outcome})
        if not cases:
            cases = [{"test": name, "status": "blocked_no_junit"} for name in TESTS]
        summary = {
            "exit_code": result.returncode,
            "temporary_workspace_only": True,
            "model_calls": 0,
            "tests": cases,
            "stdout_or_stderr": "redacted; not emitted",
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(run())
