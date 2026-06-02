from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.api.auth_helpers import require_customer_account_id
from coke.domains.identity_access.models import IdentityAccessError


def create_claim_blueprint(identity_service) -> Blueprint:
    blueprint = Blueprint("claim", __name__, url_prefix="/api/claim")

    @blueprint.errorhandler(IdentityAccessError)
    def handle_identity_access_error(error: IdentityAccessError):
        body = {"error": {"code": error.code}}
        if error.fact is not None:
            body["error"]["fact"] = error.fact
        return jsonify(body), _status_code(error.code)

    @blueprint.post("/code")
    def issue_claim_code():
        payload = _json_payload()
        result = identity_service.issue_web_claim_code(
            browser_session=_body_field(payload, "browser_session"),
            continuation=payload.get("continuation", {}),
        )
        return jsonify({"code": result.code, "artifact_id": result.artifact.id}), 201

    @blueprint.post("/email")
    def send_claim_email():
        payload = _json_payload()
        identity_service.send_claim_email(
            token=_body_field(payload, "entry_token"),
            email=_body_field(payload, "email"),
        )
        return jsonify({"accepted": True}), 202

    @blueprint.get("/code/<code>/status")
    def poll_claim_code(code: str):
        status = identity_service.get_claim_code_status(
            code=code,
            browser_session=_query_field("browser_session"),
        )
        if not status.found:
            return (
                jsonify(
                    {
                        "found": False,
                        "consumed": False,
                        "target_account_id": None,
                        "delivery_state": None,
                    }
                ),
                404,
            )
        return jsonify(
            {
                "found": True,
                "consumed": status.consumed,
                "target_account_id": status.target_account_id,
                "delivery_state": status.delivery_state,
            }
        )

    @blueprint.post("/code/redeem")
    def redeem_claim_code():
        payload = _json_payload()
        redeemed = identity_service.redeem_claim_code_from_channel(
            code=_body_field(payload, "code"),
            provider_type=_body_field(payload, "provider_type"),
            provider_subject=_body_field(payload, "provider_subject"),
        )
        return jsonify(
            {
                "account_id": redeemed.account_id,
                "continuation": redeemed.continuation,
            }
        )

    @blueprint.post("/code/complete")
    def complete_claim_code():
        payload = _json_payload()
        redeemed = identity_service.complete_web_claim_from_browser(
            code=_body_field(payload, "code"),
            browser_session=_body_field(payload, "browser_session"),
        )
        return jsonify(
            {
                "account_id": redeemed.account_id,
                "session_token": redeemed.session.token,
                "continuation": redeemed.continuation,
            }
        )

    @blueprint.post("/login-url/redeem")
    def redeem_login_url():
        payload = _json_payload()
        redeemed = identity_service.redeem_login_url(
            token=_body_field(payload, "token"),
            browser_session=_body_field(payload, "browser_session"),
        )
        return jsonify(
            {
                "account_id": redeemed.account_id,
                "session_token": redeemed.session.token,
                "continuation": redeemed.continuation,
            }
        )

    @blueprint.post("/pairing-code")
    def issue_pairing_code():
        account_id = require_customer_account_id(identity_service, IdentityAccessError)
        result = identity_service.issue_pairing_code(account_id=account_id)
        return jsonify({"code": result.code, "artifact_id": result.artifact.id}), 201

    @blueprint.post("/pairing-code/redeem")
    def redeem_pairing_code():
        payload = _json_payload()
        resolved = identity_service.resolve_or_create_channel_identity(
            provider_type=_body_field(payload, "provider_type"),
            provider_subject=_body_field(payload, "provider_subject"),
            pairing_code=_body_field(payload, "pairing_code"),
        )
        return jsonify(
            {
                "account_id": resolved.account.id,
                "channel_identity_id": resolved.channel_identity.id,
            }
        )

    return blueprint


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise IdentityAccessError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "reason": "json_body_required",
            },
        )
    return payload


def _body_field(payload: dict, field: str):
    if field not in payload:
        raise IdentityAccessError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    return payload[field]


def _query_field(field: str) -> str:
    value = request.args.get(field)
    if value is None:
        raise IdentityAccessError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    return value


def _status_code(code: str) -> int:
    return 401 if code == "unauthorized" else 400
