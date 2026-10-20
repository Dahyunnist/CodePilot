from __future__ import annotations

from flask import Flask, render_template


def test_svg_template_escapes_untrusted_text(tmp_path) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "diagram.svg").write_text(
        "<svg><text>{{ title }}</text></svg>", encoding="utf-8"
    )
    app = Flask(__name__, template_folder=str(templates))

    with app.app_context():
        rendered = render_template("diagram.svg", title="R&D <team>")

    assert rendered == "<svg><text>R&amp;D &lt;team&gt;</text></svg>"
