import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from codepilot.cli import main
from codepilot.schemas import ChatMessage, ModelReply, ToolCall, ToolSpec


class RepairScriptModel:
    """Deterministic model substitute for the full repair workflow."""

    def __init__(self) -> None:
        self.replies = [
            ModelReply(
                tool_calls=[
                    ToolCall(
                        id="call-search",
                        name="search_code",
                        arguments={"query": "def parse_config", "path": "."},
                    )
                ]
            ),
            ModelReply(
                tool_calls=[
                    ToolCall(
                        id="call-read",
                        name="read_file",
                        arguments={"path": "config_parser.py", "reason": "Inspect the search match for the failing parser behavior."},
                    )
                ]
            ),
            ModelReply(
                tool_calls=[
                    ToolCall(id="call-test-fail", name="run_tests", arguments={})
                ]
            ),
            ModelReply(
                tool_calls=[
                    ToolCall(
                        id="call-patch",
                        name="apply_patch",
                        arguments={
                            "path": "config_parser.py",
                            "old_text": "if not line and text:\n            continue",
                            "new_text": "if not line:\n            continue",
                        },
                    )
                ]
            ),
            ModelReply(
                tool_calls=[
                    ToolCall(id="call-test-pass", name="run_tests", arguments={})
                ]
            ),
            ModelReply(
                tool_calls=[
                    ToolCall(id="call-diff", name="git_diff", arguments={})
                ]
            ),
            ModelReply(text="Fixed empty input handling and verified all tests."),
        ]

    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
    ) -> ModelReply:
        assert tools
        return self.replies.pop(0)


def make_demo_repo(tmp_path: Path) -> Path:
    source = (
        Path(__file__).parents[1]
        / "evals"
        / "cases"
        / "parse-config"
        / "repo"
    )
    repo = tmp_path / "demo-repo"
    shutil.copytree(
        source,
        repo,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CodePilot Tests"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "bug baseline"], cwd=repo, check=True)
    return repo


def test_cli_repairs_demo_repository(tmp_path, capsys) -> None:
    repo = make_demo_repo(tmp_path)

    exit_code = main(
        [
            "run",
            "--repo",
            str(repo),
            "--task",
            "parse_config crashes on empty input; fix it",
            "--test-command",
            "python -m pytest tests -q",
            "--max-steps",
            "8",
            "--execution",
            "host",
            "--approve-host-tests",
            "--workspace-root",
            str(tmp_path / "workspaces"),
            "--reports-root",
            str(tmp_path / "reports"),
        ],
        model_client=RepairScriptModel(),
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Status: success" in output
    assert "Steps: 7" in output
    assert "Tests: passed" in output
    assert "-        if not line and text:" in output
    assert "+        if not line:" in output
    workspace = next((tmp_path / "workspaces").iterdir())
    assert "if not line:\n" in (workspace / "config_parser.py").read_text(encoding="utf-8")
    assert "if not line and text:\n" in (repo / "config_parser.py").read_text(
        encoding="utf-8"
    )
    assert len(list((tmp_path / "reports" / "traces").glob("*.jsonl"))) == 1
    assert len(list((tmp_path / "reports" / "runs").glob("*.md"))) == 1
