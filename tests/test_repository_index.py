import subprocess
from pathlib import Path

from codepilot.tools.registry import ToolRegistry
from codepilot.schemas import ToolCall


def make_registry(root: Path) -> ToolRegistry:
    return ToolRegistry(root, ["python", "-m", "pytest"], execution_mode="host", host_tests_approved=True)


def test_project_instructions_follow_directory_ancestry_and_include_hashes(tmp_path: Path) -> None:
    package = tmp_path / "payments"
    package.mkdir()
    (tmp_path / "AGENTS.md").write_text("全仓库规则。", encoding="utf-8")
    (package / "AGENTS.md").write_text("支付模块使用 Decimal。", encoding="utf-8")
    (package / "pricing.py").write_text("def total():\n    return 0\n", encoding="utf-8")
    tools = make_registry(tmp_path)

    result = tools.execute(
        ToolCall(
            id="instructions",
            name="read_project_instructions",
            arguments={"path": "payments/pricing.py"},
        )
    )

    assert result.ok
    assert "全仓库规则。" in result.stdout
    assert "支付模块使用 Decimal。" in result.stdout
    assert result.stdout.count("SHA-256:") == 2


def test_ast_index_searches_symbols_calls_and_invalidates_on_edits(tmp_path: Path) -> None:
    package = tmp_path / "billing"
    package.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    source = package / "pricing.py"
    source.write_text(
        "def calculate_total():\n    return round_amount()\n\ndef round_amount():\n    return 1\n",
        encoding="utf-8",
    )
    (tests / "test_pricing.py").write_text(
        "from billing.pricing import calculate_total\n\ndef test_total():\n    assert calculate_total() == 1\n",
        encoding="utf-8",
    )
    tools = make_registry(tmp_path)

    overview = tools.execute(ToolCall(id="map", name="project_map", arguments={}))
    symbols = tools.execute(
        ToolCall(id="symbols", name="search_symbols", arguments={"query": "calculate_total"})
    )
    refs = tools.execute(
        ToolCall(id="refs", name="find_references", arguments={"symbol": "calculate_total"})
    )
    before = next(line for line in overview.stdout.splitlines() if "内容版本" in line)

    assert overview.ok and "3 个类/函数" in overview.stdout
    assert "billing.pricing.calculate_total" in symbols.stdout
    assert "文件 SHA-256" in symbols.stdout
    assert "tests.test_pricing.test_total -> calculate_total" in refs.stdout
    assert "test_pricing.py" in refs.stdout

    source.write_text(source.read_text(encoding="utf-8").replace("round_amount", "round_money"), encoding="utf-8")
    after = tools.execute(ToolCall(id="map-after", name="project_map", arguments={}))
    assert before not in after.stdout


def test_selected_tests_are_suggested_and_run_without_final_acceptance(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "index@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Index Test"], cwd=tmp_path, check=True)
    source = tmp_path / "app.py"
    source.write_text("def value():\n    return 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    test_file = tests / "test_app.py"
    test_file.write_text("from app import value\n\ndef test_value():\n    assert value() == 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=tmp_path, check=True)
    source.write_text("def value():\n    return 1 + 0\n", encoding="utf-8")
    tools = make_registry(tmp_path)

    suggestion = tools.execute(ToolCall(id="suggest", name="suggest_tests", arguments={}))
    targeted = tools.execute(
        ToolCall(
            id="targeted",
            name="run_selected_tests",
            arguments={"paths": ["tests/test_app.py"]},
        )
    )
    rejected = tools.execute(
        ToolCall(
            id="outside",
            name="run_selected_tests",
            arguments={"paths": ["../outside/test_other.py"]},
        )
    )

    assert suggestion.ok and "tests/test_app.py" in suggestion.stdout
    assert targeted.ok and "1 passed" in targeted.stdout
    assert not rejected.ok and rejected.error_type == "PathPolicyError"
