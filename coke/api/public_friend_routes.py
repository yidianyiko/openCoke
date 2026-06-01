from __future__ import annotations

from flask import Blueprint, jsonify


def create_public_friend_blueprint(social_scheduling_service) -> Blueprint:
    blueprint = Blueprint(
        "public_friend_links",
        __name__,
        url_prefix="/api/public/user-links",
    )

    @blueprint.get("/<code>")
    def get_public_friend_link(code: str):
        view = social_scheduling_service.resolve_public_friend_link(code)
        if view is None:
            return jsonify({"error": {"code": "friend_link_not_active"}}), 404
        return jsonify(
            {
                "code": view.link_code,
                "status": view.status,
                "profile": {
                    "displayName": view.owner_display_name,
                    "tagline": None,
                    "avatarUrl": None,
                },
            }
        )

    return blueprint
