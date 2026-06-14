from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from agno.models.openai.like import OpenAILike

# Official Z.AI OpenAI-compatible endpoint and thinking-off request shape were
# verified against Z.AI docs on 2026-06-09. All turn-path models (interaction,
# planner, detector) keep GLM-5.1 thinking disabled: thinking mode breaks the
# JSON output protocol and inflates latency without a verified quality gain.
ZAI_BASE_URL = "https://api.z.ai/api/paas/v4/"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
TEXT_PROVIDER_ZAI = "zai"
TEXT_PROVIDER_DEEPSEEK = "deepseek"
TEXT_PROVIDERS = frozenset({TEXT_PROVIDER_ZAI, TEXT_PROVIDER_DEEPSEEK})
DEFAULT_DETECTOR_PROVIDER = TEXT_PROVIDER_ZAI
DEFAULT_EXPRESS_PROVIDER = TEXT_PROVIDER_ZAI
DEFAULT_INTERACTION_MODEL = "glm-5.1"
DEFAULT_PLANNER_MODEL = "glm-5.1"
DEFAULT_DETECTOR_MODEL = "glm-5.1"
DEFAULT_EXPRESS_MODEL = DEFAULT_INTERACTION_MODEL
DEFAULT_INTERACTION_TIMEOUT_S = 45.0
DEFAULT_MEDIA_MODEL_TIMEOUT_S = 60.0
# Media-model defaults verified live against /v1/models on 2026-06-01 using the
# actual client request shapes: Qwen3-VL-32B-Instruct returned a correct image
# caption via /chat/completions, and SenseVoiceSmall returned HTTP 200 on
# /audio/transcriptions. Voice's primary path is WeChat's native transcript;
# SenseVoiceSmall is the fallback. Tunable later via the media subset eval.
DEFAULT_ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"
DEFAULT_VISION_TEXT_MODEL = "Qwen/Qwen3-VL-32B-Instruct"


class LLMConfigurationError(RuntimeError):
    """Raised when required LLM runtime configuration is missing."""


@dataclass(frozen=True, slots=True)
class ZAILLMConfig:
    api_key: str
    base_url: str = ZAI_BASE_URL
    deepseek_api_key: str | None = None
    deepseek_base_url: str = DEEPSEEK_BASE_URL
    interaction_model: str = DEFAULT_INTERACTION_MODEL
    planner_model: str = DEFAULT_PLANNER_MODEL
    detector_provider: str = DEFAULT_DETECTOR_PROVIDER
    detector_model: str = DEFAULT_DETECTOR_MODEL
    express_provider: str = DEFAULT_EXPRESS_PROVIDER
    express_model: str = DEFAULT_EXPRESS_MODEL
    interaction_timeout_s: float = DEFAULT_INTERACTION_TIMEOUT_S
    agno_database_url: str | None = None
    agno_create_schema: bool = False

    def __post_init__(self) -> None:
        _validate_provider(self.detector_provider, "COKE_DETECTOR_PROVIDER")
        _validate_provider(self.express_provider, "COKE_EXPRESS_PROVIDER")
        if (
            TEXT_PROVIDER_DEEPSEEK in {self.detector_provider, self.express_provider}
            and not (self.deepseek_api_key or "").strip()
        ):
            raise LLMConfigurationError(
                "DEEPSEEK_API_KEY is required for DeepSeek text roles"
            )

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> ZAILLMConfig:
        source = os.environ if environ is None else environ
        api_key = _required(source, "ZAI_API_KEY", purpose="Z.AI LLM access")
        return cls(
            api_key=api_key,
            base_url=(source.get("ZAI_BASE_URL") or ZAI_BASE_URL).strip(),
            deepseek_api_key=_optional_secret(source, "DEEPSEEK_API_KEY"),
            deepseek_base_url=(
                source.get("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL
            ).strip(),
            interaction_model=_optional_model(
                source, "COKE_INTERACTION_MODEL", DEFAULT_INTERACTION_MODEL
            ),
            planner_model=_optional_model(
                source, "COKE_PLANNER_MODEL", DEFAULT_PLANNER_MODEL
            ),
            detector_provider=_optional_provider(
                source, "COKE_DETECTOR_PROVIDER", DEFAULT_DETECTOR_PROVIDER
            ),
            detector_model=_optional_model(
                source, "COKE_DETECTOR_MODEL", DEFAULT_DETECTOR_MODEL
            ),
            express_provider=_optional_provider(
                source, "COKE_EXPRESS_PROVIDER", DEFAULT_EXPRESS_PROVIDER
            ),
            express_model=_optional_model(
                source, "COKE_EXPRESS_MODEL", DEFAULT_EXPRESS_MODEL
            ),
            interaction_timeout_s=_positive_float(
                source,
                "COKE_INTERACTION_TIMEOUT_S",
                DEFAULT_INTERACTION_TIMEOUT_S,
            ),
            agno_database_url=_optional_database_url(source),
            agno_create_schema=_bool_env(source, "COKE_AGNO_CREATE_SCHEMA"),
        )

    def create_interaction_model(self) -> OpenAILike:
        # Z.AI GLM-5.1 defaults to thinking enabled. Coke's turn path needs
        # structured JSON and bounded latency, so all three text roles disable it.
        return self._create_model(
            self.interaction_model,
            provider=TEXT_PROVIDER_ZAI,
            timeout=self.interaction_timeout_s,
            extra_body=_thinking_disabled_body(),
        )

    def create_planner_model(self) -> OpenAILike:
        # Planner and detector run on the same user-reply critical path as
        # interaction, so they share the same bounded per-request timeout. Left
        # unbounded, the OpenAI client falls back to its ~600s default and a
        # single stalled Z.AI request blocks the whole turn for minutes.
        return self._create_model(
            self.planner_model,
            provider=TEXT_PROVIDER_ZAI,
            timeout=self.interaction_timeout_s,
            extra_body=_thinking_disabled_body(),
        )

    def create_detector_model(self) -> OpenAILike:
        return self._create_model(
            self.detector_model,
            provider=self.detector_provider,
            timeout=self.interaction_timeout_s,
            extra_body=_thinking_disabled_body(),
        )

    def create_express_model(self) -> OpenAILike:
        return self._create_model(
            self.express_model,
            provider=self.express_provider,
            timeout=self.interaction_timeout_s,
            extra_body=_thinking_disabled_body(),
        )

    def _create_model(
        self,
        model_id: str,
        *,
        provider: str,
        extra_body: dict | None = None,
        timeout: float | None = None,
    ) -> OpenAILike:
        api_key, base_url = self._provider_credentials(provider)
        kwargs = {
            "id": model_id,
            "api_key": api_key,
            "base_url": base_url,
            "extra_body": extra_body,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        return OpenAILike(**kwargs)

    def _provider_credentials(self, provider: str) -> tuple[str, str]:
        if provider == TEXT_PROVIDER_ZAI:
            return self.api_key, self.base_url
        if provider == TEXT_PROVIDER_DEEPSEEK:
            api_key = (self.deepseek_api_key or "").strip()
            if not api_key:
                raise LLMConfigurationError(
                    "DEEPSEEK_API_KEY is required for DeepSeek text roles"
                )
            return api_key, self.deepseek_base_url
        raise LLMConfigurationError(
            f"unknown text provider {provider!r}; expected one of {sorted(TEXT_PROVIDERS)}"
        )


@dataclass(frozen=True, slots=True)
class SiliconFlowMediaConfig:
    api_key: str
    base_url: str = SILICONFLOW_BASE_URL
    asr_model: str | None = DEFAULT_ASR_MODEL
    vision_text_model: str | None = DEFAULT_VISION_TEXT_MODEL
    media_model_timeout_s: float = DEFAULT_MEDIA_MODEL_TIMEOUT_S

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> SiliconFlowMediaConfig:
        source = os.environ if environ is None else environ
        api_key = _required(
            source,
            "SiliconFlow_API_KEY",
            purpose="SiliconFlow media model access",
        )
        return cls(
            api_key=api_key,
            base_url=(
                source.get("SILICONFLOW_BASE_URL") or SILICONFLOW_BASE_URL
            ).strip(),
            asr_model=_optional_model(source, "COKE_ASR_MODEL", DEFAULT_ASR_MODEL),
            vision_text_model=_optional_model(
                source, "COKE_VISION_TEXT_MODEL", DEFAULT_VISION_TEXT_MODEL
            ),
            media_model_timeout_s=_positive_float(
                source,
                "COKE_MEDIA_MODEL_TIMEOUT_S",
                DEFAULT_MEDIA_MODEL_TIMEOUT_S,
            ),
        )


def _thinking_disabled_body() -> dict:
    return {"thinking": {"type": "disabled"}}


def _required(source: Mapping[str, str], key: str, *, purpose: str) -> str:
    value = (source.get(key) or "").strip()
    if not value:
        raise LLMConfigurationError(f"{key} is required for {purpose}")
    return value


def _optional_secret(source: Mapping[str, str], key: str) -> str | None:
    value = (source.get(key) or "").strip()
    return value or None


def _optional_model(source: Mapping[str, str], key: str, default: str) -> str:
    return (source.get(key) or default).strip() or default


def _optional_provider(source: Mapping[str, str], key: str, default: str) -> str:
    return _validate_provider((source.get(key) or default).strip().lower(), key)


def _validate_provider(value: str, key: str) -> str:
    if value not in TEXT_PROVIDERS:
        raise LLMConfigurationError(
            f"{key} must be one of {', '.join(sorted(TEXT_PROVIDERS))}"
        )
    return value


def _optional_database_url(source: Mapping[str, str]) -> str | None:
    value = (
        source.get("COKE_AGNO_DATABASE_URL") or source.get("DATABASE_URL") or ""
    ).strip()
    return value or None


def _bool_env(source: Mapping[str, str], key: str) -> bool:
    value = (source.get(key) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _positive_float(source: Mapping[str, str], key: str, default: float) -> float:
    raw = (source.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise LLMConfigurationError(f"{key} must be a positive number") from error
    if value <= 0:
        raise LLMConfigurationError(f"{key} must be a positive number")
    return value
