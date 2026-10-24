"""Controlled project test execution without a shell."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from codepilot.schemas import ToolResult


class CommandPolicyError(RuntimeError):
    """Raised when a command is outside the supported test-runner policy."""


def normalize_test_command(command: list[str]) -> list[str]:
    """Normalize and validate supported pytest or Django test commands."""
    if not command:
        raise CommandPolicyError("test command must not be empty")

    normalized = list(command)
    if normalized[0].lower() in {"python", "python.exe"}:
        normalized[0] = sys.executable

    executable_name = Path(normalized[0]).name.lower()
    python_command = Path(normalized[0]).resolve() == Path(sys.executable).resolve()
    python_pytest = python_command and normalized[1:3] == ["-m", "pytest"]
    direct_pytest = executable_name in {"pytest", "pytest.exe", "py.test", "py.test.exe"}
    django_runner = (
        python_command
        and len(normalized) > 2
        and normalized[1] == "tests/runtests.py"
        and _valid_django_test_arguments(normalized[2:])
    )
    if not python_pytest and not direct_pytest and not django_runner:
        raise CommandPolicyError(
            "only pytest or the bounded Django tests/runtests.py command is allowed"
        )
    return normalized


def _valid_django_test_arguments(arguments: list[str]) -> bool:
    """Allow test labels and a small set of non-executable Django test options."""
    labels = 0
    index = 0
    while index < len(arguments):
        value = arguments[index]
        if value in {"--parallel", "--verbosity"}:
            index += 1
            if index >= len(arguments) or not arguments[index].isdigit():
                return False
            number = int(arguments[index])
            if value == "--parallel" and not 1 <= number <= 4:
                return False
            if value == "--verbosity" and not 0 <= number <= 3:
                return False
        elif value in {"--keepdb", "--noinput", "--shuffle"}:
            pass
        elif value.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
            return False
        else:
            labels += 1
        index += 1
    return labels > 0


def run_tests(
    repo_root: Path,
    command: list[str],
    timeout_seconds: float = 30,
    max_output_chars: int = 20_000,
    *,
    execution_mode: str = "host",
    docker_image: str = "codepilot-runner:0.1",
    docker_python: str = "python",
    additional_mounts: tuple[tuple[Path, str], ...] = (),
) -> ToolResult:
    """Run a validated project test command and normalize all outcomes."""
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

    container_name: str | None = None
    if execution_mode == "docker":
        container_name = f"codepilot-{uuid.uuid4().hex[:12]}"
        normalized = build_docker_command(
            repo_root,
            normalized,
            docker_image,
            container_name,
            docker_python=docker_python,
            additional_mounts=additional_mounts,
        )
    elif execution_mode != "host":
        return ToolResult(
            tool_name="run_tests",
            ok=False,
            stderr=f"unknown execution mode: {execution_mode}",
            duration_ms=_elapsed_ms(started),
            error_type="policy",
        )

    try:
        test_environment = _safe_environment()
        src_path = repo_root.resolve(strict=True) / "src"
        if src_path.is_dir():
            test_environment["PYTHONPATH"] = str(src_path)
        completed = subprocess.run(
            normalized,
            cwd=repo_root.resolve(strict=True),
            env=test_environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        if container_name:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    timeout=10,
                    check=False,
                    shell=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
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

    docker_error_output = (
        completed.stderr
        + completed.stdout
    ).lower()
    docker_connection_error = any(
        marker in docker_error_output
        for marker in (
            "permission denied while trying to connect to the docker api",
            "cannot connect to the docker daemon",
            "error during connect",
        )
    )
    docker_execution_error = execution_mode == "docker" and (
        completed.returncode == 125 or docker_connection_error
    )
    return ToolResult(
        tool_name="run_tests",
        ok=completed.returncode == 0,
        exit_code=completed.returncode,
        stdout=_truncate(completed.stdout, max_output_chars),
        stderr=_truncate(completed.stderr, max_output_chars),
        duration_ms=_elapsed_ms(started),
        error_type=(
            None
            if completed.returncode == 0
            else "execution"
            if docker_execution_error
            else "test_failure"
        ),
    )


def build_docker_command(
    repo_root: Path,
    normalized_command: list[str],
    image: str,
    container_name: str,
    *,
    docker_python: str = "python",
    additional_mounts: tuple[tuple[Path, str], ...] = (),
) -> list[str]:
    """Build a networkless, resource-limited Docker test command."""
    runner = _test_runner(normalized_command)
    root = repo_root.resolve(strict=True)
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "512m",
        "--cpus",
        "1",
        "--user",
        "10001:10001",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--mount",
        f"type=bind,source={root},target=/workspace,readonly",
    ]
    for source, target in additional_mounts:
        command.extend(
            [
                "--mount",
                f"type=bind,source={source.resolve(strict=True)},target={target},readonly",
            ]
        )
    if (root / "src").is_dir():
        command.extend(["--env", "PYTHONPATH=/workspace/src"])
    command.extend(["--workdir", "/workspace", image, docker_python])
    if runner == "pytest":
        command.extend(
            [
                "-m",
                "pytest",
                *_pytest_arguments(normalized_command),
                "-p",
                "no:cacheprovider",
                "--basetemp=/tmp/pytest-tmp",
            ]
        )
    else:
        command.extend(["tests/runtests.py", *normalized_command[2:]])
    return command


def _test_runner(command: list[str]) -> str:
    executable_name = Path(command[0]).name.lower()
    if (
        command[1:3] == ["-m", "pytest"]
        or executable_name in {"pytest", "pytest.exe", "py.test", "py.test.exe"}
    ):
        return "pytest"
    if len(command) > 2 and command[1] == "tests/runtests.py":
        return "django"
    raise CommandPolicyError("unsupported test runner")


def _pytest_arguments(command: list[str]) -> list[str]:
    executable_name = Path(command[0]).name.lower()
    if executable_name in {"pytest", "pytest.exe", "py.test", "py.test.exe"}:
        return command[1:]
    return command[3:]


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _safe_environment() -> dict[str, str]:
    """Keep process essentials while excluding API keys and arbitrary secrets."""
    allowed = {
        "COMSPEC",
        "DOCKER_CONFIG",
        "DOCKER_CONTEXT",
        "HOME",
        "LANG",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
    }
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in allowed
    }
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


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

