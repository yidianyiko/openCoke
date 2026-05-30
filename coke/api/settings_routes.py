from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.api.auth_helpers import require_customer_account_id
from coke.domains.settings.models import SettingsError

AGENT_SETTING_FIELDS = {
    "default_timezone",
    "assistant_name",
    "user_address_name",
    "persona",
    "background",
    "speaking_style",
    "extra_rules",
    "proactive_enabled",
    "memory_enabled",
}
PROFILE_FIELDS = {
    "real_name",
    "nickname",
    "description",
    "relationship_description",
}


def create_settings_blueprint(settings_service, identity_service) -> Blueprint:
    blueprint = Blueprint("settings", __name__, url_prefix="/api/settings")

    @blueprint.errorhandler(SettingsError)
    def handle_settings_error(error: SettingsError):
        return jsonify(_error_body(error.code, error.fact)), _status_code(error.code)

    @blueprint.get("")
    def view_settings():
        result = settings_service.view_settings(_customer_account_id(identity_service))
        return jsonify(_settings_body(result))

    @blueprint.patch("")
    def update_settings():
        account_id = _customer_account_id(identity_service)
        payload = _json_payload()
        result = settings_service.update_settings(
            account_id,
            **_selected_fields(payload, AGENT_SETTING_FIELDS),
        )
        return jsonify(_settings_body(result))

    @blueprint.patch("/profile")
    def update_profile():
        account_id = _customer_account_id(identity_service)
        payload = _json_payload()
        result = settings_service.update_profile(
            account_id,
            **_selected_fields(payload, PROFILE_FIELDS),
        )
        return jsonify(_settings_body(result))

    @blueprint.post("/reset")
    def reset_agent_settings():
        result = settings_service.reset_agent_settings(
            _customer_account_id(identity_service)
        )
        return jsonify(_settings_body(result))

    return blueprint


def _customer_account_id(identity_service) -> str:
    return require_customer_account_id(identity_service, SettingsError)


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise SettingsError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "reason": "json_object_required",
            },
        )
    return payload


def _selected_fields(payload: dict, allowed: set[str]) -> dict:
    return {field: payload[field] for field in allowed if field in payload}


def _settings_body(view) -> dict:
    settings = view.agent_settings
    profile = view.user_profile
    return {
        "account_id": view.account_id,
        "default_timezone": view.default_timezone,
        "agent_settings": {
            "assistant_name": settings.assistant_name,
            "user_address_name": settings.user_address_name,
            "persona": settings.persona,
            "background": settings.background,
            "speaking_style": settings.speaking_style,
            "extra_rules": settings.extra_rules,
            "proactive_enabled": settings.proactive_enabled,
            "memory_enabled": settings.memory_enabled,
        },
        "user_profile": {
            "real_name": profile.real_name,
            "nickname": profile.nickname,
            "description": profile.description,
            "relationship_description": profile.relationship_description,
        },
    }


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body


def _status_code(code: str) -> int:
    if code == "unauthorized":
        return 401
    if code == "account_not_found":
        return 404
    return 400
