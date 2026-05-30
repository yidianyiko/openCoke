from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping

from agno.models.openai.like import OpenAILike

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_INTERACTION_MODEL = "zai-org/GLM-5.1"
DEFAULT_INTERPRETER_MODEL = "zai-org/GLM-5.1"
DEFAULT_DETECTOR_MODEL = "zai-org/GLM-5.1"


class LLMConfigurationError(RuntimeError):
    """Raised when required LLM runtime configuration is missing."""


@dataclass(frozen=True, slots=True)
class SiliconFlowLLMConfig:
    api_key: str
    base_url: str = SILICONFLOW_BASE_URL
    interaction_model: str = DEFAULT_INTERACTION_MODEL
    interpreter_model: str = DEFAULT_INTERPRETER_MODEL
    detector_model: str = DEFAULT_DETECTOR_MODEL
    agno_database_url: str | None = None
    agno_create_schema: bool = False

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> SiliconFlowLLMConfig:
        source = os.environ if environ is None else environ
        api_key = _required(source, "SiliconFlow_API_KEY")
        return cls(
            api_key=api_key,
            base_url=(
                source.get("SILICONFLOW_BASE_URL") or SILICONFLOW_BASE_URL
            ).strip(),
            interaction_model=_optional_model(
                source, "COKE_INTERACTION_MODEL", DEFAULT_INTERACTION_MODEL
            ),
            interpreter_model=_optional_model(
                source, "COKE_INTERPRETER_MODEL", DEFAULT_INTERPRETER_MODEL
            ),
            detector_model=_optional_model(
                source, "COKE_DETECTOR_MODEL", DEFAULT_DETECTOR_MODEL
            ),
            agno_database_url=_optional_database_url(source),
            agno_create_schema=_bool_env(source, "COKE_AGNO_CREATE_SCHEMA"),
        )

    def create_interaction_model(self) -> OpenAILike:
        return self._create_model(self.interaction_model)

    def create_interpreter_model(self) -> OpenAILike:
        return self._create_model(self.interpreter_model)

    def create_detector_model(self) -> OpenAILike:
        return self._create_model(
            self.detector_model,
            extra_body={"enable_thinking": False},
        )

    def _create_model(
        self,
        model_id: str,
        *,
        extra_body: dict | None = None,
    ) -> OpenAILike:
        return OpenAILike(
            id=model_id,
            api_key=self.api_key,
            base_url=self.base_url,
            extra_body=extra_body,
        )


def _required(source: Mapping[str, str], key: str) -> str:
    value = (source.get(key) or "").strip()
    if not value:
        raise LLMConfigurationError(f"{key} is required for SiliconFlow LLM access")
    return value


def _optional_model(source: Mapping[str, str], key: str, default: str) -> str:
    return (source.get(key) or default).strip() or default


def _optional_database_url(source: Mapping[str, str]) -> str | None:
    value = (
        source.get("COKE_AGNO_DATABASE_URL") or source.get("DATABASE_URL") or ""
    ).strip()
    return value or None


def _bool_env(source: Mapping[str, str], key: str) -> bool:
    value = (source.get(key) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}
