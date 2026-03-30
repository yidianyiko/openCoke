import hashlib
import hmac
import logging
import os
import sys
import time
from datetime import datetime

import requests
from flask import Flask, jsonify, request

sys.path.append(".")
from dotenv import load_dotenv

load_dotenv()

CREEM_WEBHOOK_SECRET = os.getenv("CREEM_WEBHOOK_SECRET", "")

import stripe

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s-%(name)s-%(levelname)s-%(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

from conf.config import CONF
from connector.ecloud.ecloud_adapter import (
    ecloud_message_to_std,
    is_group_message,
    should_respond_to_group_message,
)
from connector.ecloud.ecloud_api import Ecloud_API
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.redis_client import RedisClient
from util.redis_stream import publish_input_event

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - optional dependency until redis is installed
    redis = None

mongo = MongoDBBase()
user_dao = UserDAO()
redis_conf = RedisClient.from_config()
redis_client = (
    redis.Redis(host=redis_conf.host, port=redis_conf.port, db=redis_conf.db)
    if redis is not None
    else None
)


def _publish_stream_event(message_id: str, platform: str, ts: int) -> None:
    if redis_client is None:
        return
    publish_input_event(
        redis_client,
        message_id,
        platform,
        ts,
        stream_key=redis_conf.stream_key,
    )


def _get_creem_webhook_secret() -> str:
    return os.getenv("CREEM_WEBHOOK_SECRET", CREEM_WEBHOOK_SECRET)


def _get_stripe_webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", STRIPE_WEBHOOK_SECRET)


# Whitelist dictionary-wcId as key, forwarding URL as value
# You can modify this dictionary as needed
whitelist = {
    "wxid_phyyedw9xap22": "http://example.com/forward1",
    "wxid_1dfgh4fs8vz22": "http://example.com/forward2",
    # Add more entries as needed
}

user_whitelist = []
# user_whitelist = ["LeanInWind", "z4656207", "wxid_vex849hfamd822", "samueli", "DoonsSong", "annie--y"]

supported_message_types = [
    # 私聊消息
    "60001",  # 私聊文本
    "60014",  # 私聊引用
    "60004",  # 私聊语音
    "60002",  # 私聊图片
    # 群聊消息
    "80001",  # 群聊文本
    "80014",  # 群聊引用
    "80004",  # 群聊语音
    "80002",  # 群聊图片
]


@app.route("/message", methods=["POST"])
def handle_message():
    """
    Handle incoming message requests and forward them based on wcId
    """
    if not request.is_json:
        logger.warning("Request is not JSON")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    # Get the JSON data
    data = request.get_json()
    logger.info(data)

    # Extract wcId from the request
    wcId = data.get("wcId")

    if not wcId:
        logger.warning("No wcId in request")
        return jsonify({"status": "error", "message": "No wcId provided"}), 400

    # Check if wcId is in whitelist
    if wcId in whitelist:
        forward_url = whitelist[wcId]

        try:
            # Forward the request to the corresponding URL
            logger.info(f"Forwarding request for wcId {wcId} to {forward_url}")
            response = requests.post(
                forward_url, json=data, headers={"Content-Type": "application/json"}
            )

            # Return the response from the forwarded request
            return jsonify(
                {
                    "status": "success",
                    "message": f"Request forwarded to {forward_url}",
                    "forward_status": response.status_code,
                    "forward_response": (
                        response.json()
                        if response.headers.get("content-type") == "application/json"
                        else response.text
                    ),
                }
            )

        except requests.RequestException as e:
            logger.error(f"Error forwarding request: {str(e)}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Error forwarding request: {str(e)}",
                    }
                ),
                500,
            )
    else:
        logger.info("message incoming, handling...")

        # 支持的类型
        if data["messageType"] not in supported_message_types:
            logger.info("not supported message type.")
            return (
                jsonify(
                    {"status": "success", "message": "not supported message type."}
                ),
                200,
            )

        # 白名单
        if len(user_whitelist) != 0:
            if data["data"]["fromUser"] not in user_whitelist:
                logger.info("user not in white list, ignore this message")
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "user not in white list, ignore this message",
                        }
                    ),
                    200,
                )

        # 验证character或者user是否存在
        characters = user_dao.find_characters(
            {"platforms.wechat.id": data["data"]["toUser"]}
        )

        if len(characters) == 0:
            return (
                jsonify(
                    {"status": "success", "message": "character not exist, skip..."}
                ),
                200,
            )

        cid = str(characters[0]["_id"])
        character = characters[0]

        # 群消息特殊处理
        if is_group_message(data):
            group_config = CONF.get("ecloud", {}).get("group_chat", {})
            bot_wxid = data["data"]["toUser"]
            bot_nickname = character.get("name", "")

            if not should_respond_to_group_message(
                data, group_config, bot_wxid, bot_nickname
            ):
                logger.info("group message filtered by reply policy")
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "group message filtered by reply policy",
                        }
                    ),
                    200,
                )

        # 用 id 字段查询（fromUser 是 wxid，存储在 id 字段）
        users = user_dao.find_users({"platforms.wechat.id": data["data"]["fromUser"]})

        # 如果用户不存在，则创建一个
        if len(users) == 0:
            logger.info("user not exist, create a new one")
            target_user_alias = characters[0]["name"]

            # 安全获取用户信息
            try:
                resp_json = Ecloud_API.getContact(
                    data["data"]["fromUser"], target_user_alias
                )
                logger.info(resp_json)

                # 检查 API 返回是否成功
                if not resp_json or resp_json.get("code") != "1000":
                    logger.error(
                        f"getContact API failed: {resp_json.get('message', 'unknown error')}"
                    )
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "failed to get user contact info",
                            }
                        ),
                        500,
                    )

                # 检查 data 数组是否非空
                contact_data = resp_json.get("data", [])
                if not contact_data:
                    logger.error("getContact returned empty data array")
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "user contact info not found",
                            }
                        ),
                        500,
                    )

                user_wechat_info = contact_data[0]
            except Exception as e:
                logger.error(f"getContact exception: {str(e)}")
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"failed to get user contact: {str(e)}",
                        }
                    ),
                    500,
                )

            uid = user_dao.create_user(
                {
                    "is_character": False,  # 是否是角色
                    "name": user_wechat_info.get("userName", data["data"]["fromUser"]),
                    "platforms": {
                        "wechat": {
                            "id": data["data"]["fromUser"],  # 微信统一id
                            "account": user_wechat_info.get(
                                "userName", data["data"]["fromUser"]
                            ),
                            "nickname": user_wechat_info.get("nickName", ""),
                        },
                    },
                    "status": "normal",  # normal | stopped
                    "user_info": {},
                    "user_wechat_info": user_wechat_info,
                }
            )
        else:
            uid = str(users[0]["_id"])

        # 标准化数据
        std = ecloud_message_to_std(data)
        std["from_user"] = uid
        std["to_user"] = cid

        # 消息去重：检查 newMsgId 是否已存在
        new_msg_id = std.get("metadata", {}).get("new_msg_id")
        if new_msg_id:
            existing = mongo.find_one(
                "inputmessages", {"metadata.new_msg_id": new_msg_id}
            )
            if existing:
                logger.info(f"duplicate message detected, newMsgId={new_msg_id}")
                return (
                    jsonify(
                        {"status": "success", "message": "duplicate message, skipped"}
                    ),
                    200,
                )

        # 插入到数据库
        inserted_id = mongo.insert_one("inputmessages", std)
        _publish_stream_event(
            inserted_id,
            std.get("platform", "wechat"),
            int(std.get("input_timestamp", time.time())),
        )

        return jsonify({"status": "success", "message": "message handing..."}), 200


@app.route("/webhook/creem", methods=["POST"])
def creem_webhook():
    """Handle Creem webhook events for subscription management."""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("creem-signature")
    webhook_secret = _get_creem_webhook_secret()

    if not sig_header:
        return jsonify({"error": "Missing signature"}), 400

    # Verify HMAC-SHA256 signature
    computed = hmac.new(
        webhook_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(computed, sig_header):
        logger.warning("Creem webhook: invalid signature")
        return jsonify({"error": "Invalid signature"}), 400

    event = request.get_json(force=True)
    event_type = event.get("eventType", "")
    obj = event.get("object", {})

    if event_type == "checkout.completed":
        _handle_creem_checkout_completed(obj)
    elif event_type == "subscription.paid":
        _handle_creem_subscription_paid(obj)
    elif event_type in ("subscription.canceled", "subscription.expired"):
        _handle_creem_subscription_revoked(obj)
    else:
        logger.info(f"Creem webhook: unhandled event type {event_type}")

    return jsonify({"status": "ok"}), 200


def _handle_creem_checkout_completed(obj: dict):
    """Grant access after initial checkout."""
    user_id = obj.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Creem checkout.completed: missing user_id in metadata")
        return

    customer_id = obj.get("customer", {}).get("id")
    subscription = obj.get("subscription", {})
    subscription_id = subscription.get("id")
    expire_time = _parse_creem_datetime(subscription.get("current_period_end"))

    user_dao.update_access_creem(
        user_id=user_id,
        creem_customer_id=customer_id,
        creem_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Creem: granted access to user {user_id}, expires {expire_time}")


def _handle_creem_subscription_paid(obj: dict):
    """Extend access on subscription renewal."""
    user_id = obj.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Creem subscription.paid: missing user_id in metadata")
        return

    customer_id = obj.get("customer", {}).get("id")
    subscription_id = obj.get("id")
    expire_time = _parse_creem_datetime(obj.get("current_period_end"))

    user_dao.update_access_creem(
        user_id=user_id,
        creem_customer_id=customer_id,
        creem_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Creem: extended access for user {user_id}, expires {expire_time}")


def _handle_creem_subscription_revoked(obj: dict):
    """Revoke access when subscription is cancelled or expired."""
    user_id = obj.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Creem subscription revoked: missing user_id in metadata")
        return

    user_dao.revoke_access(user_id)
    logger.info(f"Creem: revoked access for user {user_id}")


def _parse_creem_datetime(dt_str: str) -> datetime:
    """Parse ISO 8601 datetime string from Creem API."""
    if not dt_str:
        return datetime.now()
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        logger.warning(f"Creem: could not parse datetime {dt_str!r}, using now")
        return datetime.now()


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events for subscription management."""
    payload = request.get_data(as_text=False)
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = _get_stripe_webhook_secret()

    if not sig_header:
        return jsonify({"error": "Missing signature"}), 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        logger.warning("Stripe webhook: invalid signature")
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"] if isinstance(event, dict) else event.type

    if event_type == "checkout.session.completed":
        obj = event["data"]["object"] if isinstance(event, dict) else event.data.object
        _handle_stripe_checkout_completed(obj)
    elif event_type == "invoice.paid":
        obj = event["data"]["object"] if isinstance(event, dict) else event.data.object
        _handle_stripe_invoice_paid(obj)
    elif event_type == "customer.subscription.deleted":
        obj = event["data"]["object"] if isinstance(event, dict) else event.data.object
        _handle_stripe_subscription_deleted(obj)
    else:
        logger.info(f"Stripe webhook: unhandled event type {event_type}")

    return jsonify({"status": "ok"}), 200


def _handle_stripe_checkout_completed(session):
    """Grant access after initial Stripe checkout."""
    if isinstance(session, dict):
        user_id = session.get("metadata", {}).get("user_id")
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
    else:
        user_id = (session.metadata or {}).get("user_id")
        customer_id = session.customer
        subscription_id = session.subscription

    if not user_id:
        logger.warning("Stripe checkout.session.completed: missing user_id in metadata")
        return

    expire_time = _get_stripe_subscription_expire(subscription_id)

    user_dao.update_access_stripe(
        user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Stripe: granted access to user {user_id}, expires {expire_time}")


def _handle_stripe_invoice_paid(invoice):
    """Extend access on Stripe subscription renewal."""
    if isinstance(invoice, dict):
        subscription_id = invoice.get("subscription")
        customer_id = invoice.get("customer")
    else:
        subscription_id = invoice.subscription
        customer_id = invoice.customer

    if not subscription_id:
        return

    sub = stripe.Subscription.retrieve(subscription_id)
    metadata = sub.metadata if hasattr(sub, "metadata") else sub.get("metadata", {})
    user_id = metadata.get("user_id") if metadata else None

    if not user_id:
        logger.warning("Stripe invoice.paid: missing user_id in subscription metadata")
        return

    expire_time = _get_stripe_subscription_expire(subscription_id)

    user_dao.update_access_stripe(
        user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Stripe: extended access for user {user_id}, expires {expire_time}")


def _handle_stripe_subscription_deleted(subscription):
    """Revoke access when Stripe subscription is cancelled."""
    if isinstance(subscription, dict):
        user_id = subscription.get("metadata", {}).get("user_id")
    else:
        metadata = subscription.metadata if hasattr(subscription, "metadata") else {}
        user_id = metadata.get("user_id")

    if not user_id:
        logger.warning("Stripe subscription.deleted: missing user_id in metadata")
        return

    user_dao.revoke_access(user_id)
    logger.info(f"Stripe: revoked access for user {user_id}")


def _get_stripe_subscription_expire(subscription_id: str) -> datetime:
    """Fetch subscription period end from Stripe and convert to datetime."""
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        # current_period_end moved to items in newer Stripe API versions
        if hasattr(sub, "current_period_end") and sub.current_period_end:
            ts = sub.current_period_end
        else:
            ts = sub["items"]["data"][0]["current_period_end"]
        return datetime.utcfromtimestamp(ts)
    except Exception as e:
        logger.warning(f"Stripe: could not fetch subscription {subscription_id}: {e}")
        return datetime.now()


if __name__ == "__main__":
    logger.info("Starting Flask forwarding service")
    app.run(host="0.0.0.0", port=8080, debug=False)
