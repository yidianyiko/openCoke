from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse

from coke.llm.config import (
    DEEPSEEK_BASE_URL,
    DEFAULT_ASR_MODEL,
    DEFAULT_DETECTOR_MODEL,
    DEFAULT_DETECTOR_PROVIDER,
    DEFAULT_EXPRESS_MODEL,
    DEFAULT_EXPRESS_PROVIDER,
    DEFAULT_INTERACTION_MODEL,
    DEFAULT_INTERACTION_TIMEOUT_S,
    DEFAULT_MEDIA_MODEL_TIMEOUT_S,
    DEFAULT_PLANNER_MODEL,
    DEFAULT_VISION_TEXT_MODEL,
    SILICONFLOW_BASE_URL,
    TEXT_PROVIDER_DEEPSEEK,
    TEXT_PROVIDERS,
    ZAI_BASE_URL,
)

# WeChat personal sends go worker -> connector -> upstream iLink synchronously.
# The connector allows up to ~60s upstream (2x30s iLink) under gunicorn
# --timeout 90, so the worker-side send timeout must exceed slow-but-successful
# iLink calls instead of false-failing at 10s. Kept below the 60s stream reclaim
# idle so an in-flight send is never re-delivered to a second worker.
DEFAULT_WECHAT_PERSONAL_SEND_TIMEOUT_S = 45.0


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    app_env: str = "local"
    public_base_url: str = "http://localhost:4040"
    evolution_base_url: str | None = None
    evolution_api_key: str | None = None
    evolution_instance: str | None = None
    wechat_personal_endpoint_url: str | None = None
    wechat_personal_api_key: str | None = None
    wechat_personal_send_timeout_s: float = DEFAULT_WECHAT_PERSONAL_SEND_TIMEOUT_S
    wechat_ecloud_endpoint_url: str | None = None
    wechat_ecloud_token: str | None = None
    wechat_ecloud_app_id: str | None = None
    linq_endpoint_url: str | None = None
    linq_api_key: str | None = None
    resend_api_key: str | None = None
    email_from: str = "noreply@keep4oforever.com"
    email_from_name: str | None = None
    email_auth_enabled: bool = True
    zai_api_key: str | None = None
    zai_base_url: str = ZAI_BASE_URL
    deepseek_api_key: str | None = None
    deepseek_base_url: str = DEEPSEEK_BASE_URL
    siliconflow_api_key: str | None = None
    siliconflow_base_url: str = SILICONFLOW_BASE_URL
    interaction_model: str = DEFAULT_INTERACTION_MODEL
    planner_model: str = DEFAULT_PLANNER_MODEL
    detector_provider: str = DEFAULT_DETECTOR_PROVIDER
    detector_model: str = DEFAULT_DETECTOR_MODEL
    express_provider: str = DEFAULT_EXPRESS_PROVIDER
    express_model: str = DEFAULT_EXPRESS_MODEL
    interaction_timeout_s: float = DEFAULT_INTERACTION_TIMEOUT_S
    agno_database_url: str | None = None
    agno_create_schema: bool = False
    asr_model: str | None = DEFAULT_ASR_MODEL
    vision_text_model: str | None = DEFAULT_VISION_TEXT_MODEL
    media_model_timeout_s: float = DEFAULT_MEDIA_MODEL_TIMEOUT_S
    llm_fake: bool = False
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_calendar_id: str = "primary"
    lock_ttl_ms: int = 30_000
    work_stream_name: str = "coke.work"
    work_group_name: str = "workers"
    work_consumer_name: str = "worker-1"
    reply_channel_prefix: str = "coke:reply"
    outbox_relay_poll_interval_s: float = 1.0
    worker_block_ms: int = 1000
    worker_reclaim_idle_ms: int = 60_000
    waiting_reply_after_seconds: int = 20
    # The scheduler scans for due reminders on this interval, so it bounds the
    # detection lag before a fired reminder is even enqueued (avg ~interval/2).
    # At 60s that lag was the largest single component of reminder fire->send
    # latency (measured p50 ~37s of a ~58s total); 15s cuts ~30s off every
    # reminder while keeping the indexed due_at scan cheap.
    scheduler_interval_s: int = 15
    webhook_inbound_secret: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environ is None else environ

        database_url = (source.get("DATABASE_URL") or "").strip()
        redis_url = (source.get("REDIS_URL") or "").strip()
        app_env = (source.get("APP_ENV") or "local").strip() or "local"
        raw_public_base_url = _optional(source, "COKE_PUBLIC_BASE_URL")
        public_base_url = (
            _normalize_public_base_url(raw_public_base_url)
            if raw_public_base_url is not None
            else None
        )

        if not database_url:
            raise ConfigurationError(
                "DATABASE_URL is required for Coke backend startup"
            )
        if not redis_url:
            raise ConfigurationError("REDIS_URL is required for Coke backend startup")
        if app_env == "production" and not public_base_url:
            raise ConfigurationError(
                "COKE_PUBLIC_BASE_URL is required for production public links"
            )

        llm_fake = _bool_env(source, "COKE_LLM_FAKE")
        resend_api_key = _optional(source, "RESEND_API_KEY")
        email_auth_enabled = _bool_env_default(
            source, "COKE_EMAIL_AUTH_ENABLED", default=True
        )
        if app_env == "production" and email_auth_enabled and not resend_api_key:
            raise ConfigurationError(
                "RESEND_API_KEY is required for production email delivery"
            )
        zai_api_key = _optional(source, "ZAI_API_KEY")
        siliconflow_api_key = _optional(source, "SiliconFlow_API_KEY")
        asr_model = _optional(source, "COKE_ASR_MODEL") or DEFAULT_ASR_MODEL
        vision_text_model = (
            _optional(source, "COKE_VISION_TEXT_MODEL") or DEFAULT_VISION_TEXT_MODEL
        )
        if app_env == "production" and not llm_fake and not zai_api_key:
            raise ConfigurationError(
                "ZAI_API_KEY is required for production LLM startup"
            )
        deepseek_api_key = _optional(source, "DEEPSEEK_API_KEY")
        detector_provider = _text_provider(
            source, "COKE_DETECTOR_PROVIDER", DEFAULT_DETECTOR_PROVIDER
        )
        express_provider = _text_provider(
            source, "COKE_EXPRESS_PROVIDER", DEFAULT_EXPRESS_PROVIDER
        )
        if (
            app_env == "production"
            and not llm_fake
            and TEXT_PROVIDER_DEEPSEEK in {detector_provider, express_provider}
            and not deepseek_api_key
        ):
            raise ConfigurationError(
                "DEEPSEEK_API_KEY is required for production DeepSeek text roles"
            )
        if (
            app_env == "production"
            and not llm_fake
            and (asr_model or vision_text_model)
            and not siliconflow_api_key
        ):
            raise ConfigurationError(
                "SiliconFlow_API_KEY is required for production media model startup"
            )

        return cls(
            database_url=database_url,
            redis_url=redis_url,
            app_env=app_env,
            public_base_url=public_base_url or "http://localhost:4040",
            evolution_base_url=_optional(source, "COKE_PROVIDER_EVOLUTION_BASE_URL"),
            evolution_api_key=_optional(source, "COKE_PROVIDER_EVOLUTION_API_KEY"),
            evolution_instance=_optional(source, "COKE_PROVIDER_EVOLUTION_INSTANCE"),
            wechat_personal_endpoint_url=_optional(
                source, "COKE_PROVIDER_WECHAT_PERSONAL_ENDPOINT_URL"
            ),
            wechat_personal_api_key=_optional(
                source, "COKE_PROVIDER_WECHAT_PERSONAL_API_KEY"
            ),
            wechat_personal_send_timeout_s=_positive_float(
                source,
                "COKE_PROVIDER_WECHAT_PERSONAL_SEND_TIMEOUT_S",
                DEFAULT_WECHAT_PERSONAL_SEND_TIMEOUT_S,
            ),
            wechat_ecloud_endpoint_url=_optional(
                source, "COKE_PROVIDER_WECHAT_ECLOUD_ENDPOINT_URL"
            ),
            wechat_ecloud_token=_optional(source, "COKE_PROVIDER_WECHAT_ECLOUD_TOKEN"),
            wechat_ecloud_app_id=_optional(
                source, "COKE_PROVIDER_WECHAT_ECLOUD_APP_ID"
            ),
            linq_endpoint_url=_optional(source, "COKE_PROVIDER_LINQ_ENDPOINT_URL"),
            linq_api_key=_optional(source, "COKE_PROVIDER_LINQ_API_KEY"),
            resend_api_key=resend_api_key,
            email_from=(_optional(source, "EMAIL_FROM") or "noreply@keep4oforever.com"),
            email_from_name=_optional(source, "EMAIL_FROM_NAME"),
            email_auth_enabled=email_auth_enabled,
            zai_api_key=zai_api_key,
            zai_base_url=_optional(source, "ZAI_BASE_URL") or ZAI_BASE_URL,
            deepseek_api_key=deepseek_api_key,
            deepseek_base_url=(
                _optional(source, "DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL
            ),
            siliconflow_api_key=siliconflow_api_key,
            siliconflow_base_url=(
                _optional(source, "SILICONFLOW_BASE_URL") or SILICONFLOW_BASE_URL
            ),
            interaction_model=(
                _optional(source, "COKE_INTERACTION_MODEL") or DEFAULT_INTERACTION_MODEL
            ),
            planner_model=(
                _optional(source, "COKE_PLANNER_MODEL") or DEFAULT_PLANNER_MODEL
            ),
            detector_provider=detector_provider,
            detector_model=(
                _optional(source, "COKE_DETECTOR_MODEL") or DEFAULT_DETECTOR_MODEL
            ),
            express_provider=express_provider,
            express_model=(
                _optional(source, "COKE_EXPRESS_MODEL") or DEFAULT_EXPRESS_MODEL
            ),
            interaction_timeout_s=_positive_float(
                source,
                "COKE_INTERACTION_TIMEOUT_S",
                DEFAULT_INTERACTION_TIMEOUT_S,
            ),
            agno_database_url=(
                _optional(source, "COKE_AGNO_DATABASE_URL") or database_url
            ),
            agno_create_schema=_bool_env(source, "COKE_AGNO_CREATE_SCHEMA"),
            asr_model=asr_model,
            vision_text_model=vision_text_model,
            media_model_timeout_s=_positive_float(
                source,
                "COKE_MEDIA_MODEL_TIMEOUT_S",
                DEFAULT_MEDIA_MODEL_TIMEOUT_S,
            ),
            llm_fake=llm_fake,
            google_client_id=_optional(source, "COKE_GOOGLE_CLIENT_ID"),
            google_client_secret=_optional(source, "COKE_GOOGLE_CLIENT_SECRET"),
            google_calendar_id=_optional(source, "COKE_GOOGLE_CALENDAR_ID")
            or "primary",
            lock_ttl_ms=_positive_int(source, "COKE_LOCK_TTL_MS", 30_000),
            work_stream_name=_optional(source, "COKE_WORK_STREAM") or "coke.work",
            work_group_name=_optional(source, "COKE_WORK_GROUP") or "workers",
            work_consumer_name=(_optional(source, "COKE_WORK_CONSUMER") or "worker-1"),
            reply_channel_prefix=(
                _optional(source, "COKE_REPLY_CHANNEL_PREFIX") or "coke:reply"
            ),
            outbox_relay_poll_interval_s=_positive_float(
                source, "COKE_OUTBOX_RELAY_POLL_INTERVAL_S", 1.0
            ),
            worker_block_ms=_positive_int(source, "COKE_WORKER_BLOCK_MS", 1000),
            worker_reclaim_idle_ms=_positive_int(
                source, "COKE_WORKER_RECLAIM_IDLE_MS", 60_000
            ),
            waiting_reply_after_seconds=_positive_int(
                source, "COKE_WAITING_REPLY_AFTER_SECONDS", 20
            ),
            scheduler_interval_s=_positive_int(source, "COKE_SCHEDULER_INTERVAL_S", 15),
            webhook_inbound_secret=_optional(source, "COKE_WEBHOOK_INBOUND_SECRET"),
        )


def _optional(source: Mapping[str, str], key: str) -> str | None:
    value = (source.get(key) or "").strip()
    return value or None


def _text_provider(source: Mapping[str, str], key: str, default: str) -> str:
    value = (source.get(key) or default).strip().lower()
    if value not in TEXT_PROVIDERS:
        raise ConfigurationError(
            f"{key} must be one of {', '.join(sorted(TEXT_PROVIDERS))}"
        )
    return value


def _normalize_public_base_url(raw_value: str) -> str | None:
    value = raw_value.rstrip("/")
    if not value:
        return None

    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except ValueError as error:
        raise ConfigurationError(
            "COKE_PUBLIC_BASE_URL must be an absolute http(s) URL without query or fragment"
        ) from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(
            "COKE_PUBLIC_BASE_URL must be an absolute http(s) URL without query or fragment"
        )
    return value


def _bool_env(source: Mapping[str, str], key: str) -> bool:
    value = (source.get(key) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _bool_env_default(source: Mapping[str, str], key: str, default: bool) -> bool:
    raw = _optional(source, key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(source: Mapping[str, str], key: str, default: int) -> int:
    raw = _optional(source, key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError(f"{key} must be a positive integer") from error
    if value <= 0:
        raise ConfigurationError(f"{key} must be a positive integer")
    return value


def _positive_float(source: Mapping[str, str], key: str, default: float) -> float:
    raw = _optional(source, key)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigurationError(f"{key} must be a positive number") from error
    if value <= 0:
        raise ConfigurationError(f"{key} must be a positive number")
    return value
