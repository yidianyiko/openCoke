from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.domains.identity_access.models import IdentityAccessError


def create_auth_blueprint(identity_service) -> Blueprint:
    blueprint = Blueprint("auth", __name__, url_prefix="/api/auth")

    @blueprint.errorhandler(IdentityAccessError)
    def handle_identity_access_error(error: IdentityAccessError):
        body = {"error": {"code": error.code}}
        if error.fact is not None:
            body["error"]["fact"] = error.fact
        return jsonify(body), 400

    @blueprint.post("/register")
    def register():
        payload = request.get_json(silent=True) or {}
        result = identity_service.register_web_account(
            email=payload["email"],
            password_hash=payload["password_hash"],
            default_timezone=payload.get("default_timezone", "UTC"),
        )
        return (
            jsonify(
                {
                    "account_id": result.account.id,
                    "session_token": result.session.token,
                    "email_verification_artifact_id": result.email_verification.id,
                }
            ),
            201,
        )

    @blueprint.post("/login")
    def login():
        payload = request.get_json(silent=True) or {}
        result = identity_service.login(
            email=payload["email"],
            password_hash=payload["password_hash"],
        )
        return jsonify({"account_id": result.account.id, "session_token": result.session.token})

    @blueprint.post("/email-verification/verify")
    def verify_email():
        payload = request.get_json(silent=True) or {}
        credential = identity_service.verify_email(token=payload["token"])
        return jsonify({"account_id": credential.account_id, "email": credential.email})

    @blueprint.post("/password-reset/request")
    def request_password_reset():
        payload = request.get_json(silent=True) or {}
        identity_service.issue_password_reset(email=payload["email"])
        return jsonify({"accepted": True}), 202

    @blueprint.post("/password-reset/complete")
    def complete_password_reset():
        payload = request.get_json(silent=True) or {}
        credential = identity_service.reset_password(
            token=payload["token"],
            password_hash=payload["password_hash"],
        )
        return jsonify({"account_id": credential.account_id, "email": credential.email})

    @blueprint.get("/current-user")
    def current_user():
        session_token = _bearer_token()
        account = identity_service.current_user(session_token=session_token)
        return jsonify({"account_id": account.id, "origin": account.origin})

    @blueprint.get("/access-status")
    def access_status():
        account_id = request.args["account_id"]
        access = identity_service.get_access_status(account_id=account_id)
        return jsonify(
            {
                "account_id": access.account_id,
                "access_allowed": access.access_allowed,
                "denial_reason": access.denial_reason,
            }
        )

    @blueprint.post("/login-url/redeem")
    def redeem_login_url():
        payload = request.get_json(silent=True) or {}
        redeemed = identity_service.redeem_login_url(
            token=payload["token"],
            browser_session=payload["browser_session"],
        )
        return jsonify(
            {
                "account_id": redeemed.account_id,
                "session_token": redeemed.session.token,
                "continuation": redeemed.continuation,
            }
        )

    return blueprint


def _bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return ""
    return header[len(prefix) :]
