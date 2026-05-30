from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.api.auth_helpers import require_customer_account_id
from coke.domains.social_scheduling.models import SocialSchedulingError


def create_friend_blueprint(social_scheduling_service, identity_service) -> Blueprint:
    blueprint = Blueprint("friends", __name__, url_prefix="/api/friends")

    @blueprint.errorhandler(SocialSchedulingError)
    def handle_social_scheduling_error(error: SocialSchedulingError):
        return jsonify(_error_body(error.code, error.fact)), _status_code(error.code)

    @blueprint.get("/link")
    def get_friend_link():
        link = social_scheduling_service.get_or_create_friend_link(
            owner_account_id=_customer_account_id(identity_service)
        )
        return jsonify(_friend_link_body(link))

    @blueprint.post("/link/reset")
    def reset_friend_link():
        link = social_scheduling_service.reset_friend_link(
            owner_account_id=_customer_account_id(identity_service)
        )
        return jsonify(_friend_link_body(link))

    @blueprint.post("/link/disable")
    def disable_friend_link():
        link = social_scheduling_service.disable_friend_link(
            owner_account_id=_customer_account_id(identity_service)
        )
        return jsonify(_friend_link_body(link))

    @blueprint.post("/join")
    def join_friend_link():
        joiner_account_id = _customer_account_id(identity_service)
        payload = _json_payload()
        public_token = payload.get("public_token")
        link_code = payload.get("link_code")
        if (
            isinstance(public_token, str)
            and public_token.strip() == public_token
            and public_token
        ):
            result = social_scheduling_service.establish_friendship_from_token(
                joiner_account_id=joiner_account_id,
                public_token=public_token,
            )
        elif (
            isinstance(link_code, str) and link_code.strip() == link_code and link_code
        ):
            result = social_scheduling_service.establish_friendship_from_code(
                joiner_account_id=joiner_account_id,
                link_code=link_code,
            )
        else:
            raise SocialSchedulingError(
                "invalid_request",
                fact={
                    "type": "invalid_request",
                    "location": "body",
                    "field": "public_token_or_link_code",
                    "reason": "required_field_missing",
                },
            )
        return jsonify(_friendship_result_body(result))

    @blueprint.post("/complete-deferred")
    def complete_deferred():
        joiner_account_id = _customer_account_id(identity_service)
        payload = _json_payload()
        result = social_scheduling_service.complete_deferred_friend_link(
            joiner_account_id=joiner_account_id,
            friend_link_id=_body_str_field(payload, "friend_link_id"),
        )
        return jsonify(_friendship_result_body(result))

    @blueprint.get("")
    def list_friends():
        friends = social_scheduling_service.list_friends(
            account_id=_customer_account_id(identity_service)
        )
        return jsonify(
            {
                "friends": [
                    {
                        "account_id": friend.account_id,
                        "friendship_id": friend.friendship_id,
                    }
                    for friend in friends
                ]
            }
        )

    @blueprint.post("/<friend_account_id>/remove")
    def remove_friend(friend_account_id: str):
        friendship = social_scheduling_service.remove_friend(
            account_id=_customer_account_id(identity_service),
            friend_account_id=_path_str_field(friend_account_id, "friend_account_id"),
        )
        return jsonify(
            {"friendship_id": friendship.id, "lifecycle": friendship.lifecycle}
        )

    return blueprint


def _customer_account_id(identity_service) -> str:
    return require_customer_account_id(identity_service, SocialSchedulingError)


def _friend_link_body(link) -> dict:
    return {
        "friend_link_id": link.id,
        "owner_account_id": link.owner_account_id,
        "lifecycle": link.lifecycle,
        "public_token": link.public_token,
        "link_code": link.link_code,
        "qr_payload": link.qr_payload,
    }


def _friendship_result_body(result) -> dict:
    return {
        "status": result.status,
        "friendship_id": (
            result.friendship.id if result.friendship is not None else None
        ),
        "continuation": result.continuation,
    }


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise SocialSchedulingError(
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
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    return payload[field]


def _body_str_field(payload: dict, field: str) -> str:
    value = _body_field(payload, field)
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _query_str_field(field: str) -> str:
    value = request.args.get(field)
    if value is None:
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    if value.strip() == "" or value != value.strip():
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _path_str_field(value: str, field: str) -> str:
    if value.strip() == "" or value != value.strip():
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "path",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body


def _status_code(code: str) -> int:
    return 401 if code == "unauthorized" else 400
