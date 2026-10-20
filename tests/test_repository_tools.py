import os
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
    (tmp_path / ".env.local").write_text("SECRET=local-value", encoding="utf-8")
    (tmp_path / ".ENV.production").write_text("SECRET=uppercase-prod-value", encoding="utf-8")

    assert list_files(tmp_path) == "app.py"
    assert "app.py:1:def target" in search_code(tmp_path, "def target")
    assert search_code(tmp_path, "SECRET") == ""
    with pytest.raises(PathPolicyError, match="sensitive"):
        read_file(tmp_path, ".env.local")
    assert read_file(tmp_path, "app.py", 2, 2) == "2:     return 1"


def test_read_file_requires_reason_and_deduplicates_reads(tmp_path) -> None:
    from codepilot.tools.registry import ToolRegistry
    from codepilot.schemas import ToolCall

    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    tools = ToolRegistry(tmp_path, ["python", "-m", "pytest"])
    missing_reason = tools.execute(
        ToolCall(id="missing", name="read_file", arguments={"path": "app.py"})
    )
    first = tools.execute(
        ToolCall(id="first", name="read_file", arguments={"path": "app.py", "reason": "Search found target."})
    )
    duplicate = tools.execute(
        ToolCall(id="duplicate", name="read_file", arguments={"path": "app.py", "reason": "Read it again."})
    )
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")
    refreshed = tools.execute(
        ToolCall(id="refreshed", name="read_file", arguments={"path": "app.py", "reason": "Check the updated file."})
    )
    outside = tools.execute(
        ToolCall(id="outside", name="read_file", arguments={"path": "../outside.py", "reason": "Try an unrelated path."})
    )

    assert not missing_reason.ok
    assert first.ok and "value = 1" in first.stdout
    assert "来源：app.py" in first.stdout and "文件 SHA-256" in first.stdout
    assert duplicate.ok and "缓存命中" in duplicate.stdout
    assert "value = 1" not in duplicate.stdout
    assert "前次读取结果" in duplicate.stdout
    assert refreshed.ok and "value = 2" in refreshed.stdout and "缓存命中" not in refreshed.stdout
    assert not outside.ok and outside.error_type == "PathPolicyError"


def test_duplicate_search_returns_short_cache_observation(tmp_path) -> None:
    from codepilot.tools.registry import ToolRegistry
    from codepilot.schemas import ToolCall

    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    tools = ToolRegistry(tmp_path, ["python", "-m", "pytest"])

    first = tools.execute(
        ToolCall(id="first", name="search_code", arguments={"query": "value"})
    )
    duplicate = tools.execute(
        ToolCall(id="duplicate", name="search_code", arguments={"query": "value"})
    )

    assert first.ok and "app.py:1" in first.stdout
    assert duplicate.ok and "重复搜索" in duplicate.stdout
    assert "app.py:1" not in duplicate.stdout


def test_rejects_path_traversal_and_secrets(tmp_path) -> None:
    (tmp_path / "safe.py").write_text("safe = True", encoding="utf-8")

    with pytest.raises(PathPolicyError, match="escapes"):
        read_file(tmp_path, "../outside.py")
    with pytest.raises(PathPolicyError, match="sensitive"):
        read_file(tmp_path, ".env")
    with pytest.raises(PathPolicyError, match="sensitive"):
        read_file(tmp_path, ".ENV")
    with pytest.raises(PathPolicyError, match="sensitive"):
        read_file(tmp_path, ".ENV.production")
    with pytest.raises(PathPolicyError, match="internal"):
        read_file(tmp_path, ".GIT/config")
    with pytest.raises(FileNotFoundError):
        read_file(tmp_path, "missing.py")


def test_symlink_cannot_escape_repository(tmp_path) -> None:
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("outside secret", encoding="utf-8")
    link = tmp_path / "escape"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"symlink creation unavailable: {exc}")
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.skip(f"junction creation unavailable: {completed.stderr}")

    with pytest.raises(PathPolicyError, match="escapes"):
        read_file(tmp_path, "escape/secret.txt")


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
    local_secret = tmp_path / ".env.local"
    uppercase_secret = tmp_path / ".ENV.production"
    secret.write_text("TOKEN=old\n", encoding="utf-8")
    local_secret.write_text("TOKEN=old\n", encoding="utf-8")
    uppercase_secret.write_text("TOKEN=old\n", encoding="utf-8")
    subprocess.run(["git", "add", ".env"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-f", ".env.local"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-f", ".ENV.production"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=tmp_path, check=True)
    secret.write_text("TOKEN=new\n", encoding="utf-8")
    local_secret.write_text("TOKEN=new\n", encoding="utf-8")
    uppercase_secret.write_text("TOKEN=new\n", encoding="utf-8")

    assert git_diff(tmp_path) == ""


def test_patch_requires_one_exact_match(tmp_path) -> None:
    (tmp_path / "app.py").write_text("x = 1\nx = 1\n", encoding="utf-8")

    with pytest.raises(PatchError, match="found 2"):
        apply_patch(tmp_path, "app.py", "x = 1", "x = 2")

    with pytest.raises(PatchError, match="found 0"):
        apply_patch(tmp_path, "app.py", "missing context", "x = 2")

