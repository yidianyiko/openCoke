from __future__ import annotations

from flask import Flask, jsonify

from coke.config import Settings


def create_app(
    settings: Settings,
    identity_access_service=None,
    channel_reachability_service=None,
    reminder_service=None,
    social_scheduling_service=None,
    calendar_import_service=None,
    settings_service=None,
    provider_adapters=None,
    composed_runtime=None,
    delivery_callback_service=None,
    reply_pubsub=None,
    internal_api_key: str | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["COKE_SETTINGS"] = settings
    app.config["APP_ENV"] = settings.app_env
    if internal_api_key is not None:
        app.config["COKE_INTERNAL_API_KEY"] = internal_api_key
    if composed_runtime is not None:
        app.config["COKE_RUNTIME"] = composed_runtime
        identity_access_service = (
            identity_access_service or composed_runtime.identity_access_service
        )
        channel_reachability_service = (
            channel_reachability_service
            or composed_runtime.channel_reachability_service
        )
        reminder_service = reminder_service or composed_runtime.reminder_service
        social_scheduling_service = (
            social_scheduling_service or composed_runtime.social_scheduling_service
        )
        calendar_import_service = (
            calendar_import_service or composed_runtime.calendar_import_service
        )
        settings_service = settings_service or getattr(
            composed_runtime,
            "settings_service",
            None,
        )
        provider_adapters = provider_adapters or getattr(
            composed_runtime,
            "provider_adapters",
            None,
        )
        delivery_callback_service = delivery_callback_service or getattr(
            composed_runtime,
            "delivery_callback_service",
            None,
        )
        reply_pubsub = reply_pubsub or getattr(composed_runtime, "reply_pubsub", None)
        _register_session_lifecycle(app, getattr(composed_runtime, "session", None))

    if identity_access_service is not None:
        from coke.api.account_routes import create_account_blueprint
        from coke.api.auth_routes import create_auth_blueprint
        from coke.api.claim_routes import create_claim_blueprint
        from coke.api.subscription_routes import create_subscription_blueprint

        app.register_blueprint(create_account_blueprint(identity_access_service))
        app.register_blueprint(create_auth_blueprint(identity_access_service))
        app.register_blueprint(create_claim_blueprint(identity_access_service))
        app.register_blueprint(create_subscription_blueprint(identity_access_service))

    if channel_reachability_service is not None:
        if identity_access_service is not None:
            from coke.api.channel_routes import create_channel_blueprint

            app.register_blueprint(
                create_channel_blueprint(
                    channel_reachability_service,
                    identity_access_service,
                )
            )
        if provider_adapters is not None:
            from coke.api.provider_webhooks import create_provider_webhook_blueprint

            app.register_blueprint(
                create_provider_webhook_blueprint(
                    channel_reachability_service,
                    provider_adapters,
                    conversation_runtime_service=(
                        composed_runtime.conversation_runtime_service
                        if composed_runtime is not None
                        else None
                    ),
                    reminder_service=reminder_service,
                    social_scheduling_service=social_scheduling_service,
                    commit_callback=(
                        composed_runtime.session.commit
                        if composed_runtime is not None
                        and composed_runtime.session is not None
                        else None
                    ),
                )
            )

    if reminder_service is not None and identity_access_service is not None:
        from coke.api.reminder_routes import create_reminder_blueprint

        app.register_blueprint(
            create_reminder_blueprint(reminder_service, identity_access_service)
        )

    if settings_service is not None and identity_access_service is not None:
        from coke.api.settings_routes import create_settings_blueprint

        app.register_blueprint(
            create_settings_blueprint(settings_service, identity_access_service)
        )

    if social_scheduling_service is not None and identity_access_service is not None:
        from coke.api.friend_routes import create_friend_blueprint
        from coke.api.shared_reminder_routes import create_shared_reminder_blueprint

        app.register_blueprint(
            create_friend_blueprint(social_scheduling_service, identity_access_service)
        )
        app.register_blueprint(
            create_shared_reminder_blueprint(
                social_scheduling_service,
                identity_access_service,
            )
        )

    if calendar_import_service is not None and identity_access_service is not None:
        from coke.api.calendar_import_routes import create_calendar_import_blueprint

        app.register_blueprint(
            create_calendar_import_blueprint(
                calendar_import_service,
                identity_access_service,
            )
        )

    if (
        delivery_callback_service is not None
        or reply_pubsub is not None
        or internal_api_key is not None
    ):
        from coke.api.internal_routes import create_internal_blueprint

        app.register_blueprint(
            create_internal_blueprint(
                delivery_callback_service=delivery_callback_service,
                reply_pubsub=reply_pubsub,
                internal_api_key=internal_api_key,
            )
        )

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app


def _register_session_lifecycle(app: Flask, session) -> None:
    if session is None:
        return

    @app.after_request
    def commit_or_rollback(response):
        if response.status_code < 400:
            session.commit()
        else:
            session.rollback()
        return response

    @app.teardown_request
    def rollback_on_exception(error):
        if error is not None:
            session.rollback()
