import time

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import BadRequest

from conf.config import CONF
from connector.clawscale_bridge.identity_service import IdentityService
from connector.clawscale_bridge.message_gateway import CokeMessageGateway
from connector.clawscale_bridge.reply_waiter import ReplyWaiter
from connector.clawscale_bridge.user_auth import UserAuthService
from connector.clawscale_bridge.wechat_bind_session_service import (
    WechatBindSessionService,
)
from dao.binding_ticket_dao import BindingTicketDAO
from dao.external_identity_dao import ExternalIdentityDAO
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from dao.wechat_bind_session_dao import WechatBindSessionDAO


def _mongo_uri() -> str:
    return (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )


def _resolve_target_character_id(user_dao: UserDAO) -> str:
    character_alias = CONF.get("default_character_alias", "coke")
    characters = user_dao.find_characters({"name": character_alias}, limit=1)
    if not characters:
        raise ValueError(f"target character not found for alias={character_alias}")
    return str(characters[0]["_id"])


def _build_default_bridge_gateway():
    bridge_conf = CONF["clawscale_bridge"]
    mongo_uri = _mongo_uri()
    db_name = CONF["mongodb"]["mongodb_name"]

    user_dao = UserDAO(mongo_uri=mongo_uri, db_name=db_name)
    external_identity_dao = ExternalIdentityDAO(mongo_uri=mongo_uri, db_name=db_name)
    binding_ticket_dao = BindingTicketDAO(mongo_uri=mongo_uri, db_name=db_name)
    bind_session_dao = WechatBindSessionDAO(mongo_uri=mongo_uri, db_name=db_name)
    mongo = MongoDBBase(connection_string=mongo_uri, db_name=db_name)
    message_gateway = CokeMessageGateway(mongo=mongo, user_dao=user_dao)
    reply_waiter = ReplyWaiter(
        mongo=mongo,
        poll_interval_seconds=bridge_conf["poll_interval_seconds"],
        timeout_seconds=bridge_conf["reply_timeout_seconds"],
    )
    bind_session_service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        connect_url_template=bridge_conf["wechat_public_connect_url_template"],
        ttl_seconds=bridge_conf["wechat_bind_session_ttl_seconds"],
    )

    return IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url=bridge_conf["bind_base_url"],
        target_character_id=_resolve_target_character_id(user_dao),
    )


def _build_user_bind_service():
    mongo_uri = _mongo_uri()
    db_name = CONF["mongodb"]["mongodb_name"]
    bridge_conf = CONF["clawscale_bridge"]
    return WechatBindSessionService(
        bind_session_dao=WechatBindSessionDAO(mongo_uri=mongo_uri, db_name=db_name),
        external_identity_dao=ExternalIdentityDAO(mongo_uri=mongo_uri, db_name=db_name),
        connect_url_template=bridge_conf["wechat_public_connect_url_template"],
        ttl_seconds=bridge_conf["wechat_bind_session_ttl_seconds"],
    )


def _build_user_auth_service():
    bridge_conf = CONF["clawscale_bridge"]
    return UserAuthService(
        user_dao=UserDAO(
            mongo_uri=_mongo_uri(),
            db_name=CONF["mongodb"]["mongodb_name"],
        ),
        secret_key=bridge_conf["user_auth_secret"],
        token_ttl_seconds=bridge_conf["user_auth_token_ttl_seconds"],
    )


def _parse_required_json_fields(*required_fields):
    try:
        payload = request.get_json(force=True)
    except BadRequest:
        return None, (jsonify({"ok": False, "error": "invalid_request"}), 400)

    if not isinstance(payload, dict):
        return None, (jsonify({"ok": False, "error": "invalid_request"}), 400)

    missing_fields = [field for field in required_fields if field not in payload]
    if missing_fields:
        return None, (
            jsonify({"ok": False, "error": "missing_required_fields"}),
            400,
        )

    invalid_fields = [
        field
        for field in required_fields
        if not isinstance(payload.get(field), str) or not payload[field].strip()
    ]
    if invalid_fields:
        return None, (jsonify({"ok": False, "error": "invalid_request"}), 400)

    return payload, None


def create_app(testing: bool = False):
    app = Flask(__name__, template_folder="templates")
    app.config["TESTING"] = testing
    if testing:
        app.config["COKE_BRIDGE_API_KEY"] = "test-bridge-key"
        app.config["COKE_WEB_ALLOWED_ORIGIN"] = "http://127.0.0.1:4040"
    else:
        app.config["COKE_BRIDGE_API_KEY"] = CONF["clawscale_bridge"]["api_key"]
        app.config["BRIDGE_GATEWAY"] = _build_default_bridge_gateway()
        app.config["COKE_WEB_ALLOWED_ORIGIN"] = CONF["clawscale_bridge"][
            "web_allowed_origin"
        ]
        app.config["USER_AUTH_SERVICE"] = _build_user_auth_service()
        app.config["USER_BIND_SERVICE"] = _build_user_bind_service()

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = app.config[
            "COKE_WEB_ALLOWED_ORIGIN"
        ]
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.get("/bridge/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.post("/bridge/inbound")
    def inbound():
        from connector.clawscale_bridge.auth import require_bridge_auth

        ok, error = require_bridge_auth(app.config["COKE_BRIDGE_API_KEY"])
        if not ok:
            body, status = error
            return jsonify(body), status

        payload = request.get_json(force=True)
        gateway = app.config.get("BRIDGE_GATEWAY")
        if gateway is None:
            return jsonify({"ok": False, "error": "bridge service not wired"}), 500

        result = gateway.handle_inbound(payload)
        if result["status"] == "bind_required":
            response = {"ok": True, "reply": result["reply"]}
            if "bind_url" in result:
                response["bind_url"] = result["bind_url"]
            return jsonify(response)

        return jsonify({"ok": True, "reply": result["reply"]})

    @app.get("/bind/<ticket_id>")
    def bind_page(ticket_id: str):
        return render_template("bind.html", ticket_id=ticket_id)

    @app.post("/bind/<ticket_id>/submit")
    def submit_bind(ticket_id: str):
        return jsonify({"ok": True, "ticket_id": ticket_id})

    @app.post("/user/register")
    def user_register():
        payload, error_response = _parse_required_json_fields(
            "display_name", "email", "password"
        )
        if error_response:
            return error_response
        service = app.config["USER_AUTH_SERVICE"]
        try:
            result = service.register(
                display_name=payload["display_name"],
                email=payload["email"],
                password=payload["password"],
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, "data": result}), 201

    @app.post("/user/login")
    def user_login():
        payload, error_response = _parse_required_json_fields("email", "password")
        if error_response:
            return error_response
        service = app.config["USER_AUTH_SERVICE"]
        ok, result = service.login(payload["email"], payload["password"])
        if not ok:
            return jsonify({"ok": False, "error": result}), 401
        return jsonify({"ok": True, "data": result})

    def require_user_auth():
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header.split(" ", 1)[1]
        return app.config["USER_AUTH_SERVICE"].verify_token(token)

    @app.post("/user/wechat-bind/session")
    def create_wechat_bind_session():
        user = require_user_auth()
        if not user:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        result = app.config["USER_BIND_SERVICE"].create_or_reuse_session(
            account_id=str(user["_id"]),
            now_ts=int(time.time()),
        )
        return jsonify({"ok": True, "data": result})

    @app.get("/user/wechat-bind/status")
    def get_wechat_bind_status():
        user = require_user_auth()
        if not user:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        result = app.config["USER_BIND_SERVICE"].get_status(
            account_id=str(user["_id"]),
            now_ts=int(time.time()),
        )
        return jsonify({"ok": True, "data": result})

    return app


if __name__ == "__main__":
    bridge_conf = CONF["clawscale_bridge"]
    create_app().run(
        host=bridge_conf["host"],
        port=bridge_conf["port"],
    )
