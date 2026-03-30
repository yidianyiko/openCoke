import hashlib
import hmac
import json
import os
from datetime import datetime
from typing import Any

import stripe
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)

router = APIRouter()

CREEM_WEBHOOK_SECRET = os.getenv("CREEM_WEBHOOK_SECRET", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
user_dao = None


def _get_user_dao():
    global user_dao
    if user_dao is None:
        user_dao = UserDAO()
    return user_dao


def handle_creem_webhook_request(
    *, payload: bytes, signature: str | None
) -> tuple[int, dict[str, str]]:
    if not signature:
        return 400, {"error": "Missing signature"}

    computed = hmac.new(CREEM_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, signature):
        logger.warning("Creem webhook: invalid signature")
        return 400, {"error": "Invalid signature"}

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Creem webhook: invalid payload")
        return 400, {"error": "Invalid payload"}
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

    return 200, {"status": "ok"}


def handle_stripe_webhook_request(
    *, payload: bytes, signature: str | None
) -> tuple[int, dict[str, str]]:
    if not signature:
        return 400, {"error": "Missing signature"}

    try:
        event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception:
        logger.warning("Stripe webhook: invalid signature")
        return 400, {"error": "Invalid signature"}

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

    return 200, {"status": "ok"}


@router.post("/webhook/creem")
async def creem_webhook(request: Request) -> JSONResponse:
    payload = await request.body()
    sig_header = request.headers.get("creem-signature")
    status_code, body = handle_creem_webhook_request(
        payload=payload,
        signature=sig_header,
    )
    return JSONResponse(status_code=status_code, content=body)


def _handle_creem_checkout_completed(obj: dict) -> None:
    user_id = obj.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Creem checkout.completed: missing user_id in metadata")
        return

    customer_id = obj.get("customer", {}).get("id")
    subscription = obj.get("subscription", {})
    subscription_id = subscription.get("id")
    expire_time = _parse_creem_datetime(subscription.get("current_period_end"))

    _get_user_dao().update_access_creem(
        user_id=user_id,
        creem_customer_id=customer_id,
        creem_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Creem: granted access to user {user_id}, expires {expire_time}")


def _handle_creem_subscription_paid(obj: dict) -> None:
    user_id = obj.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Creem subscription.paid: missing user_id in metadata")
        return

    customer_id = obj.get("customer", {}).get("id")
    subscription_id = obj.get("id")
    expire_time = _parse_creem_datetime(obj.get("current_period_end"))

    _get_user_dao().update_access_creem(
        user_id=user_id,
        creem_customer_id=customer_id,
        creem_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Creem: extended access for user {user_id}, expires {expire_time}")


def _handle_creem_subscription_revoked(obj: dict) -> None:
    user_id = obj.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Creem subscription revoked: missing user_id in metadata")
        return

    _get_user_dao().revoke_access(user_id)
    logger.info(f"Creem: revoked access for user {user_id}")


def _parse_creem_datetime(dt_str: str | None) -> datetime:
    if not dt_str:
        return datetime.now()
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        logger.warning(f"Creem: could not parse datetime {dt_str!r}, using now")
        return datetime.now()


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> JSONResponse:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    status_code, body = handle_stripe_webhook_request(
        payload=payload,
        signature=sig_header,
    )
    return JSONResponse(status_code=status_code, content=body)


def _handle_stripe_checkout_completed(session: Any) -> None:
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
    _get_user_dao().update_access_stripe(
        user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Stripe: granted access to user {user_id}, expires {expire_time}")


def _handle_stripe_invoice_paid(invoice: Any) -> None:
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
    _get_user_dao().update_access_stripe(
        user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Stripe: extended access for user {user_id}, expires {expire_time}")


def _handle_stripe_subscription_deleted(subscription: Any) -> None:
    if isinstance(subscription, dict):
        user_id = subscription.get("metadata", {}).get("user_id")
    else:
        metadata = subscription.metadata if hasattr(subscription, "metadata") else {}
        user_id = metadata.get("user_id")

    if not user_id:
        logger.warning("Stripe subscription.deleted: missing user_id in metadata")
        return

    _get_user_dao().revoke_access(user_id)
    logger.info(f"Stripe: revoked access for user {user_id}")


def _get_stripe_subscription_expire(subscription_id: str) -> datetime:
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        if hasattr(sub, "current_period_end") and sub.current_period_end:
            ts = sub.current_period_end
        else:
            ts = sub["items"]["data"][0]["current_period_end"]
        return datetime.utcfromtimestamp(ts)
    except Exception as exc:
        logger.warning(f"Stripe: could not fetch subscription {subscription_id}: {exc}")
        return datetime.now()
