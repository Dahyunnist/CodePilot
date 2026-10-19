import os
import shutil
import subprocess
import re
from collections.abc import Sequence
from pathlib import Path

from codepilot.cli import main
from codepilot.schemas import ChatMessage, ModelReply, ToolCall, ToolSpec


class RepairScriptModel:
    """Deterministic model substitute for the full repair workflow."""

    def __init__(self) -> None:
        self.requests: list[list[ChatMessage]] = []
        self.tool_definitions: list[tuple[ToolSpec, ...]] = []
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
            ModelReply(text="\u5df2\u4fee\u590d\u7a7a\u8f93\u5165\u5904\u7406\uff0c\u5e76\u901a\u8fc7\u5168\u90e8\u6d4b\u8bd5\u3002"),
        ]

    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
    ) -> ModelReply:
        assert tools
        self.requests.append(list(messages))
        self.tool_definitions.append(tuple(tools))
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

    model = RepairScriptModel()
    state_db = tmp_path / "reports" / "run-state.sqlite"
    exit_code = main(
        [
            "run",
            "--repo",
            str(repo),
            "--task",
            "\u4fee\u590d parse_config \u5904\u7406\u7a7a\u8f93\u5165\u65f6\u5d29\u6e83\u7684\u95ee\u9898\u3002",
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
        model_client=model,
    )

    assert "始终使用简体中文" in model.requests[0][0].content
    assert "请用简体中文" in model.requests[0][1].content
    assert model.requests[1][-1].content.startswith(
        "工具执行结果：在仓库文本中搜索指定字符串"
    )
    available_tools = {
        tool.function.name: tool.function for tool in model.tool_definitions[0]
    }
    assert "search_code" in available_tools
    assert "query" in available_tools["search_code"].parameters["properties"]
    assert "搜索" in available_tools["search_code"].description
    read_file_parameters = available_tools["read_file"].parameters
    assert "reason" in read_file_parameters["required"]
    assert "read_file" in available_tools
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "\u72b6\u6001\uff1a\u6210\u529f" in output
    assert "\u6a21\u578b\u6b65\u9aa4\uff1a7" in output
    assert "\u6d4b\u8bd5\uff1a\u901a\u8fc7" in output
    assert "-        if not line and text:" in output
    assert "+        if not line:" in output
    workspace = next((tmp_path / "workspaces").iterdir())
    assert "if not line:\n" in (workspace / "config_parser.py").read_text(encoding="utf-8")
    assert "if not line and text:\n" in (repo / "config_parser.py").read_text(
        encoding="utf-8"
    )
    assert len(list((tmp_path / "reports" / "traces").glob("*.jsonl"))) == 1
    assert len(list((tmp_path / "reports" / "runs").glob("*.md"))) == 1


def test_cli_can_apply_successful_patch_to_external_repository(tmp_path, capsys) -> None:
    repo = make_demo_repo(tmp_path)

    model = RepairScriptModel()
    state_db = tmp_path / "reports" / "run-state.sqlite"
    exit_code = main(
        [
            "run",
            "--repo",
            str(repo),
            "--task",
            "修复 parse_config 的空输入问题。",
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
            "--apply-to-repo",
            "--state-db",
            str(state_db),
        ],
        model_client=model,
    )

    assert exit_code == 3
    pending = capsys.readouterr().out
    match = re.search(r"运行 ID：([A-Za-z0-9_-]+)", pending)
    assert match
    run_id = match.group(1)
    assert "回写审批待处理" in pending
    assert "if not line and text:" in (repo / "config_parser.py").read_text(encoding="utf-8")

    exit_code = main(
        ["resume", "--run-id", run_id, "--approve", "--state-db", str(state_db), "--reports-root", str(tmp_path / "reports")]
    )
    assert exit_code == 0
    assert "回写状态：applied" in capsys.readouterr().out
    assert "if not line:\n" in (repo / "config_parser.py").read_text(encoding="utf-8")
    source_tests = subprocess.run(
        ["python", "-m", "pytest", "-p", "no:cacheprovider", "tests", "-q"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert source_tests.returncode == 0, source_tests.stdout + source_tests.stderr
    source_diff = subprocess.run(
        ["git", "diff", "--check"], cwd=repo, capture_output=True, text=True
    )
    assert source_diff.returncode == 0, source_diff.stderr
    changed = subprocess.run(
        ["git", "status", "--short"], cwd=repo, capture_output=True, text=True
    )
    assert changed.stdout.splitlines() == [" M config_parser.py"]

    duplicate = main(
        ["resume", "--run-id", run_id, "--approve", "--state-db", str(state_db)]
    )
    assert duplicate == 2
    assert "拒绝重复恢复" in capsys.readouterr().err


def test_cli_rejects_writeback_after_restart(tmp_path, capsys) -> None:
    repo = make_demo_repo(tmp_path)
    state_db = tmp_path / "reports" / "run-state.sqlite"
    exit_code = main(
        [
            "run", "--repo", str(repo), "--task", "修复 parse_config 空输入问题。",
            "--test-command", "python -m pytest tests -q", "--execution", "host",
            "--approve-host-tests", "--workspace-root", str(tmp_path / "workspaces"),
            "--reports-root", str(tmp_path / "reports"), "--apply-to-repo",
            "--state-db", str(state_db),
        ],
        model_client=RepairScriptModel(),
    )
    assert exit_code == 3
    match = re.search(r"运行 ID：([A-Za-z0-9_-]+)", capsys.readouterr().out)
    assert match

    rejected = main(
        ["resume", "--run-id", match.group(1), "--reject", "--state-db", str(state_db)]
    )
    assert rejected == 1
    assert "回写状态：rejected" in capsys.readouterr().out
    assert "if not line and text:\n" in (repo / "config_parser.py").read_text(encoding="utf-8")


def test_cli_invalidates_approval_if_patch_changes_while_paused(tmp_path, capsys) -> None:
    repo = make_demo_repo(tmp_path)
    state_db = tmp_path / "reports" / "run-state.sqlite"
    workspace_root = tmp_path / "workspaces"
    exit_code = main(
        [
            "run", "--repo", str(repo), "--task", "修复 parse_config 空输入问题。",
            "--test-command", "python -m pytest tests -q", "--execution", "host",
            "--approve-host-tests", "--workspace-root", str(workspace_root),
            "--reports-root", str(tmp_path / "reports"), "--apply-to-repo",
            "--state-db", str(state_db),
        ],
        model_client=RepairScriptModel(),
    )
    assert exit_code == 3
    match = re.search(r"运行 ID：([A-Za-z0-9_-]+)", capsys.readouterr().out)
    assert match
    (workspace_root / match.group(1) / "config_parser.py").write_text(
        "changed after approval pause\n", encoding="utf-8"
    )

    resumed = main(
        ["resume", "--run-id", match.group(1), "--approve", "--state-db", str(state_db)]
    )
    assert resumed == 1
    output = capsys.readouterr().out
    assert "回写状态：stale_patch" in output
    assert "旧测试和审批均作废" in output
    assert "if not line and text:\n" in (repo / "config_parser.py").read_text(encoding="utf-8")


def test_cli_refuses_to_apply_when_external_repository_is_dirty(tmp_path, capsys) -> None:
    repo = make_demo_repo(tmp_path)
    (repo / "local.py").write_text("uncommitted = True\n", encoding="utf-8")
    model = RepairScriptModel()

    exit_code = main(
        [
            "run",
            "--repo",
            str(repo),
            "--task",
            "修复 parse_config 的空输入问题。",
            "--test-command",
            "python -m pytest tests -q",
            "--apply-to-repo",
            "--workspace-root",
            str(tmp_path / "workspaces"),
            "--reports-root",
            str(tmp_path / "reports"),
        ],
        model_client=model,
    )

    assert exit_code == 2
    assert not model.requests
    assert (repo / "local.py").read_text(encoding="utf-8") == "uncommitted = True\n"
    assert "must be clean" in capsys.readouterr().err
