import sys
import subprocess

import pytest

from codepilot.tools.execute import (
    CommandPolicyError,
    _safe_environment,
    build_docker_command,
    normalize_test_command,
    run_tests,
)


def test_run_tests_reports_success(tmp_path) -> None:
    (tmp_path / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )

    result = run_tests(tmp_path, ["python", "-m", "pytest", "-q"])

    assert result.ok is True
    assert result.exit_code == 0


def test_run_tests_reports_failure(tmp_path) -> None:
    (tmp_path / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )

    result = run_tests(tmp_path, ["python", "-m", "pytest", "-q"])

    assert result.ok is False
    assert result.exit_code == 1
    assert result.error_type == "test_failure"


def test_run_tests_reports_timeout(tmp_path) -> None:
    (tmp_path / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(1)\n",
        encoding="utf-8",
    )

    result = run_tests(
        tmp_path,
        ["python", "-m", "pytest", "-q"],
        timeout_seconds=0.1,
    )

    assert result.ok is False
    assert result.error_type == "timeout"


def test_run_tests_rejects_other_commands(tmp_path) -> None:
    result = run_tests(tmp_path, ["python", "-c", "print('unsafe')"])

    assert result.ok is False
    assert result.error_type == "policy"


def test_normalize_test_command_accepts_bounded_django_runner() -> None:
    command = normalize_test_command(
        ["python", "tests/runtests.py", "cache.tests", "--parallel", "2"]
    )

    assert command == [
        sys.executable,
        "tests/runtests.py",
        "cache.tests",
        "--parallel",
        "2",
    ]


@pytest.mark.parametrize(
    "command",
    [
        ["python", "tests/runtests.py", "../outside"],
        ["python", "tests/runtests.py", "cache.tests", "--parallel", "999"],
        ["python", "tests/runtests.py", "cache.tests", "--settings", "evil"],
        ["python", "-c", "print('unsafe')"],
    ],
)
def test_normalize_test_command_rejects_unbounded_django_or_python_commands(command) -> None:
    with pytest.raises(CommandPolicyError):
        normalize_test_command(command)


def test_run_tests_truncates_large_output(tmp_path) -> None:
    (tmp_path / "test_output.py").write_text(
        "def test_output():\n    print('x' * 500)\n    assert False\n",
        encoding="utf-8",
    )

    result = run_tests(
        tmp_path,
        ["python", "-m", "pytest", "-q", "-s"],
        max_output_chars=100,
    )

    assert result.ok is False
    assert result.stdout.endswith("... output truncated")


def test_docker_command_has_isolation_and_resource_limits(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    command = build_docker_command(
        tmp_path,
        [sys.executable, "-m", "pytest", "tests", "-q"],
        "codepilot-runner:0.1",
        "codepilot-test",
    )

    assert command[:2] == ["docker", "run"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    workspace_mount = command[command.index("--mount") + 1]
    assert workspace_mount.endswith(",target=/workspace,readonly")
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--memory") + 1] == "512m"
    assert "PYTHONPATH=/workspace/src" in command
    assert command[-9:] == [
        "codepilot-runner:0.1",
        "python",
        "-m",
        "pytest",
        "tests",
        "-q",
        "-p",
        "no:cacheprovider",
        "--basetemp=/tmp/pytest-tmp",
    ]


def test_docker_command_can_select_image_specific_python(tmp_path) -> None:
    command = build_docker_command(
        tmp_path,
        [sys.executable, "-m", "pytest", "tests", "-q"],
        "swebench/test:latest",
        "codepilot-testbed",
        docker_python="/opt/miniconda3/envs/testbed/bin/python",
    )
    assert command[-9:] == [
        "swebench/test:latest",
        "/opt/miniconda3/envs/testbed/bin/python",
        "-m",
        "pytest",
        "tests",
        "-q",
        "-p",
        "no:cacheprovider",
        "--basetemp=/tmp/pytest-tmp",
    ]


def test_docker_command_runs_bounded_django_runner_inside_same_sandbox(tmp_path) -> None:
    command = build_docker_command(
        tmp_path,
        [sys.executable, "tests/runtests.py", "cache.tests"],
        "swebench/django:test",
        "codepilot-django-test",
        docker_python="/opt/miniconda3/envs/testbed/bin/python",
    )

    assert command[:2] == ["docker", "run"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[-4:] == [
        "swebench/django:test",
        "/opt/miniconda3/envs/testbed/bin/python",
        "tests/runtests.py",
        "cache.tests",
    ]


def test_docker_daemon_permission_error_is_not_a_test_failure(tmp_path, monkeypatch) -> None:
    error = "permission denied while trying to connect to the docker API"
    monkeypatch.setattr(
        "codepilot.tools.execute.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", error),
    )

    result = run_tests(
        tmp_path,
        ["python", "-m", "pytest", "-q"],
        execution_mode="docker",
    )

    assert result.ok is False
    assert result.error_type == "execution"


def test_docker_timeout_survives_failed_container_cleanup(tmp_path, monkeypatch) -> None:
    calls = 0

    def timed_out(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise subprocess.TimeoutExpired(args[0], 0.1, output="partial")
        raise subprocess.TimeoutExpired(args[0], 10)

    monkeypatch.setattr("codepilot.tools.execute.subprocess.run", timed_out)

    result = run_tests(
        tmp_path,
        ["python", "-m", "pytest", "-q"],
        timeout_seconds=0.1,
        execution_mode="docker",
    )

    assert result.ok is False
    assert result.error_type == "timeout"
    assert calls == 2


def test_missing_docker_executable_is_execution_error(tmp_path, monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("docker executable missing")

    monkeypatch.setattr("codepilot.tools.execute.subprocess.run", unavailable)

    result = run_tests(
        tmp_path, ["python", "-m", "pytest"], execution_mode="docker"
    )

    assert result.ok is False
    assert result.error_type == "execution"


def test_host_tests_do_not_receive_model_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "must-not-reach-tests")
    (tmp_path / "test_env.py").write_text(
        "import os\n\ndef test_no_key():\n    assert 'LLM_API_KEY' not in os.environ\n",
        encoding="utf-8",
    )

    result = run_tests(tmp_path, ["python", "-m", "pytest", "-q"])

    assert result.ok is True


def test_safe_environment_preserves_docker_config_but_drops_api_keys(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    monkeypatch.setenv("DOCKER_CONTEXT", "desktop-linux")
    monkeypatch.setenv("LLM_API_KEY", "must-not-reach-tests")

    environment = _safe_environment()

    assert environment["DOCKER_CONFIG"] == str(tmp_path)
    assert environment["DOCKER_CONTEXT"] == "desktop-linux"
    assert "LLM_API_KEY" not in environment


def test_src_layout_is_importable_without_inheriting_host_pythonpath(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "must-not-reach-tests")
    package = tmp_path / "src"
    package.mkdir()
    (package / "sample_package.py").write_text("VALUE = 42\n", encoding="utf-8")
    (tmp_path / "test_src_layout.py").write_text(
        "from sample_package import VALUE\n\ndef test_value():\n    assert VALUE == 42\n",
        encoding="utf-8",
    )

    result = run_tests(tmp_path, ["python", "-m", "pytest", "-q"])

    assert result.ok is True

