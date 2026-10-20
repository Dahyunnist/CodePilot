from __future__ import annotations

import flask.cli
from click.testing import CliRunner


def test_run_accepts_debug_and_enables_debugger_and_reloader(monkeypatch, tmp_path) -> None:
    app_file = tmp_path / "app.py"
    app_file.write_text("from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")
    calls = []

    def fake_run_simple(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(flask.cli, "run_simple", fake_run_simple)
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    result = CliRunner().invoke(flask.cli.cli, ["--app", str(app_file), "run", "--debug"])

    assert result.exit_code == 0, result.output
    assert calls
    assert calls[-1][1]["use_debugger"] is True
    assert calls[-1][1]["use_reloader"] is True


def test_run_debug_can_be_overridden(monkeypatch, tmp_path) -> None:
    app_file = tmp_path / "app.py"
    app_file.write_text("from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")
    calls = []

    def fake_run_simple(*args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(flask.cli, "run_simple", fake_run_simple)
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    result = CliRunner().invoke(
        flask.cli.cli,
        ["--app", str(app_file), "run", "--debug", "--no-debugger", "--no-reload"],
    )

    assert result.exit_code == 0, result.output
    assert calls[-1]["use_debugger"] is False
    assert calls[-1]["use_reloader"] is False
