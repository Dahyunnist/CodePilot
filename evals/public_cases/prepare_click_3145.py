"""Prepare pinned Click source and evaluator files for the public regression case."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


EXPECTED_TREE = "3c2036983ac4e0120b5946244f36351b4a276f34"
CASE_DIR = Path(__file__).parent / "click-3145"


def prepare(source: Path, output: Path) -> Path:
    source = source.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite: {output}")
    actual_tree = subprocess.run(
        ["git", "-c", f"safe.directory={source.as_posix()}", "write-tree"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual_tree != EXPECTED_TREE:
        raise ValueError(f"source tree mismatch: expected {EXPECTED_TREE}, got {actual_tree}")

    output.mkdir(parents=True)
    repo = output / "repo"
    shutil.copytree(
        source,
        repo,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc"),
    )
    shutil.copyfile(CASE_DIR / "visible_tests" / "test_issue_3145.py", repo / "tests" / "test_issue_3145.py")
    shutil.copytree(CASE_DIR / "hidden_tests", output / "hidden_tests")
    shutil.copyfile(CASE_DIR / "case.json", output / "case.json")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.source, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
