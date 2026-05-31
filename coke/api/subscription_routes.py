from __future__ import annotations

from flask import Blueprint, jsonify

from coke.api.auth_helpers import require_customer_account
from coke.domains.identity_access.models import IdentityAccessError


def create_subscription_blueprint(identity_service) -> Blueprint:
    blueprint = Blueprint("subscription", __name__, url_prefix="/api/subscription")

    @blueprint.errorhandler(IdentityAccessError)
    def handle_identity_access_error(error: IdentityAccessError):
        return jsonify(_error_body(error.code, error.fact)), _status_code(error.code)

    @blueprint.get("/status")
    def status():
        account = require_customer_account(identity_service, IdentityAccessError)
        access = identity_service.get_access_status(account_id=account.id)
        checkout_url = _checkout_url(identity_service, account.id)
        return jsonify(
            {
                "account_id": access.account_id,
                "subscription_state": access.subscription_state,
                "access_allowed": access.access_allowed,
                "denial_reason": access.denial_reason,
                "checkout_url": checkout_url,
            }
        )

    @blueprint.post("/checkout-link")
    def checkout_link():
        account = require_customer_account(identity_service, IdentityAccessError)
        decision = identity_service.check_access_for_inbound(account_id=account.id)
        checkout_url = _checkout_url_from_decision(decision)
        return jsonify(
            {
                "account_id": account.id,
                "available": checkout_url is not None,
                "checkout_url": checkout_url,
                "denial_reason": decision.denial_reason,
            }
        )

    return blueprint


def _checkout_url(identity_service, account_id: str) -> str | None:
    decision = identity_service.check_access_for_inbound(account_id=account_id)
    return _checkout_url_from_decision(decision)


def _checkout_url_from_decision(decision) -> str | None:
    fact = getattr(decision, "fact", None)
    if not isinstance(fact, dict):
        return None
    checkout_url = fact.get("checkout_url")
    return checkout_url if isinstance(checkout_url, str) and checkout_url else None


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body


def _status_code(code: str) -> int:
    if code == "unauthorized":
        return 401
    if code in {"account_not_found", "access_not_found"}:
        return 404
    return 400
