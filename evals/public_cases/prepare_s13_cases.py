"""Verify pinned PyPI source archives and prepare isolated public cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath


CASE_FIXTURES = Path(__file__).parent / "s13"
ARCHIVES = {
    "flask-4834": ("Flask-2.2.2.tar.gz", "642c450d19c4ad482f96729bd2a8f6d32554aa1e231f4f6b4e7e5264b16cca2b"),
    "urllib3-3710": ("urllib3-2.5.0.tar.gz", "3fc47733c7e419d4bc3f6b3dc2b4f890bb743906a30d56ba4a5bfa4bbff92760"),
}


def verify_archive(path: Path, expected_sha256: str) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ValueError(f"source archive checksum mismatch: {path.name}")


def _safe_extract(
    archive: Path, destination: Path, excluded_paths: set[str] | None = None
) -> Path:
    excluded_paths = excluded_paths or set()
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        roots: set[str] = set()
        extracted: list[tarfile.TarInfo] = []
        for member in members:
            relative = PurePosixPath(member.name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in member.name
                or (relative.parts and ":" in relative.parts[0])
            ):
                raise ValueError(f"unsafe path in source archive: {member.name}")
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported entry in source archive: {member.name}")
            if relative.parts:
                roots.add(relative.parts[0])
                suffix = PurePosixPath(*relative.parts[1:]).as_posix()
                if suffix not in excluded_paths:
                    extracted.append(member)
        if len(roots) != 1:
            raise ValueError("source archive must contain exactly one root directory")
        bundle.extractall(destination, members=extracted)
        return destination / roots.pop()


def prepare(archives_root: Path, output_root: Path) -> Path:
    archives_root = archives_root.resolve(strict=True)
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite: {output_root}")

    verified: list[tuple[str, Path, Path, dict[str, object]]] = []
    for case_id, (archive_name, digest) in ARCHIVES.items():
        archive = archives_root / archive_name
        verify_archive(archive, digest)
        fixture = CASE_FIXTURES / case_id
        metadata = json.loads((fixture / "case.json").read_text(encoding="utf-8"))
        if metadata.get("archive_sha256") != digest:
            raise ValueError(f"case metadata checksum mismatch: {case_id}")
        verified.append((case_id, archive, fixture, metadata))

    output_root.mkdir(parents=True)
    for case_id, archive, fixture, metadata in verified:
        case_output = output_root / case_id
        case_output.mkdir()
        source_root = _safe_extract(
            archive,
            case_output / "source",
            set(metadata.get("source_exclusions", [])),
        )
        repo = case_output / "repo"
        shutil.move(str(source_root), str(repo))
        (case_output / "source").rmdir()
        (repo / "benchmark_tests").mkdir()
        for test in (fixture / "visible_tests").glob("*.py"):
            shutil.copyfile(test, repo / "benchmark_tests" / test.name)
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
