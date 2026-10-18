import subprocess

import pytest

from codepilot.workspace import WorkspaceError, WorkspaceManager


def init_repo(path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.invalid"], cwd=path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "CodePilot Tests"], cwd=path, check=True
    )


def test_workspace_is_a_clean_clone_of_committed_state(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    file = source / "app.py"
    file.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=source, check=True)
    file.write_text("value = 2\n", encoding="utf-8")

    workspace = WorkspaceManager(tmp_path / "workspaces").prepare(source, "run-1")

    assert (workspace.path / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    (workspace.path / "app.py").write_text("value = 3\n", encoding="utf-8")
    assert file.read_text(encoding="utf-8") == "value = 2\n"


def test_workspace_rejects_duplicate_run_id(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    (source / "app.py").write_text("pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=source, check=True)
    manager = WorkspaceManager(tmp_path / "workspaces")
    manager.prepare(source, "same")

    with pytest.raises(WorkspaceError, match="already exists"):
        manager.prepare(source, "same")


def test_workspace_rejects_tracked_secret_files(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    (source / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", ".env"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "bad baseline"], cwd=source, check=True)

    with pytest.raises(WorkspaceError, match="tracks sensitive"):
        WorkspaceManager(tmp_path / "workspaces").prepare(source, "run")
