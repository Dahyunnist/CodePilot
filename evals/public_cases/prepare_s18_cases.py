"""Prepare checksum-pinned S18 issue cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path
from pathlib import PurePosixPath

from evals.public_cases.prepare_s13_cases import _safe_extract


ROOT = Path(__file__).parent
CLICK_SHA256 = "f3999c7e787a93e159eb78a97db7a768a441509795a23f3a060bde24362ff38d"
FLASK_SHA256 = "642c450d19c4ad482f96729bd2a8f6d32554aa1e231f4f6b4e7e5264b16cca2b"


def _safe_extract_zip(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        roots: set[str] = set()
        members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for member in bundle.infolist():
            relative = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in member.filename
                or (relative.parts and ":" in relative.parts[0])
            ):
                raise ValueError(f"unsafe path in source archive: {member.filename}")
            if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"unsupported entry in source archive: {member.filename}")
            if relative.parts:
                roots.add(relative.parts[0])
                members.append((member, relative))
        if len(roots) != 1:
            raise ValueError("source archive must contain exactly one root directory")
        destination.mkdir(parents=True)
        for member, relative in members:
            target = destination.joinpath(*relative.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        return destination / roots.pop()


def _extract(archive: Path, destination: Path, exclusions: set[str]) -> Path:
    if zipfile.is_zipfile(archive):
        return _safe_extract_zip(archive, destination)
    from evals.public_cases.prepare_s13_cases import _safe_extract

    return _safe_extract(archive, destination, exclusions)


def prepare(click_archive: Path, flask_archives: Path, output_root: Path) -> Path:
    click_archive = click_archive.resolve(strict=True)
    flask_archive = (flask_archives.resolve(strict=True) / "Flask-2.2.2.tar.gz").resolve(
        strict=True
    )
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite: {output_root}")

    sources = {
        "click-3084": click_archive,
        "click-3121": click_archive,
        "flask-4777": flask_archive,
    }
    verified: list[tuple[str, Path, Path, dict[str, object]]] = []
    for case_id, archive in sources.items():
        fixture = ROOT / "s18" / case_id
        metadata = json.loads((fixture / "case.json").read_text(encoding="utf-8"))
        expected = metadata["archive_sha256"]
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"source archive checksum mismatch: {archive.name}")
        if metadata["case_id"] != case_id:
            raise ValueError(f"case ID mismatch: {case_id}")
        verified.append((case_id, archive, fixture, metadata))

    output_root.mkdir(parents=True)
    for case_id, archive, fixture, metadata in verified:
        case_output = output_root / case_id
        case_output.mkdir()
        source_root = _extract(
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
    parser.add_argument("--click-archive", type=Path, required=True)
    parser.add_argument("--flask-archives", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.click_archive, args.flask_archives, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
