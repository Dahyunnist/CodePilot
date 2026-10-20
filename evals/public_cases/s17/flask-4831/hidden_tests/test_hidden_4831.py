from flask import Flask


def test_svg_is_added_without_changing_other_extension_defaults() -> None:
    app = Flask(__name__)

    assert app.select_jinja_autoescape("icon.svg") is True
    assert app.select_jinja_autoescape("page.html") is True
    assert app.select_jinja_autoescape("document.xml") is True
    assert app.select_jinja_autoescape("notes.txt") is False
