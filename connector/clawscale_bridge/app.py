import time
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import BadRequest

from conf.config import CONF
from connector.clawscale_bridge.identity_service import IdentityService
from connector.clawscale_bridge.gateway_identity_client import GatewayIdentityClient
from connector.clawscale_bridge.gateway_personal_channel_client import (
    GatewayPersonalChannelClient,
    GatewayPersonalChannelClientError,
)
from connector.clawscale_bridge.gateway_user_provision_client import (
    GatewayUserProvisionClient,
    GatewayUserProvisionClientError,
)
from connector.clawscale_bridge.message_gateway import CokeMessageGateway
from connector.clawscale_bridge.reply_waiter import ReplyWaiter
from connector.clawscale_bridge.personal_wechat_channel_service import (
    PersonalWechatChannelService,
)
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


def _build_gateway_identity_client():
    bridge_conf = CONF["clawscale_bridge"]
    return GatewayIdentityClient(
        api_url=bridge_conf["identity_api_url"],
        api_key=bridge_conf["identity_api_key"],
    )


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
    gateway_identity_client = _build_gateway_identity_client()
    bind_session_service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        bind_base_url=bridge_conf["bind_base_url"],
        public_connect_url_template=bridge_conf["wechat_public_connect_url_template"],
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
    gateway_identity_client = _build_gateway_identity_client()
    return WechatBindSessionService(
        bind_session_dao=WechatBindSessionDAO(mongo_uri=mongo_uri, db_name=db_name),
        external_identity_dao=ExternalIdentityDAO(mongo_uri=mongo_uri, db_name=db_name),
        gateway_identity_client=gateway_identity_client,
        bind_base_url=bridge_conf["bind_base_url"],
        public_connect_url_template=bridge_conf["wechat_public_connect_url_template"],
        ttl_seconds=bridge_conf["wechat_bind_session_ttl_seconds"],
    )


def _build_gateway_personal_channel_client():
    bridge_conf = CONF["clawscale_bridge"]
    return GatewayPersonalChannelClient(
        api_base_url=bridge_conf["wechat_channel_api_url"],
        api_key=bridge_conf["wechat_channel_api_key"],
    )


def _build_gateway_user_provision_client():
    bridge_conf = CONF["clawscale_bridge"]
    return GatewayUserProvisionClient(
        api_url=bridge_conf["user_provision_api_url"],
        api_key=bridge_conf["identity_api_key"],
    )


def _build_personal_wechat_channel_service():
    client = _build_gateway_personal_channel_client()
    return PersonalWechatChannelService(gateway_client=client)


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


def _resolve_cors_origin(allowed_origin: str, request_origin: str | None) -> str:
    if not request_origin or request_origin == allowed_origin:
        return allowed_origin

    allowed = urlsplit(allowed_origin)
    requested = urlsplit(request_origin)
    loopback_hosts = {"localhost", "127.0.0.1"}

    if (
        allowed.scheme == requested.scheme
        and allowed.port == requested.port
        and allowed.hostname in loopback_hosts
        and requested.hostname in loopback_hosts
    ):
        return request_origin

    return allowed_origin


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
        app.config["USER_PERSONAL_CHANNEL_SERVICE"] = (
            _build_personal_wechat_channel_service()
        )
        app.config["USER_PROVISION_SERVICE"] = _build_gateway_user_provision_client()

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = _resolve_cors_origin(
            app.config["COKE_WEB_ALLOWED_ORIGIN"],
            request.headers.get("Origin"),
        )
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
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
        provision_service = app.config.get("USER_PROVISION_SERVICE")
        if provision_service is not None:
            try:
                provision_service.ensure_user(
                    account_id=result["user"]["id"],
                    display_name=result["user"].get("display_name"),
                )
            except GatewayUserProvisionClientError as exc:
                service.user_dao.delete_user(result["user"]["id"])
                return jsonify({"ok": False, "error": str(exc)}), 502
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
        provision_service = app.config.get("USER_PROVISION_SERVICE")
        if provision_service is not None:
            try:
                provision_service.ensure_user(
                    account_id=result["user"]["id"],
                    display_name=result["user"].get("display_name"),
                )
            except GatewayUserProvisionClientError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 502
        return jsonify({"ok": True, "data": result})

    def require_user_auth():
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header.split(" ", 1)[1]
        return app.config["USER_AUTH_SERVICE"].verify_token(token)

    def _personal_channel_response(method_name: str):
        user = require_user_auth()
        if not user:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        service = app.config.get("USER_PERSONAL_CHANNEL_SERVICE")
        if service is None:
            return jsonify({"ok": False, "error": "bridge service not wired"}), 500

        try:
            result = getattr(service, method_name)(account_id=str(user["_id"]))
        except GatewayPersonalChannelClientError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502

        return jsonify({"ok": True, "data": result})

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

    @app.post("/user/wechat-channel")
    def create_wechat_channel():
        return _personal_channel_response("create_or_reuse_channel")

    @app.post("/user/wechat-channel/connect")
    def connect_wechat_channel():
        return _personal_channel_response("start_connect")

    @app.get("/user/wechat-channel/status")
    def get_wechat_channel_status():
        return _personal_channel_response("get_status")

    @app.post("/user/wechat-channel/disconnect")
    def disconnect_wechat_channel():
        return _personal_channel_response("disconnect_channel")

    @app.delete("/user/wechat-channel")
    def archive_wechat_channel():
        return _personal_channel_response("archive_channel")

    @app.get("/user/wechat-bind/entry/<bind_token>")
    def user_wechat_bind_entry(bind_token: str):
        context = app.config["USER_BIND_SERVICE"].get_entry_page_context(
            bind_token=bind_token,
            now_ts=int(time.time()),
        )
        status_code = 200 if context["status"] == "pending" else 410
        return (
            render_template("wechat_bind_entry.html", context=context),
            status_code,
        )

    return app


if __name__ == "__main__":
    bridge_conf = CONF["clawscale_bridge"]
    create_app().run(
        host=bridge_conf["host"],
        port=bridge_conf["port"],
    )
