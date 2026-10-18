"""Controlled pytest execution without a shell."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from codepilot.schemas import ToolResult


class CommandPolicyError(RuntimeError):
    """Raised when a command is outside the pytest-only policy."""


def normalize_test_command(command: list[str]) -> list[str]:
    """Map a portable Python command to the active interpreter and validate it."""
    if not command:
        raise CommandPolicyError("test command must not be empty")

    normalized = list(command)
    if normalized[0].lower() in {"python", "python.exe"}:
        normalized[0] = sys.executable

    executable_name = Path(normalized[0]).name.lower()
    python_pytest = (
        Path(normalized[0]).resolve() == Path(sys.executable).resolve()
        and normalized[1:3] == ["-m", "pytest"]
    )
    direct_pytest = executable_name in {"pytest", "pytest.exe", "py.test", "py.test.exe"}
    if not python_pytest and not direct_pytest:
        raise CommandPolicyError("only pytest commands are allowed")
    return normalized


def run_tests(
    repo_root: Path,
    command: list[str],
    timeout_seconds: float = 30,
    max_output_chars: int = 20_000,
) -> ToolResult:
    """Run a validated pytest command and normalize all outcomes."""
    started = time.perf_counter()
    try:
        normalized = normalize_test_command(command)
    except CommandPolicyError as exc:
        return ToolResult(
            tool_name="run_tests",
            ok=False,
            stderr=str(exc),
            duration_ms=_elapsed_ms(started),
            error_type="policy",
        )

    try:
        completed = subprocess.run(
            normalized,
            cwd=repo_root.resolve(strict=True),
            env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return ToolResult(
            tool_name="run_tests",
            ok=False,
            stdout=_truncate(_as_text(exc.stdout), max_output_chars),
            stderr=_truncate(_as_text(exc.stderr), max_output_chars),
            duration_ms=_elapsed_ms(started),
            error_type="timeout",
        )
    except OSError as exc:
        return ToolResult(
            tool_name="run_tests",
            ok=False,
            stderr=str(exc),
            duration_ms=_elapsed_ms(started),
            error_type="execution",
        )

    return ToolResult(
        tool_name="run_tests",
        ok=completed.returncode == 0,
        exit_code=completed.returncode,
        stdout=_truncate(completed.stdout, max_output_chars),
        stderr=_truncate(completed.stderr, max_output_chars),
        duration_ms=_elapsed_ms(started),
        error_type=None if completed.returncode == 0 else "test_failure",
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... output truncated"

