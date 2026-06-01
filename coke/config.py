from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from coke.llm.config import (
    DEFAULT_ASR_MODEL,
    DEFAULT_DETECTOR_MODEL,
    DEFAULT_INTERACTION_MODEL,
    DEFAULT_INTERACTION_TIMEOUT_S,
    DEFAULT_INTERPRETER_MODEL,
    DEFAULT_MEDIA_MODEL_TIMEOUT_S,
    DEFAULT_VISION_TEXT_MODEL,
    SILICONFLOW_BASE_URL,
)


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
    wechat_ecloud_endpoint_url: str | None = None
    wechat_ecloud_token: str | None = None
    wechat_ecloud_app_id: str | None = None
    linq_endpoint_url: str | None = None
    linq_api_key: str | None = None
    siliconflow_api_key: str | None = None
    siliconflow_base_url: str = SILICONFLOW_BASE_URL
    interaction_model: str = DEFAULT_INTERACTION_MODEL
    interpreter_model: str = DEFAULT_INTERPRETER_MODEL
    detector_model: str = DEFAULT_DETECTOR_MODEL
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
    scheduler_interval_s: int = 60
    webhook_inbound_secret: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environ is None else environ

        database_url = (source.get("DATABASE_URL") or "").strip()
        redis_url = (source.get("REDIS_URL") or "").strip()
        app_env = (source.get("APP_ENV") or "local").strip() or "local"
        raw_public_base_url = _optional(source, "COKE_PUBLIC_BASE_URL")
        public_base_url = (
            raw_public_base_url.rstrip("/")
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
        siliconflow_api_key = _optional(source, "SiliconFlow_API_KEY")
        if app_env == "production" and not llm_fake and not siliconflow_api_key:
            raise ConfigurationError(
                "SiliconFlow_API_KEY is required for production LLM startup"
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
            wechat_ecloud_endpoint_url=_optional(
                source, "COKE_PROVIDER_WECHAT_ECLOUD_ENDPOINT_URL"
            ),
            wechat_ecloud_token=_optional(source, "COKE_PROVIDER_WECHAT_ECLOUD_TOKEN"),
            wechat_ecloud_app_id=_optional(
                source, "COKE_PROVIDER_WECHAT_ECLOUD_APP_ID"
            ),
            linq_endpoint_url=_optional(source, "COKE_PROVIDER_LINQ_ENDPOINT_URL"),
            linq_api_key=_optional(source, "COKE_PROVIDER_LINQ_API_KEY"),
            siliconflow_api_key=siliconflow_api_key,
            siliconflow_base_url=(
                _optional(source, "SILICONFLOW_BASE_URL") or SILICONFLOW_BASE_URL
            ),
            interaction_model=(
                _optional(source, "COKE_INTERACTION_MODEL") or DEFAULT_INTERACTION_MODEL
            ),
            interpreter_model=(
                _optional(source, "COKE_INTERPRETER_MODEL") or DEFAULT_INTERPRETER_MODEL
            ),
            detector_model=(
                _optional(source, "COKE_DETECTOR_MODEL") or DEFAULT_DETECTOR_MODEL
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
            asr_model=_optional(source, "COKE_ASR_MODEL") or DEFAULT_ASR_MODEL,
            vision_text_model=(
                _optional(source, "COKE_VISION_TEXT_MODEL") or DEFAULT_VISION_TEXT_MODEL
            ),
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
            scheduler_interval_s=_positive_int(source, "COKE_SCHEDULER_INTERVAL_S", 60),
            webhook_inbound_secret=_optional(source, "COKE_WEBHOOK_INBOUND_SECRET"),
        )


def _optional(source: Mapping[str, str], key: str) -> str | None:
    value = (source.get(key) or "").strip()
    return value or None


def _bool_env(source: Mapping[str, str], key: str) -> bool:
    value = (source.get(key) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


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
