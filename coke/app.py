from __future__ import annotations

from flask import Flask, jsonify

from coke.config import Settings


def create_app(settings: Settings, identity_access_service=None) -> Flask:
    app = Flask(__name__)
    app.config["COKE_SETTINGS"] = settings
    app.config["APP_ENV"] = settings.app_env

    if identity_access_service is not None:
        from coke.api.auth_routes import create_auth_blueprint
        from coke.api.claim_routes import create_claim_blueprint

        app.register_blueprint(create_auth_blueprint(identity_access_service))
        app.register_blueprint(create_claim_blueprint(identity_access_service))

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app
