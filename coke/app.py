from __future__ import annotations

from flask import Flask, jsonify

from coke.config import Settings


def create_app(
    settings: Settings,
    identity_access_service=None,
    channel_reachability_service=None,
    social_scheduling_service=None,
    provider_adapters=None,
) -> Flask:
    app = Flask(__name__)
    app.config["COKE_SETTINGS"] = settings
    app.config["APP_ENV"] = settings.app_env

    if identity_access_service is not None:
        from coke.api.auth_routes import create_auth_blueprint
        from coke.api.claim_routes import create_claim_blueprint

        app.register_blueprint(create_auth_blueprint(identity_access_service))
        app.register_blueprint(create_claim_blueprint(identity_access_service))

    if channel_reachability_service is not None:
        from coke.api.channel_routes import create_channel_blueprint

        app.register_blueprint(create_channel_blueprint(channel_reachability_service))
        if provider_adapters is not None:
            from coke.api.provider_webhooks import create_provider_webhook_blueprint

            app.register_blueprint(
                create_provider_webhook_blueprint(
                    channel_reachability_service,
                    provider_adapters,
                )
            )

    if social_scheduling_service is not None:
        from coke.api.friend_routes import create_friend_blueprint
        from coke.api.shared_reminder_routes import create_shared_reminder_blueprint

        app.register_blueprint(create_friend_blueprint(social_scheduling_service))
        app.register_blueprint(
            create_shared_reminder_blueprint(social_scheduling_service)
        )

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app
