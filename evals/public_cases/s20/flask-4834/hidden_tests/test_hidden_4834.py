from __future__ import annotations

from flask import Blueprint, Flask


def test_nested_blueprint_subdomains_are_chained_child_first() -> None:
    app = Flask(__name__, subdomain_matching=True)
    app.config["SERVER_NAME"] = "example.test"
    parent = Blueprint("parent", __name__)
    child = Blueprint("child", __name__, subdomain="v2")

    @child.get("/")
    def child_index() -> str:
        return "nested"

    parent.register_blueprint(child)
    app.register_blueprint(parent, subdomain="api")

    response = app.test_client().get(
        "/", base_url="http://v2.api.example.test"
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "nested"
