import logging
import time
import threading
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, jsonify, request

from conf.config import CONF
from connector.clawscale_bridge.gateway_delivery_route_client import (
    GatewayDeliveryRouteClient,
)
from connector.clawscale_bridge.google_calendar_import_service import (
    GoogleCalendarImportService,
)
from connector.clawscale_bridge.inbound_attachments import (
    MAX_ATTACHMENT_JSON_BYTES,
    format_input_with_attachments,
    normalize_inbound_attachments,
)
from connector.clawscale_bridge.message_gateway import CokeMessageGateway
from connector.clawscale_bridge.reply_waiter import ReplyWaiter
from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO

logger = logging.getLogger(__name__)
MAX_BRIDGE_INBOUND_REQUEST_BYTES = MAX_ATTACHMENT_JSON_BYTES


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
        "web_allowed_origin",
        "wechat_channel_api_url",
        "wechat_channel_api_key",
        "identity_api_url",
        "identity_api_key",
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


def _derive_delivery_route_api_url(identity_api_url: str) -> str:
    parsed = urlsplit(identity_api_url)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            "/api/internal/coke-delivery",
            "",
            "",
        )
    )


def _resolve_target_character_id(user_dao: UserDAO) -> str:
    character_alias = CONF.get("default_character_alias", "coke")
    characters = user_dao.find_characters({"name": character_alias}, limit=1)
    if not characters:
        raise ValueError(f"target character not found for alias={character_alias}")
    return str(characters[0]["_id"])


class LateReplyFallbackPromoter:
    def __init__(
        self,
        *,
        mongo,
        reply_waiter,
        delivery_route_client=None,
        thread_factory=threading.Thread,
    ):
        self.mongo = mongo
        self.reply_waiter = reply_waiter
        self.delivery_route_client = delivery_route_client
        self.thread_factory = thread_factory

    def start_async(
        self,
        *,
        causal_inbound_event_id: str,
        customer_id: str,
        tenant_id: str | None = None,
        conversation_id: str | None = None,
        channel_id: str | None = None,
        end_user_id: str | None = None,
        external_end_user_id: str | None = None,
        sync_reply_token: str | None = None,
    ):
        thread = self.thread_factory(
            target=self._promote_for_async_dispatch,
            kwargs={
                "causal_inbound_event_id": causal_inbound_event_id,
                "customer_id": customer_id,
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "channel_id": channel_id,
                "end_user_id": end_user_id,
                "external_end_user_id": external_end_user_id,
                "sync_reply_token": sync_reply_token,
            },
            daemon=True,
        )
        thread.start()
        return thread

    def _promote_for_async_dispatch(
        self,
        *,
        causal_inbound_event_id: str,
        customer_id: str,
        tenant_id: str | None = None,
        conversation_id: str | None = None,
        channel_id: str | None = None,
        end_user_id: str | None = None,
        external_end_user_id: str | None = None,
        sync_reply_token: str | None = None,
    ) -> bool:
        try:
            message = self.reply_waiter.wait_for_reply_message(
                causal_inbound_event_id,
                sync_reply_token=sync_reply_token,
                consume=False,
            )
        except TimeoutError:
            logger.warning(
                "late_clawscale_reply_timeout: causal_inbound_event_id=%s",
                causal_inbound_event_id,
            )
            return False

        metadata = message.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        business_protocol = metadata.get("business_protocol")
        if not isinstance(business_protocol, dict):
            business_protocol = {}

        business_conversation_key = business_protocol.get("business_conversation_key")
        if not isinstance(business_conversation_key, str) or not business_conversation_key:
            logger.warning(
                "late_clawscale_reply_missing_business_conversation_key: "
                "causal_inbound_event_id=%s output_id=%s",
                causal_inbound_event_id,
                message.get("_id"),
            )
            return False

        output_id = str(message["_id"])
        idempotency_key = f"late_sync_reply:{output_id}"

        if self.delivery_route_client is not None:
            if all(
                isinstance(value, str) and value.strip()
                for value in (
                    tenant_id,
                    conversation_id,
                    channel_id,
                    end_user_id,
                    external_end_user_id,
                )
            ):
                try:
                    self.delivery_route_client.bind(
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        account_id=customer_id,
                        business_conversation_key=business_conversation_key,
                        channel_id=channel_id,
                        end_user_id=end_user_id,
                        external_end_user_id=external_end_user_id,
                    )
                except Exception:
                    logger.exception(
                        "late_clawscale_reply_delivery_route_bind_failed: "
                        "causal_inbound_event_id=%s output_id=%s",
                        causal_inbound_event_id,
                        output_id,
                    )
                    return False
            else:
                logger.warning(
                    "late_clawscale_reply_missing_route_context: "
                    "causal_inbound_event_id=%s output_id=%s",
                    causal_inbound_event_id,
                    output_id,
                )
                return False

        updated = self.mongo.update_one(
            "outputmessages",
            {"_id": message["_id"], "status": "pending"},
            {
                "$set": {
                    "customer_id": customer_id,
                    "metadata.business_conversation_key": business_conversation_key,
                    "metadata.delivery_mode": "push",
                    "metadata.output_id": output_id,
                    "metadata.idempotency_key": idempotency_key,
                    "metadata.trace_id": idempotency_key,
                    "metadata.causal_inbound_event_id": causal_inbound_event_id,
                }
            },
        )
        if updated == 0:
            logger.info(
                "late_clawscale_reply_already_claimed: causal_inbound_event_id=%s output_id=%s",
                causal_inbound_event_id,
                output_id,
            )
            return False

        logger.info(
            "late_clawscale_reply_promoted_for_async_dispatch: "
            "causal_inbound_event_id=%s output_id=%s",
            causal_inbound_event_id,
            output_id,
        )
        return True


class BusinessOnlyBridgeGateway:
    def __init__(
        self,
        *,
        message_gateway,
        reply_waiter,
        target_character_id: str,
        late_reply_fallback=None,
    ):
        self.message_gateway = message_gateway
        self.reply_waiter = reply_waiter
        self.target_character_id = target_character_id
        self.late_reply_fallback = late_reply_fallback

    def _metadata_value(
        self, inbound_payload: dict, metadata: dict, key: str, legacy_key: str
    ):
        value = metadata.get(key)
        if value is not None:
            return value
        return inbound_payload.get(legacy_key)

    def _first_present(self, *values):
        for value in values:
            if value is not None:
                return value
        return None

    def _has_required_context(self, inbound: dict, required_fields: list[str]) -> bool:
        return not any(
            not isinstance(inbound.get(field), str) or not inbound[field].strip()
            for field in required_fields
        )

    def _latest_user_message(self, messages: list) -> dict:
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                return message
        return {}

    def _choose_attachments(
        self,
        *,
        inbound_payload: dict,
        latest_user_message: dict,
        last_message: dict,
    ):
        candidates = [inbound_payload.get("attachments")]
        if latest_user_message:
            candidates.append(latest_user_message.get("attachments"))
        if last_message.get("role") == "user" and last_message is not latest_user_message:
            candidates.append(last_message.get("attachments"))

        for raw_attachments in candidates:
            result = normalize_inbound_attachments(raw_attachments)
            if result.rejected:
                return result
            if result.attachments:
                return result
        return normalize_inbound_attachments(None)

    def _normalize_inbound(self, inbound_payload: dict) -> dict:
        metadata = inbound_payload.get("metadata") or {}
        messages = inbound_payload.get("messages") or []
        last_message = messages[-1] if messages and isinstance(messages[-1], dict) else {}
        latest_user_message = self._latest_user_message(messages)
        inbound_text = (
            inbound_payload.get("input")
            or latest_user_message.get("content")
            or last_message.get("content")
            or ""
        )
        attachment_result = self._choose_attachments(
            inbound_payload=inbound_payload,
            latest_user_message=latest_user_message,
            last_message=last_message,
        )
        attachments = attachment_result.attachments

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
            "input": format_input_with_attachments(inbound_text, attachments),
            "inbound_text": inbound_text,
            "attachments": attachments,
            "attachments_rejected": attachment_result.rejected,
            "attachments_rejected_reason": attachment_result.reason,
            "channel_scope": inbound_payload.get("channel_scope")
            or metadata.get("channelScope"),
            "clawscale_user_id": inbound_payload.get("clawscale_user_id")
            or metadata.get("clawscaleUserId"),
            "coke_account_id": self._first_present(
                inbound_payload.get("coke_account_id"),
                inbound_payload.get("customer_id"),
                inbound_payload.get("customerId"),
                metadata.get("cokeAccountId"),
                metadata.get("customerId"),
                metadata.get("customer_id"),
            ),
            "coke_account_display_name": self._metadata_value(
                inbound_payload,
                metadata,
                "cokeAccountDisplayName",
                "coke_account_display_name",
            ),
            "account_status": self._metadata_value(
                inbound_payload, metadata, "accountStatus", "account_status"
            ),
            "email_verified": self._metadata_value(
                inbound_payload, metadata, "emailVerified", "email_verified"
            ),
            "subscription_active": self._metadata_value(
                inbound_payload, metadata, "subscriptionActive", "subscription_active"
            ),
            "subscription_expires_at": self._metadata_value(
                inbound_payload,
                metadata,
                "subscriptionExpiresAt",
                "subscription_expires_at",
            ),
            "account_access_allowed": self._metadata_value(
                inbound_payload,
                metadata,
                "accountAccessAllowed",
                "account_access_allowed",
            ),
            "account_access_denied_reason": self._metadata_value(
                inbound_payload,
                metadata,
                "accountAccessDeniedReason",
                "account_access_denied_reason",
            ),
            "renewal_url": self._metadata_value(
                inbound_payload, metadata, "renewalUrl", "renewal_url"
            ),
        }
        return normalized

    def _trusted_coke_account_id(self, inbound: dict) -> str | None:
        required_fields = [
            "tenant_id",
            "channel_id",
            "platform",
            "external_id",
            "end_user_id",
            "coke_account_id",
        ]
        if not self._has_required_context(inbound, required_fields):
            return None

        if inbound.get("channel_scope") == "personal" and not self._has_required_context(
            inbound, ["clawscale_user_id"]
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
        if inbound.get("coke_account_id"):
            enqueue_payload["customer_id"] = inbound["coke_account_id"]
            enqueue_payload["coke_account_id"] = inbound["coke_account_id"]
        for key in ("coke_account_display_name",):
            if key in inbound:
                enqueue_payload[key] = inbound[key]
        if inbound.get("attachments"):
            enqueue_payload["input"] = inbound["input"]
            enqueue_payload["inbound_text"] = inbound.get("inbound_text", "")
            enqueue_payload["attachments"] = inbound["attachments"]

        causal_inbound_event_id = self.message_gateway.enqueue(
            account_id=account_id,
            character_id=self.target_character_id,
            text=inbound["input"],
            inbound=enqueue_payload,
        )
        sync_reply_token = inbound.get("sync_reply_token")
        try:
            if sync_reply_token:
                reply = self.reply_waiter.wait_for_reply(
                    causal_inbound_event_id,
                    sync_reply_token=sync_reply_token,
                )
            else:
                reply = self.reply_waiter.wait_for_reply(causal_inbound_event_id)
        except TimeoutError:
            customer_id = inbound.get("coke_account_id") or inbound.get("customer_id")
            if (
                self.late_reply_fallback is not None
                and isinstance(customer_id, str)
                and customer_id.strip()
            ):
                self.late_reply_fallback.start_async(
                    causal_inbound_event_id=causal_inbound_event_id,
                    customer_id=customer_id,
                    tenant_id=inbound.get("tenant_id"),
                    conversation_id=inbound.get("gateway_conversation_id"),
                    channel_id=inbound.get("channel_id"),
                    end_user_id=inbound.get("end_user_id"),
                    external_end_user_id=inbound.get("external_id"),
                    sync_reply_token=sync_reply_token,
                )
                return {"status": "ok"}
            raise
        if isinstance(reply, dict):
            return {"status": "ok", **reply}
        return {"status": "ok", "reply": reply}

    def _build_access_denied_reply(self, inbound: dict) -> str:
        renewal_url = inbound.get("renewal_url")
        denied_reason = inbound.get("account_access_denied_reason")

        if denied_reason == "subscription_required":
            message = "Your subscription is required."
        elif denied_reason == "email_not_verified":
            message = "Your email address is not verified."
        elif denied_reason == "account_suspended":
            message = "Your account is suspended."
        else:
            message = "This account is currently unavailable."

        if renewal_url:
            return f"{message} Renew here: {renewal_url}"
        return message

    def handle_inbound(self, inbound_payload: dict):
        inbound = self._normalize_inbound(inbound_payload)
        coke_account_id = self._trusted_coke_account_id(inbound)
        if not coke_account_id:
            return {
                "status": "error",
                "error": "missing_coke_account_id",
            }
        if inbound.get("attachments_rejected"):
            return {
                "status": "error",
                "error": inbound.get("attachments_rejected_reason")
                or "attachment_payload_too_large",
            }
        if not inbound.get("input", "").strip() and not inbound.get("attachments"):
            return {
                "status": "ignored",
                "reason": "empty_inbound",
            }
        if inbound.get("account_access_allowed") is False:
            return {
                "status": "ok",
                "reply": self._build_access_denied_reply(inbound),
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
    delivery_route_client = GatewayDeliveryRouteClient(
        api_url=_derive_delivery_route_api_url(bridge_conf["identity_api_url"]),
        api_key=bridge_conf["identity_api_key"],
    )
    late_reply_fallback = LateReplyFallbackPromoter(
        mongo=mongo,
        reply_waiter=ReplyWaiter(
            mongo=mongo,
            poll_interval_seconds=bridge_conf["poll_interval_seconds"],
            timeout_seconds=max(bridge_conf["reply_timeout_seconds"] * 4, 300),
        ),
        delivery_route_client=delivery_route_client,
    )
    return BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id=_resolve_target_character_id(user_dao),
        late_reply_fallback=late_reply_fallback,
    )


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


def _build_google_calendar_import_service():
    return GoogleCalendarImportService()


def _resolve_google_calendar_import_target(service, payload: dict) -> dict:
    customer_id = payload.get("customer_id")
    conversation_id = payload.get("target_conversation_id")
    character_id = payload.get("target_character_id")
    target_timezone = payload.get("target_timezone")

    if all(
        isinstance(value, str) and value.strip()
        for value in (customer_id, conversation_id, character_id, target_timezone)
    ):
        return {
            "conversation_id": conversation_id,
            "user_id": customer_id,
            "character_id": character_id,
            "timezone": target_timezone,
        }

    return service.preflight(customer_id=customer_id)


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
        _validate_runtime_bridge_settings()
        app.config["COKE_BRIDGE_API_KEY"] = _require_bridge_setting("api_key")
        app.config["BRIDGE_GATEWAY"] = _build_default_bridge_gateway()
        app.config["GOOGLE_CALENDAR_IMPORT_SERVICE"] = _build_google_calendar_import_service()
        app.config["COKE_WEB_ALLOWED_ORIGIN"] = _require_bridge_setting(
            "web_allowed_origin"
        )
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

        if (
            request.content_length is not None
            and request.content_length > MAX_BRIDGE_INBOUND_REQUEST_BYTES
        ):
            return jsonify(
                {"ok": False, "error": "attachment_payload_too_large"}
            ), 413

        payload = request.get_json(force=True)
        gateway = app.config.get("BRIDGE_GATEWAY")
        if gateway is None:
            return jsonify({"ok": False, "error": "bridge service not wired"}), 500

        result = gateway.handle_inbound(payload)
        if result.get("status") == "ignored":
            return jsonify(
                {
                    "ok": True,
                    "ignored": True,
                    "reason": result.get("reason", "empty_inbound"),
                }
            )
        if result.get("status") != "ok":
            return jsonify({"ok": False, "error": result.get("error", "invalid_request")}), 400

        response = {"ok": True}
        if isinstance(result.get("reply"), str) and result["reply"]:
            response["reply"] = result["reply"]
        for key in (
            "business_conversation_key",
            "output_id",
            "causal_inbound_event_id",
        ):
            if key in result and result[key]:
                response[key] = result[key]
        return jsonify(response)

    @app.post("/bridge/internal/google-calendar-import/preflight")
    def google_calendar_import_preflight():
        from connector.clawscale_bridge.auth import require_bridge_auth

        ok, error = require_bridge_auth(app.config["COKE_BRIDGE_API_KEY"])
        if not ok:
            body, status = error
            return jsonify(body), status

        service = app.config.get("GOOGLE_CALENDAR_IMPORT_SERVICE")
        if service is None:
            return jsonify({"ok": False, "error": "bridge service not wired"}), 500

        payload = request.get_json(force=True) or {}
        try:
            result = service.preflight(customer_id=payload.get("customer_id"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "data": result})

    @app.post("/bridge/internal/google-calendar-import/run")
    def google_calendar_import_run():
        from connector.clawscale_bridge.auth import require_bridge_auth

        ok, error = require_bridge_auth(app.config["COKE_BRIDGE_API_KEY"])
        if not ok:
            body, status = error
            return jsonify(body), status

        service = app.config.get("GOOGLE_CALENDAR_IMPORT_SERVICE")
        if service is None:
            return jsonify({"ok": False, "error": "bridge service not wired"}), 500

        payload = request.get_json(force=True) or {}
        try:
            target = _resolve_google_calendar_import_target(service, payload)
            result = service.import_events(
                target=target,
                run_id=payload.get("run_id"),
                provider_account_email=payload.get("provider_account_email"),
                calendar_defaults=payload.get("calendar_defaults") or {},
                events=payload.get("events") or [],
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "data": result})

    return app


if __name__ == "__main__":
    bridge_conf = CONF["clawscale_bridge"]
    create_app().run(
        host=bridge_conf["host"],
        port=bridge_conf["port"],
    )
