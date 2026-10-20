from flask import Blueprint, Flask


def make_app(child_subdomain=None):
    app = Flask(__name__)
    app.config["SERVER_NAME"] = "localhost:5000"
    parent = Blueprint("parent", __name__)
    child = Blueprint("child", __name__, subdomain=child_subdomain)

    @child.route("/child/")
    def child_index():
        return "child"

    parent.register_blueprint(child)
    app.register_blueprint(parent, subdomain="api")
    return app


def test_nested_blueprint_inherits_parent_subdomain():
    response = make_app().test_client().get(
        "/child/", base_url="http://api.localhost:5000"
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "child"


def test_explicit_child_subdomain_is_prefixed_before_parent():
    response = make_app("v2").test_client().get(
        "/child/", base_url="http://v2.api.localhost:5000"
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "child"
