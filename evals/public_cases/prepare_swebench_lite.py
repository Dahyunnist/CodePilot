"""Materialize frozen SWE-bench tasks from pinned official Docker images."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from evals.live_runner import _directory_sha256


VISIBLE_TEST_FILTERS = {
    # Fallback: the unmodified legacy fixtures module is slow; select issue-adjacent tests.
    "pytest-dev__pytest-5221": ["-k", "show"],
}
VISIBLE_TESTS = {
    "pytest-dev__pytest-5221": (
        "testing/benchmark_tests/test_fixture_scope_visible.py",
        """def test_fixtures_cli_reports_declared_scope(testdir):
    testdir.makeconftest(\"\"\"
import pytest

@pytest.fixture(scope=\"session\")
def cp2_visible_fixture():
    return \"ready\"
\"\"\")
    result = testdir.runpytest(\"--fixtures\")
    result.stdout.fnmatch_lines([\"*cp2_visible_fixture*\"])
    fixture_line = next(
        line for line in result.stdout.lines
        if \"cp2_visible_fixture\" in line
    )
    assert \"session\" in fixture_line
""",
    )
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _task_rows(raw: Any) -> dict[str, dict[str, Any]]:
    rows = raw if isinstance(raw, list) else raw.get("rows", [])
    if rows and isinstance(rows[0], dict) and "row" in rows[0]:
        rows = [item["row"] for item in rows]
    return {str(row["instance_id"]): row for row in rows}


def _safe_extract_tar(archive_bytes: bytes, destination: Path) -> None:
    """Extract regular files and safe in-tree file symlinks; reject other entries."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        members = archive.getmembers()
        regular_files = {
            member.name: member for member in members if member.isfile()
        }
        deferred_links = []
        for member in members:
            relative = PurePosixPath(member.name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in member.name
                or (relative.parts and ":" in relative.parts[0])
            ):
                raise ValueError(f"unsafe source path in Docker archive: {member.name}")
            if member.isdir():
                destination.joinpath(*relative.parts).mkdir(parents=True, exist_ok=True)
                continue
            if member.issym():
                link = PurePosixPath(member.linkname)
                target_name = posixpath.normpath(
                    posixpath.join(relative.parent.as_posix(), member.linkname)
                )
                if (
                    link.is_absolute()
                    or "\\" in member.linkname
                    or (link.parts and ":" in link.parts[0])
                    or target_name == ".."
                    or target_name.startswith("../")
                    or target_name not in regular_files
                ):
                    raise ValueError(f"unsafe or unsupported source symlink: {member.name}")
                deferred_links.append((relative, target_name))
                continue
            if not member.isfile():
                raise ValueError(f"unsupported source entry in Docker archive: {member.name}")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise ValueError(f"source archive overwrites an existing path: {member.name}")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"missing source payload in Docker archive: {member.name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
        for relative, target_name in deferred_links:
            target = destination.joinpath(*PurePosixPath(target_name).parts)
            link_path = destination.joinpath(*relative.parts)
            link_path.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or target.is_symlink():
                raise ValueError(f"source symlink target is not a regular file: {target_name}")
            try:
                os.link(target, link_path)
            except OSError as exc:
                raise RuntimeError(
                    f"cannot materialize safe source symlink as a hard link: {relative.as_posix()}"
                ) from exc


def _source_archive(image: str, base_commit: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", base_commit):
        raise ValueError("base commit must be a full Git SHA")
    result = subprocess.run(
        [
            "docker", "run", "--rm", "--network", "none", "--entrypoint", "bash",
            image, "-lc", f"git -C /testbed archive --format=tar {base_commit}",
        ],
        capture_output=True,
        check=False,
        shell=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"cannot export {base_commit} from {image}: "
            f"{result.stderr.decode('utf-8', errors='replace')[:600]}"
        )
    if not result.stdout:
        raise RuntimeError(f"Docker returned an empty source archive for {image}")
    return result.stdout


def _pytest_version_file(image: str) -> bytes | None:
    """Retrieve the setup-generated version metadata omitted by git archive."""
    result = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "--entrypoint", "cat",
         image, "/testbed/src/_pytest/_version.py"],
        capture_output=True,
        check=False,
        shell=False,
    )
    if result.returncode:
        return None
    return result.stdout


def _scikit_learn_extensions_archive(image: str) -> bytes:
    """Restore compiled extensions generated inside the pinned test image."""
    command = (
        "cd /testbed && find sklearn -type f -name '*.so' -print0 "
        "| tar --null -T - -cf -"
    )
    result = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "--entrypoint", "bash",
         image, "-lc", command],
        capture_output=True,
        check=False,
        shell=False,
        timeout=180,
    )
    if result.returncode or not result.stdout:
        raise RuntimeError(
            "cannot export compiled scikit-learn extensions from pinned image: "
            + result.stderr.decode("utf-8", errors="replace")[:600]
        )
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        members = archive.getmembers()
        if not members:
            raise ValueError("compiled extension archive is empty")
        for member in members:
            relative = PurePosixPath(member.name)
            if (
                not member.isfile()
                or relative.is_absolute()
                or ".." in relative.parts
                or "\\" in member.name
                or not relative.parts
                or relative.parts[0] != "sklearn"
                or relative.suffix != ".so"
            ):
                raise ValueError(f"unsafe compiled extension entry: {member.name}")
    return result.stdout


def _validate_record(task: dict[str, Any], row: dict[str, Any]) -> tuple[str, list[str]]:
    task_id = task["task_id"]
    if str(row.get("base_commit")) != task["base_commit"]:
        raise ValueError(f"base commit mismatch: {task_id}")
    if _sha256(str(row.get("patch") or "").encode()) != task["gold_patch_sha256"]:
        raise ValueError(f"gold patch hash mismatch: {task_id}")
    test_patch = str(row.get("test_patch") or "")
    if _sha256(test_patch.encode()) != task["hidden_test_patch_sha256"]:
        raise ValueError(f"hidden test patch hash mismatch: {task_id}")
    test_paths = [
        line.split(" b/", 1)[0].removeprefix("diff --git a/")
        for line in test_patch.splitlines()
        if line.startswith("diff --git a/")
    ]
    if test_paths != task["hidden_test_files"]:
        raise ValueError(f"hidden test path mismatch: {task_id}")
    return test_patch, test_paths


def _new_test_files(test_patch: str) -> set[str]:
    """Return test paths explicitly added by the hidden test patch."""
    added = set()
    old_path = None
    for line in test_patch.splitlines():
        if line.startswith("--- "):
            old_path = line[4:]
        elif line.startswith("+++ b/") and old_path == "/dev/null":
            added.add(line[6:])
    return added


def prepare(
    dataset_path: Path,
    manifest_path: Path,
    output_root: Path,
    task_ids: set[str] | None = None,
) -> list[dict[str, str]]:
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite materialized tasks: {output_root}")
    dataset_bytes = dataset_path.read_bytes()
    if _sha256(dataset_bytes) != json.loads(manifest_path.read_text(encoding="utf-8"))["dataset_source_sha256"]:
        raise ValueError("raw dataset does not match the frozen selection manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = _task_rows(json.loads(dataset_bytes.decode("utf-8-sig")))
    selected = [task for task in manifest["tasks"] if task_ids is None or task["task_id"] in task_ids]
    if task_ids and {task["task_id"] for task in selected} != task_ids:
        raise ValueError("requested task IDs are missing from the frozen manifest")
    if not selected:
        raise ValueError("no SWE-bench tasks selected")

    output_root.mkdir(parents=True)
    prepared: list[dict[str, str]] = []
    for task in selected:
        task_id = task["task_id"]
        if task_id not in rows:
            raise ValueError(f"raw dataset is missing task: {task_id}")
        test_patch, test_paths = _validate_record(task, rows[task_id])
        image = task["docker_image"]
        case_root = output_root / task_id
        repo = case_root / "repo"
        case_root.mkdir()
        archive = _source_archive(image, task["base_commit"])
        _safe_extract_tar(archive, repo)
        generated_version = None
        if task["repo"] == "pytest-dev/pytest":
            generated_version = _pytest_version_file(image)
            if generated_version:
                version_path = repo / "src" / "_pytest" / "_version.py"
                version_path.parent.mkdir(parents=True, exist_ok=True)
                version_path.write_bytes(generated_version)
        compiled_extensions = None
        if task["repo"] == "scikit-learn/scikit-learn":
            compiled_extensions = _scikit_learn_extensions_archive(image)
            _safe_extract_tar(compiled_extensions, repo)
        allowed_new_files = _new_test_files(test_patch)
        if not allowed_new_files.issubset(test_paths):
            raise ValueError(f"hidden test patch adds an unexpected path ({task_id})")
        missing = [
            path for path in test_paths
            if path not in allowed_new_files and not (repo / path).is_file()
        ]
        if missing:
            raise ValueError(f"test patch target is absent at base commit ({task_id}): {missing}")

        visible_test_sha256 = None
        visible_test = VISIBLE_TESTS.get(task_id)
        if visible_test:
            visible_path, visible_source = visible_test
            visible_file = repo / visible_path
            visible_file.parent.mkdir(parents=True, exist_ok=True)
            visible_file.write_bytes(visible_source.encode("utf-8"))
            visible_test_sha256 = _sha256(visible_source.encode("utf-8"))

        hidden_patch_path = case_root / "hidden_tests.patch"
        hidden_patch_path.write_bytes(test_patch.encode("utf-8"))
        test_nodes = list(dict.fromkeys(
            list(rows[task_id].get("FAIL_TO_PASS", []))
            + list(rows[task_id].get("PASS_TO_PASS", []))
        ))
        visible_command = (
            ["python", "-m", "pytest", visible_test[0], "-q"]
            if visible_test
            else [
                "python", "-m", "pytest", *test_paths,
                *VISIBLE_TEST_FILTERS.get(task_id, []), "-q",
            ]
        )
        metadata = {
            "case_id": task_id,
            "category": "swe-bench-lite-public-repair",
            "instruction": task["problem_statement"],
            "test_command": visible_command,
            "search_query": task["problem_statement"].splitlines()[0][:160],
            "patches": [],
            "source_url": f"https://github.com/{task['repo']}",
            "source_release": f"SWE-bench Lite base {task['base_commit']}",
            "source_commit": task["base_commit"],
            "source_tree_sha": _directory_sha256(repo),
            "issue_url": task["issue_url"],
            "pull_request_url": task["pull_request_url"],
            "archive_sha256": _sha256(archive),
            "hidden_test_patch": hidden_patch_path.name,
            "hidden_test_command": ["python", "-m", "pytest", *test_nodes, "-q"],
            "docker_image": image,
            "baseline_expected_failure": False,
            "test_timeout_seconds": 120,
            "docker_python": "/opt/miniconda3/envs/testbed/bin/python",
            "generated_version_sha256": _sha256(generated_version) if generated_version else None,
            "compiled_extensions_sha256": (
                _sha256(compiled_extensions) if compiled_extensions else None
            ),
            "visible_test_sha256": visible_test_sha256,
        }
        (case_root / "case.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        prepared.append({"task_id": task_id, "source_tree_sha": metadata["source_tree_sha"]})
        print(f"已物化 {task_id}；隐藏测试不在 Agent 工作副本中")
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("evals/public_cases/cp2/frozen-selection.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-ids", nargs="*")
    args = parser.parse_args()
    prepare(args.dataset, args.manifest, args.output, set(args.task_ids) if args.task_ids else None)
    print(f"已物化 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
