import base64
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


MAX_INBOUND_ATTACHMENTS = 4
MAX_HTTP_URL_LENGTH = 4096
MAX_DATA_URL_BYTES = 2 * 1024 * 1024
MAX_TOTAL_DATA_URL_BYTES = 4 * 1024 * 1024
MAX_ATTACHMENT_JSON_BYTES = 5 * 1024 * 1024
MAX_DISPLAY_FILENAME_LENGTH = 120

TRUSTED_DATA_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "audio/ogg",
    "audio/mpeg",
    "audio/silk",
    "video/mp4",
    "application/pdf",
}

_DATA_URL_RE = re.compile(r"^data:([^;,]+);base64,([A-Za-z0-9+/=]+)$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class NormalizeInboundAttachmentsResult:
    attachments: list[dict]
    rejected: bool = False
    reason: str | None = None


def _read_string(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_size(value) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _normalize_url_input(value: str) -> str:
    return _CONTROL_CHARS_RE.sub("", value).strip()


def _sanitize_display_filename(value: str) -> str:
    sanitized = _CONTROL_CHARS_RE.sub(" ", value)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if not sanitized:
        return "attachment"
    if "data:" in sanitized.lower():
        return "attachment"
    return sanitized[:MAX_DISPLAY_FILENAME_LENGTH]


def _json_footprint_bytes(value) -> int:
    try:
        return len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
    except (TypeError, ValueError, RecursionError):
        return MAX_ATTACHMENT_JSON_BYTES + 1


def _parse_data_url(value: str) -> tuple[str, int] | None:
    match = _DATA_URL_RE.match(value)
    if not match:
        return None

    content_type = match.group(1).lower()
    if content_type not in TRUSTED_DATA_CONTENT_TYPES:
        return None

    payload = match.group(2)
    if len(payload) % 4 != 0:
        return None
    padding_index = payload.find("=")
    if padding_index != -1 and not re.fullmatch(r"=+", payload[padding_index:]):
        return None

    try:
        decoded = base64.b64decode(payload, validate=True)
    except Exception:
        return None

    if base64.b64encode(decoded).decode("ascii") != payload:
        return None
    return content_type, len(decoded)


def _safe_http_display_url(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def normalize_inbound_attachments(
    raw_attachments, allow_data_urls: bool = True
) -> NormalizeInboundAttachmentsResult:
    if not isinstance(raw_attachments, list) or not raw_attachments:
        return NormalizeInboundAttachmentsResult(attachments=[])

    if len(raw_attachments) > MAX_INBOUND_ATTACHMENTS:
        return NormalizeInboundAttachmentsResult(
            attachments=[],
            rejected=True,
            reason="attachment_limit_exceeded",
        )

    if _json_footprint_bytes(raw_attachments) > MAX_ATTACHMENT_JSON_BYTES:
        return NormalizeInboundAttachmentsResult(
            attachments=[],
            rejected=True,
            reason="attachment_payload_too_large",
        )

    total_data_bytes = 0
    attachments = []
    for raw in raw_attachments:
        if not isinstance(raw, dict):
            continue

        raw_url = _read_string(raw.get("url"))
        url = _normalize_url_input(raw_url) if raw_url else None
        if not url:
            continue

        filename = _read_string(raw.get("filename")) or "attachment"
        display_filename = _sanitize_display_filename(filename)
        explicit_content_type = _read_string(raw.get("contentType"))
        size = _read_size(raw.get("size"))

        if url.startswith("data:"):
            if not allow_data_urls:
                continue
            parsed_data = _parse_data_url(url)
            if parsed_data is None:
                continue
            content_type, data_bytes = parsed_data
            if data_bytes > MAX_DATA_URL_BYTES:
                return NormalizeInboundAttachmentsResult(
                    attachments=[],
                    rejected=True,
                    reason="attachment_payload_too_large",
                )
            total_data_bytes += data_bytes
            if total_data_bytes > MAX_TOTAL_DATA_URL_BYTES:
                return NormalizeInboundAttachmentsResult(
                    attachments=[],
                    rejected=True,
                    reason="attachment_payload_too_large",
                )
            attachment = {
                "url": url,
                "contentType": content_type,
                "filename": filename,
                "safeDisplayUrl": (
                    f"[inline {content_type} attachment: {display_filename}]"
                ),
                "size": size if size is not None else data_bytes,
            }
            attachments.append(attachment)
            continue

        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if len(urlunsplit(parsed)) > MAX_HTTP_URL_LENGTH:
            continue

        attachment = {
            "url": urlunsplit(parsed),
            "contentType": explicit_content_type or "application/octet-stream",
            "filename": filename,
            "safeDisplayUrl": _safe_http_display_url(urlunsplit(parsed)),
        }
        if size is not None:
            attachment["size"] = size
        attachments.append(attachment)

    return NormalizeInboundAttachmentsResult(attachments=attachments)


def format_input_with_attachments(text: str | None, attachments: list[dict]) -> str:
    normalized_text = text if isinstance(text, str) else ""
    attachment_lines = [
        f"Attachment: {attachment['safeDisplayUrl']}"
        for attachment in attachments
        if isinstance(attachment, dict) and attachment.get("safeDisplayUrl")
    ]
    attachment_text = "\n".join(attachment_lines)
    if normalized_text and attachment_text:
        return f"{normalized_text}\n\n{attachment_text}"
    if attachment_text:
        return attachment_text
    return normalized_text
