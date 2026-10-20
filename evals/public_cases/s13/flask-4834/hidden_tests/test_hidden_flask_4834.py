from flask import Blueprint, Flask


def test_subdomains_chain_through_multiple_nested_blueprints():
    app = Flask(__name__)
    app.config["SERVER_NAME"] = "localhost:5000"
    root = Blueprint("root", __name__)
    middle = Blueprint("middle", __name__, subdomain="v2")
    leaf = Blueprint("leaf", __name__, subdomain="admin")

    @leaf.get("/health")
    def health():
        return "ok"

    middle.register_blueprint(leaf)
    root.register_blueprint(middle)
    app.register_blueprint(root, subdomain="api")

    response = app.test_client().get(
        "/health", base_url="http://admin.v2.api.localhost:5000"
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "ok"
