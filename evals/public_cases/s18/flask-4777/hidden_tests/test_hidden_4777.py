from __future__ import annotations

import flask.cli
from click.testing import CliRunner


def test_run_debug_keeps_existing_global_debug_option(monkeypatch, tmp_path) -> None:
    app_file = tmp_path / "app.py"
    app_file.write_text("from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(flask.cli, "run_simple", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.delenv("FLASK_DEBUG", raising=False)

    result = CliRunner().invoke(flask.cli.cli, ["--app", str(app_file), "--debug", "run"])

    assert result.exit_code == 0, result.output
    assert calls[-1]["use_debugger"] is True
    assert calls[-1]["use_reloader"] is True
