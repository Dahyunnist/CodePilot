from __future__ import annotations

import ssl

from urllib3.util.ssl_ import create_urllib3_context


def test_sslkeylogfile_expands_environment_variable(tmp_path, monkeypatch) -> None:
    keylog_dir = tmp_path / "tls logs"
    keylog_dir.mkdir()
    monkeypatch.setenv("CODEPILOT_TLS_LOG_DIR", str(keylog_dir))
    monkeypatch.setenv("SSLKEYLOGFILE", "$CODEPILOT_TLS_LOG_DIR/session.keys")

    context = create_urllib3_context()

    assert isinstance(context, ssl.SSLContext)
    assert context.keylog_filename == str(keylog_dir / "session.keys")
    assert (keylog_dir / "session.keys").is_file()
