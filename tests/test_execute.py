import sys
import subprocess

from codepilot.tools.execute import build_docker_command, run_tests


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
    command = build_docker_command(
        tmp_path,
        [sys.executable, "-m", "pytest", "tests", "-q"],
        "codepilot-runner:0.1",
        "codepilot-test",
    )

    assert command[:2] == ["docker", "run"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--memory") + 1] == "512m"
    assert command[-6:] == [
        "codepilot-runner:0.1",
        "python",
        "-m",
        "pytest",
        "tests",
        "-q",
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

