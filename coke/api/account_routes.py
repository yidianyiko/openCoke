from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify

from coke.api.auth_helpers import require_customer_account
from coke.domains.identity_access.models import IdentityAccessError


def create_account_blueprint(identity_service) -> Blueprint:
    blueprint = Blueprint("account", __name__, url_prefix="/api/account")

    @blueprint.errorhandler(IdentityAccessError)
    def handle_identity_access_error(error: IdentityAccessError):
        return jsonify(_error_body(error.code, error.fact)), _status_code(error.code)

    @blueprint.get("/current-user")
    def current_user():
        account = require_customer_account(identity_service, IdentityAccessError)
        return jsonify(
            {
                "account_id": account.id,
                "origin": account.origin,
                "default_timezone": account.default_timezone,
                "lifecycle": account.lifecycle,
            }
        )

    @blueprint.get("/access-status")
    def access_status():
        account = require_customer_account(identity_service, IdentityAccessError)
        access = identity_service.get_access_status(account_id=account.id)
        return jsonify(_access_body(access))

    @blueprint.get("/activation")
    def activation():
        account = require_customer_account(identity_service, IdentityAccessError)
        activation = identity_service.get_activation(account_id=account.id)
        return jsonify(
            {
                "account_id": activation.account_id,
                "first_inbound_received_at": _iso(activation.first_inbound_received_at),
                "activation_completed_at": _iso(activation.activation_completed_at),
                "first_guidance_sent_at": _iso(activation.first_guidance_sent_at),
            }
        )

    return blueprint


def _access_body(access) -> dict:
    return {
        "account_id": access.account_id,
        "email_verification_state": access.email_verification_state,
        "subscription_state": access.subscription_state,
        "suspension_state": access.suspension_state,
        "access_allowed": access.access_allowed,
        "denial_reason": access.denial_reason,
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body


def _status_code(code: str) -> int:
    if code == "unauthorized":
        return 401
    if code in {"account_not_found", "access_not_found", "activation_not_found"}:
        return 404
    return 400
