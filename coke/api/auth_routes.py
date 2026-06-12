from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.api.auth_helpers import require_customer_account
from coke.domains.identity_access.models import IdentityAccessError


def create_auth_blueprint(identity_service) -> Blueprint:
    blueprint = Blueprint("auth", __name__, url_prefix="/api/auth")

    @blueprint.errorhandler(IdentityAccessError)
    def handle_identity_access_error(error: IdentityAccessError):
        body = {"error": {"code": error.code}}
        if error.fact is not None:
            body["error"]["fact"] = error.fact
        return jsonify(body), _status_code(error.code)

    @blueprint.post("/register")
    def register():
        payload = _json_payload()
        result = identity_service.register_web_account(
            email=_body_field(payload, "email"),
            password=_body_field(payload, "password"),
            display_name=_body_field(payload, "display_name"),
            default_timezone=payload.get("default_timezone", "UTC"),
        )
        body = {
            "account_id": result.account.id,
            "session_token": result.session.token,
        }
        if result.email_verification is not None:
            body["email_verification_artifact_id"] = result.email_verification.id
        return (jsonify(body), 201)

    @blueprint.post("/login")
    def login():
        payload = _json_payload()
        result = identity_service.login(
            email=_body_field(payload, "email"),
            password=_body_field(payload, "password"),
        )
        return jsonify(
            {"account_id": result.account.id, "session_token": result.session.token}
        )

    @blueprint.post("/email-verification/verify")
    def verify_email():
        payload = _json_payload()
        result = identity_service.verify_email_and_create_session(
            token=_body_field(payload, "token")
        )
        return jsonify(
            {
                "account_id": result.account_id,
                "email": result.email,
                "session_token": result.session.token,
            }
        )

    @blueprint.post("/email-verification/resend")
    def resend_email_verification():
        payload = _json_payload()
        try:
            identity_service.resend_email_verification(
                email=_body_field(payload, "email")
            )
        except IdentityAccessError as error:
            if error.code != "unknown_email":
                raise
        return jsonify({"accepted": True}), 202

    @blueprint.post("/password-reset/request")
    def request_password_reset():
        payload = _json_payload()
        identity_service.issue_password_reset(email=_body_field(payload, "email"))
        return jsonify({"accepted": True}), 202

    @blueprint.post("/password-reset/complete")
    def complete_password_reset():
        payload = _json_payload()
        credential = identity_service.reset_password(
            token=_body_field(payload, "token"),
            password=_body_field(payload, "password"),
        )
        return jsonify({"account_id": credential.account_id, "email": credential.email})

    @blueprint.get("/current-user")
    def current_user():
        account = require_customer_account(identity_service, IdentityAccessError)
        return jsonify({"account_id": account.id, "origin": account.origin})

    @blueprint.get("/access-status")
    def access_status():
        account = require_customer_account(identity_service, IdentityAccessError)
        access = identity_service.get_access_status(account_id=account.id)
        return jsonify(
            {
                "account_id": access.account_id,
                "access_allowed": access.access_allowed,
                "denial_reason": access.denial_reason,
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
