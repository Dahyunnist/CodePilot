import io
import tarfile

import pytest

from evals.public_cases.prepare_s13_cases import _safe_extract, verify_archive


def test_archive_checksum_rejects_modified_source(tmp_path):
    archive = tmp_path / "source.tar.gz"
    archive.write_bytes(b"modified")

    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_archive(archive, "0" * 64)


def test_source_archive_rejects_parent_path(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        data = b"unsafe"
        info = tarfile.TarInfo("../outside.txt")
        info.size = len(data)
        bundle.addfile(info, io.BytesIO(data))

    with pytest.raises(ValueError, match="unsafe path"):
        _safe_extract(archive, tmp_path / "unpacked")


def test_source_archive_excludes_listed_fixture(tmp_path):
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        root = tarfile.TarInfo("Flask-2.2.2/")
        root.type = tarfile.DIRTYPE
        bundle.addfile(root)
        for name, data in (
            ("Flask-2.2.2/src/flask.py", b"source"),
            ("Flask-2.2.2/tests/test_apps/.env", b"fixture"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))

    root = _safe_extract(
        archive, tmp_path / "unpacked", {"tests/test_apps/.env"}
    )

    assert (root / "src/flask.py").is_file()
    assert not (root / "tests/test_apps/.env").exists()
