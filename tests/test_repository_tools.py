import subprocess

import pytest

from codepilot.tools.edit import PatchError, apply_patch, git_diff
from codepilot.tools.repo import PathPolicyError, list_files, read_file, search_code


def init_repo(path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.invalid"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CodePilot Tests"],
        cwd=path,
        check=True,
    )


def test_list_search_and_bounded_read(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        "def target():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")

    assert list_files(tmp_path) == "app.py"
    assert "app.py:1:def target" in search_code(tmp_path, "def target")
    assert search_code(tmp_path, "SECRET") == ""
    assert read_file(tmp_path, "app.py", 2, 2) == "2:     return 1"


def test_rejects_path_traversal_and_secrets(tmp_path) -> None:
    (tmp_path / "safe.py").write_text("safe = True", encoding="utf-8")

    with pytest.raises(PathPolicyError, match="escapes"):
        read_file(tmp_path, "../outside.py")
    with pytest.raises(PathPolicyError, match="sensitive"):
        read_file(tmp_path, ".env")
    with pytest.raises(FileNotFoundError):
        read_file(tmp_path, "missing.py")


def test_exact_patch_and_git_diff(tmp_path) -> None:
    init_repo(tmp_path)
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=tmp_path, check=True)

    assert apply_patch(tmp_path, "app.py", "value = 1", "value = 2") == "updated app.py"
    assert "-value = 1" in git_diff(tmp_path)
    assert "+value = 2" in git_diff(tmp_path)


def test_git_diff_hides_sensitive_files(tmp_path) -> None:
    init_repo(tmp_path)
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=old\n", encoding="utf-8")
    subprocess.run(["git", "add", ".env"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=tmp_path, check=True)
    secret.write_text("TOKEN=new\n", encoding="utf-8")

    assert git_diff(tmp_path) == ""


def test_patch_requires_one_exact_match(tmp_path) -> None:
    (tmp_path / "app.py").write_text("x = 1\nx = 1\n", encoding="utf-8")

    with pytest.raises(PatchError, match="found 2"):
        apply_patch(tmp_path, "app.py", "x = 1", "x = 2")

    with pytest.raises(PatchError, match="found 0"):
        apply_patch(tmp_path, "app.py", "missing context", "x = 2")

