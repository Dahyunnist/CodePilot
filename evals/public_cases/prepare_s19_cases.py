"""Prepare checksum-pinned S19 Requests issue cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from evals.public_cases.prepare_s13_cases import _safe_extract


CASE_ID = "requests-6628"
ARCHIVE = "requests-2.31.0.tar.gz"
SHA256 = "942c5a758f98d790eaed1a29cb6eefc7ffb0d1cf7af05c3d2791656dbd6ad1e1"
FIXTURE = Path(__file__).parent / "s19" / CASE_ID


def prepare(archives_root: Path, output_root: Path) -> Path:
    archives_root = archives_root.resolve(strict=True)
    archive = (archives_root / ARCHIVE).resolve(strict=True)
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite: {output_root}")
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != SHA256:
        raise ValueError(f"source archive checksum mismatch: {ARCHIVE}")
    metadata = json.loads((FIXTURE / "case.json").read_text(encoding="utf-8"))
    if metadata.get("archive_sha256") != SHA256:
        raise ValueError("case metadata checksum mismatch")

    output_root.mkdir(parents=True)
    case_output = output_root / CASE_ID
    case_output.mkdir()
    source_root = _safe_extract(archive, case_output / "source")
    repo = case_output / "repo"
    shutil.copytree(source_root, repo)
    shutil.rmtree(case_output / "source")
    benchmark_tests = repo / "benchmark_tests"
    benchmark_tests.mkdir()
    for test_file in (FIXTURE / "visible_tests").glob("*.py"):
        shutil.copyfile(test_file, benchmark_tests / test_file.name)
    shutil.copytree(FIXTURE / "hidden_tests", case_output / "hidden_tests")
    (case_output / "case.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.archives, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
