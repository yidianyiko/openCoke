from __future__ import annotations

from flask import request

from coke.domains.identity_access.models import IdentityAccessError


def require_customer_account(identity_service, route_error_type) -> object:
    try:
        return identity_service.current_user(
            session_token=_required_bearer_token(route_error_type)
        )
    except IdentityAccessError as error:
        raise map_identity_error(error, route_error_type) from error


def require_customer_account_id(identity_service, route_error_type) -> str:
    account = require_customer_account(identity_service, route_error_type)
    return account.id


def _required_bearer_token(route_error_type) -> str:
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        raise _unauthorized_error(route_error_type, "missing_bearer_token")
    token = header[len(prefix) :]
    if token.strip() == "" or token != token.strip():
        raise _unauthorized_error(route_error_type, "missing_bearer_token")
    return token


def _unauthorized_error(route_error_type, reason: str):
    return route_error_type(
        "unauthorized",
        fact={
            "type": "unauthorized",
            "reason": reason,
        },
    )


def map_identity_error(error: IdentityAccessError, route_error_type):
    if error.code == "invalid_session":
        return _unauthorized_error(route_error_type, "invalid_session")
    return route_error_type(error.code, fact=error.fact)
