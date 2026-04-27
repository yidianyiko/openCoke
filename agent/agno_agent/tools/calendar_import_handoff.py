from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests


class CalendarImportHandoffError(RuntimeError):
    pass


def _read_api_url() -> str:
    explicit = os.environ.get("CALENDAR_IMPORT_HANDOFF_API_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    base = (
        os.environ.get("COKE_GATEWAY_API_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_COKE_API_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_API_URL", "").strip()
    )
    if not base:
        try:
            from conf.config import CONF

            identity_api_url = str(
                CONF.get("clawscale_bridge", {}).get("identity_api_url") or ""
            ).strip()
            if identity_api_url:
                parsed = urlsplit(identity_api_url)
                return urlunsplit(
                    (
                        parsed.scheme,
                        parsed.netloc,
                        "/api/internal/calendar-import-handoffs",
                        "",
                        "",
                    )
                )
        except Exception:
            pass
        raise CalendarImportHandoffError("handoff_api_url_missing")
    return f"{base.rstrip('/')}/api/internal/calendar-import-handoffs"


def _read_api_key() -> str:
    api_key = (
        os.environ.get("CALENDAR_IMPORT_HANDOFF_API_KEY", "").strip()
        or os.environ.get("CLAWSCALE_IDENTITY_API_KEY", "").strip()
    )
    if not api_key:
        try:
            from conf.config import CONF

            api_key = str(
                CONF.get("clawscale_bridge", {}).get("identity_api_key") or ""
            ).strip()
        except Exception:
            api_key = ""
    if not api_key:
        raise CalendarImportHandoffError("handoff_api_key_missing")
    return api_key


def create_calendar_import_handoff_link(payload: dict[str, Any]) -> str:
    response = requests.post(
        _read_api_url(),
        json=payload,
        headers={
            "Authorization": f"Bearer {_read_api_key()}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict) or body.get("ok") is not True:
        error = body.get("error") if isinstance(body, dict) else None
        raise CalendarImportHandoffError(str(error or "handoff_link_create_failed"))
    data = body.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("url"), str):
        raise CalendarImportHandoffError("invalid_handoff_link_response")
    return data["url"]
