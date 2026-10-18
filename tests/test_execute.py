from codepilot.tools.execute import run_tests


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

