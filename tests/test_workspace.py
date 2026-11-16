import os
import subprocess
from pathlib import Path

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


def test_workspace_uses_local_clone_without_hardlinks(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    (source / "app.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=source, check=True)

    real_run = subprocess.run
    clone_commands = []

    def record_clone(command, **kwargs):
        if command[:2] == ["git", "clone"]:
            clone_commands.append(command)
        return real_run(command, **kwargs)

    monkeypatch.setattr("codepilot.workspace.subprocess.run", record_clone)
    workspace = WorkspaceManager(tmp_path / "workspaces").prepare(
        source, "local-copy", require_clean_source=True
    )

    assert len(clone_commands) == 1
    assert "--local" in clone_commands[0]
    assert "--no-hardlinks" in clone_commands[0]
    source_objects = [
        path
        for path in (source / ".git" / "objects").rglob("*")
        if path.is_file() and len(path.parent.name) == 2 and len(path.name) == 38
    ]
    assert source_objects
    assert all(
        not os.path.samefile(
            path,
            workspace.path / ".git" / "objects" / path.parent.name / path.name,
        )
        for path in source_objects
    )
    assert not (workspace.path / ".git" / "objects" / "info" / "alternates").exists()
    assert subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=source, capture_output=True, text=True, check=True,
    ).stdout == ""


def test_workspace_rejects_source_head_change_during_local_clone(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    (source / "app.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=source, check=True)

    real_run = subprocess.run

    def change_source_after_clone(command, **kwargs):
        result = real_run(command, **kwargs)
        if command[:2] == ["git", "clone"] and result.returncode == 0:
            real_run(
                ["git", "commit", "--allow-empty", "-q", "-m", "concurrent update"],
                cwd=source, check=True,
            )
        return result

    monkeypatch.setattr("codepilot.workspace.subprocess.run", change_source_after_clone)
    manager = WorkspaceManager(tmp_path / "workspaces")

    with pytest.raises(WorkspaceError, match="source HEAD changed while preparing workspace"):
        manager.prepare(source, "source-race", require_clean_source=True)

    assert not (tmp_path / "workspaces" / "source-race").exists()


def test_workspace_excludes_untracked_private_oracle_sentinels(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    (source / "app.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=source, check=True)
    (source / "gold.patch").write_text("SENTINEL ONLY\n", encoding="utf-8")
    hidden = source / "hidden_tests"
    hidden.mkdir()
    (hidden / "test_private.py").write_text("SENTINEL ONLY\n", encoding="utf-8")

    workspace = WorkspaceManager(tmp_path / "workspaces").prepare(source, "run-private")

    assert (workspace.path / "app.py").is_file()
    assert not (workspace.path / "gold.patch").exists()
    assert not (workspace.path / "hidden_tests").exists()
    assert (source / "gold.patch").is_file()


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


def test_workspace_rejects_run_id_path_traversal(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)

    with pytest.raises(WorkspaceError, match="safe directory name"):
        WorkspaceManager(tmp_path / "workspaces").prepare(source, "../escape")


def test_workspace_removes_partial_clone_after_failure(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    (source / "app.py").write_text("pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=source, check=True)
    manager = WorkspaceManager(tmp_path / "workspaces")
    real_run = subprocess.run

    def fail_clone(command, **kwargs):
        if command[:2] == ["git", "clone"]:
            Path(command[-1]).mkdir(parents=True)
            return subprocess.CompletedProcess(command, 1, "", "clone failed")
        return real_run(command, **kwargs)

    monkeypatch.setattr("codepilot.workspace.subprocess.run", fail_clone)

    with pytest.raises(WorkspaceError, match="clone failed"):
        manager.prepare(source, "partial")

    assert not (tmp_path / "workspaces" / "partial").exists()


def test_workspace_rejects_tracked_secret_files(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    (source / ".env.production").write_text("TOKEN=secret\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", ".env.production"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "bad baseline"], cwd=source, check=True)

    with pytest.raises(WorkspaceError, match="tracks sensitive"):
        WorkspaceManager(tmp_path / "workspaces").prepare(source, "run")


def test_workspace_rejects_tracked_cloud_credentials(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    credentials = source / ".aws" / "credentials"
    credentials.parent.mkdir()
    credentials.write_text("aws_secret_access_key=FAKE_SENTINEL", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "credential fixture"], cwd=source, check=True)

    with pytest.raises(WorkspaceError, match="tracks sensitive"):
        WorkspaceManager(tmp_path / "workspaces").prepare(source, "run")
