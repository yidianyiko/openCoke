from __future__ import annotations

import logging
from typing import Protocol
from urllib.parse import urlencode

import httpx

LOGGER = logging.getLogger(__name__)
RESEND_EMAILS_URL = "https://api.resend.com/emails"


class CustomerEmailSender(Protocol):
    def send_verification(self, to: str, token: str, email: str) -> None: ...

    def send_password_reset(self, to: str, token: str) -> None: ...

    def send_claim(self, to: str, token: str) -> None: ...


class ResendEmailSender:
    def __init__(
        self,
        *,
        api_key: str,
        email_from: str,
        email_from_name: str | None,
        public_base_url: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._email_from = email_from
        self._email_from_name = email_from_name
        self._public_base_url = public_base_url.rstrip("/")
        self._transport = transport

    def send_verification(self, to: str, token: str, email: str) -> None:
        self._send(
            to=to,
            subject="Verify your email",
            html=f'<a href="{self._verification_url(token, email)}">Verify your email</a>',
        )

    def send_password_reset(self, to: str, token: str) -> None:
        self._send(
            to=to,
            subject="Reset your password",
            html=(
                f'<a href="{self._url("/auth/reset-password", {"token": token})}">'
                "Reset your password</a>"
            ),
        )

    def send_claim(self, to: str, token: str) -> None:
        self._send(
            to=to,
            subject="Claim your account",
            html=(
                f'<a href="{self._url("/auth/claim", {"token": token})}">'
                "Claim your account</a>"
            ),
        )

    def _verification_url(self, token: str, email: str) -> str:
        return self._url("/auth/verify-email", {"token": token, "email": email})

    def _url(self, path: str, query: dict[str, str]) -> str:
        return f"{self._public_base_url}{path}?{urlencode(query)}"

    def _send(self, *, to: str, subject: str, html: str) -> None:
        payload = {
            "from": self._formatted_from(),
            "to": to,
            "subject": subject,
            "html": html,
        }
        with httpx.Client(transport=self._transport) as client:
            response = client.post(
                RESEND_EMAILS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"resend_send_failed:{response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise RuntimeError("resend_send_failed:invalid_response") from error
        if not body.get("id"):
            raise RuntimeError("resend_send_failed:missing_id")

    def _formatted_from(self) -> str:
        if not self._email_from_name:
            return self._email_from
        return f'"{self._email_from_name}" <{self._email_from}>'


class NullEmailSender:
    def send_verification(self, to: str, token: str, email: str) -> None:
        self._log_noop("verification", to)

    def send_password_reset(self, to: str, token: str) -> None:
        self._log_noop("password_reset", to)

    def send_claim(self, to: str, token: str) -> None:
        self._log_noop("claim", to)

    def _log_noop(self, email_type: str, to: str) -> None:
        LOGGER.info("email_send_skipped", extra={"email_type": email_type, "to": to})
