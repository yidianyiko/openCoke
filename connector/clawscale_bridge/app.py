import logging
import time
import threading
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest

from conf.config import CONF
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
from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher
from connector.clawscale_bridge.personal_wechat_channel_service import (
    PersonalWechatChannelService,
)
from connector.clawscale_bridge.user_auth import UserAuthService
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO

logger = logging.getLogger(__name__)


def _is_unresolved_bridge_setting(value) -> bool:
    return (
        not isinstance(value, str)
        or not value.strip()
        or (value.startswith("${") and value.endswith("}"))
    )


def _require_bridge_setting(name: str) -> str:
    value = CONF["clawscale_bridge"].get(name)
    if _is_unresolved_bridge_setting(value):
        raise RuntimeError(f"missing_required_clawscale_bridge_setting:{name}")
    return value


def _validate_runtime_bridge_settings() -> None:
    required_names = (
        "api_key",
        "user_auth_secret",
        "web_allowed_origin",
        "wechat_channel_api_url",
        "wechat_channel_api_key",
        "identity_api_url",
        "identity_api_key",
        "user_provision_api_url",
        "outbound_api_url",
        "outbound_api_key",
    )
    for name in required_names:
        _require_bridge_setting(name)


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


class BusinessOnlyBridgeGateway:
    def __init__(self, *, message_gateway, reply_waiter, target_character_id: str):
        self.message_gateway = message_gateway
        self.reply_waiter = reply_waiter
        self.target_character_id = target_character_id

    def _normalize_inbound(self, inbound_payload: dict) -> dict:
        metadata = inbound_payload.get("metadata") or {}
        messages = inbound_payload.get("messages") or []
        last_message = messages[-1] if messages else {}

        normalized = {
            "tenant_id": inbound_payload.get("tenant_id") or metadata.get("tenantId"),
            "channel_id": inbound_payload.get("channel_id") or metadata.get("channelId"),
            "platform": inbound_payload.get("platform") or metadata.get("platform"),
            "external_id": inbound_payload.get("external_id") or metadata.get("externalId"),
            "end_user_id": inbound_payload.get("end_user_id") or metadata.get("endUserId"),
            "gateway_conversation_id": inbound_payload.get("gateway_conversation_id")
            or metadata.get("gatewayConversationId")
            or inbound_payload.get("conversation_id")
            or metadata.get("conversationId"),
            "business_conversation_key": inbound_payload.get("business_conversation_key")
            or metadata.get("businessConversationKey"),
            "inbound_event_id": inbound_payload.get("inbound_event_id")
            or metadata.get("inboundEventId"),
            "sync_reply_token": inbound_payload.get("sync_reply_token")
            or metadata.get("syncReplyToken"),
            "input": inbound_payload.get("input")
            or last_message.get("content")
            or "",
            "channel_scope": inbound_payload.get("channel_scope")
            or metadata.get("channelScope"),
            "clawscale_user_id": inbound_payload.get("clawscale_user_id")
            or metadata.get("clawscaleUserId"),
            "coke_account_id": inbound_payload.get("coke_account_id")
            or metadata.get("cokeAccountId"),
        }
        return normalized

    def _trusted_coke_account_id(self, inbound: dict) -> str | None:
        required_fields = [
            "tenant_id",
            "channel_id",
            "platform",
            "external_id",
            "end_user_id",
            "channel_scope",
            "clawscale_user_id",
            "coke_account_id",
        ]
        if inbound.get("channel_scope") != "personal":
            return None
        if any(
            not isinstance(inbound.get(field), str) or not inbound[field].strip()
            for field in required_fields
        ):
            return None
        return inbound["coke_account_id"]

    def _enqueue_and_wait(self, account_id: str, inbound: dict, now_ts: int) -> dict:
        enqueue_payload = {
            "tenant_id": inbound["tenant_id"],
            "channel_id": inbound["channel_id"],
            "platform": inbound["platform"],
            "end_user_id": inbound["end_user_id"],
            "external_id": inbound["external_id"],
            "timestamp": now_ts,
        }
        if inbound.get("business_conversation_key"):
            enqueue_payload["business_conversation_key"] = inbound[
                "business_conversation_key"
            ]
        if inbound.get("gateway_conversation_id"):
            enqueue_payload["gateway_conversation_id"] = inbound[
                "gateway_conversation_id"
            ]
        if inbound.get("sync_reply_token"):
            enqueue_payload["sync_reply_token"] = inbound["sync_reply_token"]
        if inbound.get("inbound_event_id"):
            enqueue_payload["inbound_event_id"] = inbound["inbound_event_id"]

        causal_inbound_event_id = self.message_gateway.enqueue(
            account_id=account_id,
            character_id=self.target_character_id,
            text=inbound["input"],
            inbound=enqueue_payload,
        )
        sync_reply_token = inbound.get("sync_reply_token")
        if sync_reply_token:
            reply = self.reply_waiter.wait_for_reply(
                causal_inbound_event_id,
                sync_reply_token=sync_reply_token,
            )
        else:
            reply = self.reply_waiter.wait_for_reply(causal_inbound_event_id)
        if isinstance(reply, dict):
            return {"status": "ok", **reply}
        return {"status": "ok", "reply": reply}

    def handle_inbound(self, inbound_payload: dict):
        inbound = self._normalize_inbound(inbound_payload)
        coke_account_id = self._trusted_coke_account_id(inbound)
        if not coke_account_id:
            return {
                "status": "error",
                "error": "missing_coke_account_id",
            }
        return self._enqueue_and_wait(
            account_id=coke_account_id,
            inbound=inbound,
            now_ts=int(time.time()),
        )


def _build_default_bridge_gateway():
    bridge_conf = CONF["clawscale_bridge"]
    mongo_uri = _mongo_uri()
    db_name = CONF["mongodb"]["mongodb_name"]

    user_dao = UserDAO(mongo_uri=mongo_uri, db_name=db_name)
    mongo = MongoDBBase(connection_string=mongo_uri, db_name=db_name)
    message_gateway = CokeMessageGateway(mongo=mongo, user_dao=user_dao)
    reply_waiter = ReplyWaiter(
        mongo=mongo,
        poll_interval_seconds=bridge_conf["poll_interval_seconds"],
        timeout_seconds=bridge_conf["reply_timeout_seconds"],
    )
    return BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id=_resolve_target_character_id(user_dao),
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


def _build_output_dispatcher():
    bridge_conf = CONF["clawscale_bridge"]
    mongo_uri = _mongo_uri()
    db_name = CONF["mongodb"]["mongodb_name"]
    return ClawScaleOutputDispatcher(
        mongo=MongoDBBase(connection_string=mongo_uri, db_name=db_name),
        session=None,
        outbound_api_url=bridge_conf["outbound_api_url"],
        outbound_api_key=bridge_conf["outbound_api_key"],
    )


def _run_output_dispatcher_loop(dispatcher, poll_interval_seconds: int):
    while True:
        try:
            dispatcher.dispatch_once()
        except Exception:
            logger.exception("clawscale output dispatcher iteration failed")
        time.sleep(poll_interval_seconds)


def _start_output_dispatcher(dispatcher):
    bridge_conf = CONF["clawscale_bridge"]
    poll_interval_seconds = bridge_conf.get(
        "output_dispatcher_poll_interval_seconds",
        bridge_conf["poll_interval_seconds"],
    )
    thread = threading.Thread(
        target=_run_output_dispatcher_loop,
        args=(dispatcher, poll_interval_seconds),
        daemon=True,
    )
    thread.start()
    return thread


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


def _require_durable_provision_readiness(provision_result):
    if not isinstance(provision_result, dict):
        raise GatewayUserProvisionClientError("invalid_gateway_user_provision_response")

    if provision_result.get("ready") is False:
        raise GatewayUserProvisionClientError("gateway_user_provision_not_ready")

    tenant_id = provision_result.get("tenant_id") or provision_result.get("tenantId")
    clawscale_user_id = provision_result.get("clawscale_user_id") or provision_result.get(
        "clawscaleUserId"
    )
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise GatewayUserProvisionClientError("invalid_gateway_user_provision_response")
    if not isinstance(clawscale_user_id, str) or not clawscale_user_id.strip():
        raise GatewayUserProvisionClientError("invalid_gateway_user_provision_response")

    return {
        "tenant_id": tenant_id,
        "clawscale_user_id": clawscale_user_id,
        "ready": True,
    }


def create_app(testing: bool = False):
    app = Flask(__name__, template_folder="templates")
    app.config["TESTING"] = testing
    if testing:
        app.config["COKE_BRIDGE_API_KEY"] = "test-bridge-key"
        app.config["COKE_WEB_ALLOWED_ORIGIN"] = "http://127.0.0.1:4040"
    else:
        _validate_runtime_bridge_settings()
        app.config["COKE_BRIDGE_API_KEY"] = _require_bridge_setting("api_key")
        app.config["BRIDGE_GATEWAY"] = _build_default_bridge_gateway()
        app.config["COKE_WEB_ALLOWED_ORIGIN"] = _require_bridge_setting(
            "web_allowed_origin"
        )
        app.config["USER_AUTH_SERVICE"] = _build_user_auth_service()
        app.config["USER_PERSONAL_CHANNEL_SERVICE"] = (
            _build_personal_wechat_channel_service()
        )
        app.config["USER_PROVISION_SERVICE"] = _build_gateway_user_provision_client()
        app.config["OUTPUT_DISPATCHER"] = _build_output_dispatcher()
        app.config["OUTPUT_DISPATCHER_THREAD"] = _start_output_dispatcher(
            app.config["OUTPUT_DISPATCHER"]
        )

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
        if result.get("status") != "ok":
            return jsonify({"ok": False, "error": result.get("error", "invalid_request")}), 400

        response = {"ok": True, "reply": result["reply"]}
        for key in (
            "business_conversation_key",
            "output_id",
            "causal_inbound_event_id",
        ):
            if key in result and result[key]:
                response[key] = result[key]
        return jsonify(response)

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
                _require_durable_provision_readiness(
                    provision_service.ensure_user(
                        account_id=result["user"]["id"],
                        display_name=result["user"].get("display_name"),
                    )
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
                _require_durable_provision_readiness(
                    provision_service.ensure_user(
                        account_id=result["user"]["id"],
                        display_name=result["user"].get("display_name"),
                    )
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

    return app


if __name__ == "__main__":
    bridge_conf = CONF["clawscale_bridge"]
    create_app().run(
        host=bridge_conf["host"],
        port=bridge_conf["port"],
    )
