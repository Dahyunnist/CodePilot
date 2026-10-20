"""Prepare checksum-pinned S20 public issue cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from evals.public_cases.prepare_s13_cases import _safe_extract


FIXTURES = Path(__file__).parent / "s20"


def prepare(archives_root: Path, output_root: Path) -> Path:
    archives_root = archives_root.resolve(strict=True)
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite: {output_root}")

    verified: list[tuple[Path, Path, dict[str, object]]] = []
    for fixture in sorted(FIXTURES.iterdir()):
        if not fixture.is_dir():
            continue
        metadata = json.loads((fixture / "case.json").read_text(encoding="utf-8"))
        archive_name = "Flask-2.2.2.tar.gz" if metadata["case_id"].startswith("flask-") else "urllib3-2.5.0.tar.gz"
        archive = archives_root / archive_name
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != metadata["archive_sha256"]:
            raise ValueError(f"source archive checksum mismatch: {archive_name}")
        verified.append((archive, fixture, metadata))

    output_root.mkdir(parents=True)
    for archive, fixture, metadata in verified:
        case_id = str(metadata["case_id"])
        case_output = output_root / case_id
        case_output.mkdir()
        source_root = _safe_extract(
            archive,
            case_output / "source",
            set(metadata.get("source_exclusions", [])),
        )
        repo = case_output / "repo"
        shutil.copytree(source_root, repo)
        shutil.rmtree(case_output / "source")
        benchmark_tests = repo / "benchmark_tests"
        benchmark_tests.mkdir()
        for test_file in (fixture / "visible_tests").glob("*.py"):
            shutil.copyfile(test_file, benchmark_tests / test_file.name)
        shutil.copytree(fixture / "hidden_tests", case_output / "hidden_tests")
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
