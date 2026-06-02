from __future__ import annotations

import json

import httpx
import pytest

from coke.domains.identity_access.email import ResendEmailSender


def test_resend_sender_posts_verification_email_with_encoded_link_and_from_name():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "email_123"})

    sender = ResendEmailSender(
        api_key="resend_key",
        email_from="noreply@keep4oforever.com",
        email_from_name="Coke Support",
        public_base_url="https://coke.keep4oforever.com/",
        transport=httpx.MockTransport(handler),
    )

    sender.send_verification(
        to="alice@example.com",
        token="verify token+/=",
        email="alice+test@example.com",
    )

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer resend_key"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.read()) == {
        "from": '"Coke Support" <noreply@keep4oforever.com>',
        "to": "alice@example.com",
        "subject": "Verify your email",
        "html": (
            '<a href="https://coke.keep4oforever.com/auth/verify-email'
            '?token=verify+token%2B%2F%3D&email=alice%2Btest%40example.com">'
            "Verify your email</a>"
        ),
    }


def test_resend_sender_posts_password_reset_and_claim_links_without_from_name():
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.read()))
        return httpx.Response(200, json={"id": "email_123"})

    sender = ResendEmailSender(
        api_key="resend_key",
        email_from="noreply@keep4oforever.com",
        email_from_name=None,
        public_base_url="https://coke.keep4oforever.com",
        transport=httpx.MockTransport(handler),
    )

    sender.send_password_reset(to="alice@example.com", token="reset token")
    sender.send_claim(to="alice@example.com", token="claim token")

    assert payloads == [
        {
            "from": "noreply@keep4oforever.com",
            "to": "alice@example.com",
            "subject": "Reset your password",
            "html": (
                '<a href="https://coke.keep4oforever.com/auth/reset-password'
                '?token=reset+token">Reset your password</a>'
            ),
        },
        {
            "from": "noreply@keep4oforever.com",
            "to": "alice@example.com",
            "subject": "Claim your account",
            "html": (
                '<a href="https://coke.keep4oforever.com/auth/claim'
                '?token=claim+token">Claim your account</a>'
            ),
        },
    ]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            httpx.Response(400, json={"message": "bad request"}),
            "resend_send_failed:400",
        ),
        (httpx.Response(200, json={}), "resend_send_failed:missing_id"),
    ],
)
def test_resend_sender_raises_clear_error_on_provider_failure(response, message):
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    sender = ResendEmailSender(
        api_key="resend_key",
        email_from="noreply@keep4oforever.com",
        email_from_name=None,
        public_base_url="https://coke.keep4oforever.com",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeError, match=message):
        sender.send_claim(to="alice@example.com", token="claim token")
