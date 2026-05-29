from __future__ import annotations

from flask import Flask, jsonify

from coke.config import Settings


def create_app(settings: Settings) -> Flask:
    app = Flask(__name__)
    app.config["COKE_SETTINGS"] = settings
    app.config["APP_ENV"] = settings.app_env

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app
