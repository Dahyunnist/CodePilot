from __future__ import annotations

from flask import Blueprint, Flask


def test_nested_blueprint_inherits_parent_subdomain() -> None:
    app = Flask(__name__, subdomain_matching=True)
    app.config["SERVER_NAME"] = "example.test"
    parent = Blueprint("parent", __name__)
    child = Blueprint("child", __name__)

    @child.get("/child/")
    def child_index() -> str:
        return "child"

    parent.register_blueprint(child)
    app.register_blueprint(parent, subdomain="api")

    response = app.test_client().get(
        "/child/", base_url="http://api.example.test"
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "child"
