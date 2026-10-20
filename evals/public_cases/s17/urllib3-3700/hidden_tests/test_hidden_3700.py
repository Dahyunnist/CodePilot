from __future__ import annotations

from urllib3.util.ssl_ import create_urllib3_context


def test_unset_sslkeylogfile_leaves_context_without_key_log(monkeypatch) -> None:
    monkeypatch.delenv("SSLKEYLOGFILE", raising=False)

    context = create_urllib3_context()

    assert context.keylog_filename is None
