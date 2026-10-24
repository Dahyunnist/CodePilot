import hashlib
import io
import subprocess
import tarfile

import pytest

from evals.public_cases.prepare_swebench_lite import (
    VISIBLE_TESTS,
    _safe_extract_tar,
    _new_test_files,
    _scikit_learn_extensions_archive,
    _validate_record,
)


def _tar_bytes(name: str, data: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _tar_with_symlink(name: str, target: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:") as archive:
        info = tarfile.TarInfo("docs/target.png")
        info.size = 3
        archive.addfile(info, io.BytesIO(b"png"))
        link = tarfile.TarInfo(name)
        link.type = tarfile.SYMTYPE
        link.linkname = target
        archive.addfile(link)
    return buffer.getvalue()


def test_safe_archive_extraction_writes_regular_files(tmp_path):
    destination = tmp_path / "repo"
    _safe_extract_tar(_tar_bytes("src/module.py", b"VALUE = 1\n"), destination)
    assert (destination / "src/module.py").read_bytes() == b"VALUE = 1\n"


def test_safe_archive_extraction_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError, match="unsafe source path"):
        _safe_extract_tar(_tar_bytes("../outside.txt", b"x"), tmp_path / "repo")
    assert not (tmp_path / "outside.txt").exists()


def test_safe_archive_materializes_in_tree_file_symlinks_as_hard_links(tmp_path):
    destination = tmp_path / "repo"
    _safe_extract_tar(
        _tar_with_symlink("docs/theme/icon.png", "../target.png"), destination
    )
    target = destination / "docs/target.png"
    link = destination / "docs/theme/icon.png"
    assert link.read_bytes() == b"png"
    assert not link.is_symlink()
    link.write_bytes(b"new")
    assert target.read_bytes() == b"new"


def test_safe_archive_refuses_to_overwrite_existing_source(tmp_path):
    destination = tmp_path / "repo"
    destination.mkdir()
    (destination / "src.py").write_text("trusted", encoding="utf-8")

    with pytest.raises(ValueError, match="overwrites an existing path"):
        _safe_extract_tar(_tar_bytes("src.py", b"untrusted"), destination)

    assert (destination / "src.py").read_text(encoding="utf-8") == "trusted"


def test_safe_archive_rejects_symlink_that_escapes_source_tree(tmp_path):
    destination = tmp_path / "repo"
    with pytest.raises(ValueError, match="unsafe or unsupported source symlink"):
        _safe_extract_tar(_tar_with_symlink("docs/escape", "../../../outside"), destination)
    assert not (tmp_path / "outside").exists()


def test_record_validation_checks_hidden_and_gold_hashes_without_returning_gold():
    test_patch = (
        "diff --git a/testing/test_issue.py b/testing/test_issue.py\n"
        "--- a/testing/test_issue.py\n+++ b/testing/test_issue.py\n"
    )
    gold_patch = "diff --git a/src/module.py b/src/module.py\n"
    task = {
        "task_id": "repo-1",
        "base_commit": "a" * 40,
        "hidden_test_patch_sha256": hashlib.sha256(test_patch.encode()).hexdigest(),
        "gold_patch_sha256": hashlib.sha256(gold_patch.encode()).hexdigest(),
        "hidden_test_files": ["testing/test_issue.py"],
    }
    row = {"base_commit": "a" * 40, "test_patch": test_patch, "patch": gold_patch}
    recovered_test, paths = _validate_record(task, row)
    assert recovered_test == test_patch
    assert paths == task["hidden_test_files"]
    assert gold_patch not in recovered_test


def test_record_validation_rejects_changed_hidden_patch():
    task = {
        "task_id": "repo-1",
        "base_commit": "a" * 40,
        "hidden_test_patch_sha256": "0" * 64,
        "gold_patch_sha256": hashlib.sha256(b"").hexdigest(),
        "hidden_test_files": [],
    }
    with pytest.raises(ValueError, match="hidden test patch hash mismatch"):
        _validate_record(task, {"base_commit": "a" * 40, "patch": "", "test_patch": ""})


def test_new_test_files_only_accepts_explicit_git_additions():
    patch = (
        "diff --git a/tests/test_new.py b/tests/test_new.py\n"
        "--- /dev/null\n+++ b/tests/test_new.py\n"
        "@@ -0,0 +1 @@\n+def test_new(): pass\n"
        "diff --git a/tests/test_existing.py b/tests/test_existing.py\n"
        "--- a/tests/test_existing.py\n+++ b/tests/test_existing.py\n"
    )
    assert _new_test_files(patch) == {"tests/test_new.py"}


def test_scikit_learn_extension_export_is_limited_to_extension_files(monkeypatch):
    archive = _tar_bytes("sklearn/__check_build/_check_build.so", b"binary")

    def fake_run(command, **kwargs):
        assert command[:3] == ["docker", "run", "--rm"]
        assert "none" in command
        assert kwargs["shell"] is False
        return subprocess.CompletedProcess(command, 0, archive, b"")

    monkeypatch.setattr("evals.public_cases.prepare_swebench_lite.subprocess.run", fake_run)

    assert _scikit_learn_extensions_archive("trusted/image:tag") == archive


def test_scikit_learn_extension_export_rejects_non_extension_paths(monkeypatch):
    archive = _tar_bytes("untrusted/module.so", b"binary")
    monkeypatch.setattr(
        "evals.public_cases.prepare_swebench_lite.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, archive, b""),
    )

    with pytest.raises(ValueError, match="unsafe compiled extension entry"):
        _scikit_learn_extensions_archive("trusted/image:tag")


def test_issue_visible_test_is_derived_from_public_behavior_not_hidden_patch():
    path, source = VISIBLE_TESTS["pytest-dev__pytest-5221"]
    assert path.startswith("testing/benchmark_tests/")
    assert "testdir.runpytest(\"--fixtures\")" in source
    assert "cp2_visible_fixture" in source
    assert "test_patch" not in source
