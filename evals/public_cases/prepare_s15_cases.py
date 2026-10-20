"""Prepare the frozen Requests S15 holdout from its verified PyPI archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from evals.public_cases.prepare_s13_cases import _safe_extract


CASE_ID = "requests-6628"
ARCHIVE = "requests-2.31.0.tar.gz"
SHA256 = "942c5a758f98d790eaed1a29cb6eeFC7FFB0D1CF7AF05C3D2791656DBD6AD1E1"
FIXTURE = Path(__file__).parent / "s15" / CASE_ID


def prepare(archives_root: Path, output_root: Path) -> Path:
    archives_root = archives_root.resolve(strict=True)
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite: {output_root}")

    archive = archives_root / ARCHIVE
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != SHA256.lower():
        raise ValueError(f"source archive checksum mismatch: {ARCHIVE}")
    metadata = json.loads((FIXTURE / "case.json").read_text(encoding="utf-8"))
    if metadata["archive_sha256"].lower() != SHA256.lower():
        raise ValueError("case metadata checksum mismatch")

    output_root.mkdir(parents=True)
    case_output = output_root / CASE_ID
    case_output.mkdir()
    source_root = _safe_extract(archive, case_output / "source")
    repo = case_output / "repo"
    shutil.move(str(source_root), str(repo))
    (case_output / "source").rmdir()
    benchmark_tests = repo / "benchmark_tests"
    benchmark_tests.mkdir()
    for test_file in (FIXTURE / "visible_tests").glob("*.py"):
        shutil.copyfile(test_file, benchmark_tests / test_file.name)
    shutil.copytree(FIXTURE / "hidden_tests", case_output / "hidden_tests")
    (case_output / "case.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
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
