from __future__ import annotations

import pytest

import coke.llm.config as llm_config
from coke.llm.config import (
    DEFAULT_ASR_MODEL,
    DEFAULT_DETECTOR_MODEL,
    DEFAULT_INTERACTION_MODEL,
    DEFAULT_INTERACTION_TIMEOUT_S,
    DEFAULT_PLANNER_MODEL,
    DEFAULT_VISION_TEXT_MODEL,
    SILICONFLOW_BASE_URL,
    ZAI_BASE_URL,
    LLMConfigurationError,
    SiliconFlowMediaConfig,
    ZAILLMConfig,
)


def test_zai_config_reads_key_base_url_and_default_model_ids():
    config = ZAILLMConfig.from_env(
        {
            "ZAI_API_KEY": "test-key",
            "DATABASE_URL": "postgresql+psycopg://coke:coke@localhost/coke",
        }
    )

    assert config.api_key == "test-key"
    assert config.base_url == ZAI_BASE_URL
    assert config.base_url == "https://api.z.ai/api/coding/paas/v4/"
    assert config.interaction_model == DEFAULT_INTERACTION_MODEL
    assert config.interaction_model == "glm-5.2"
    assert config.planner_model == DEFAULT_PLANNER_MODEL
    assert config.planner_model == "glm-5.2"
    assert config.detector_model == DEFAULT_DETECTOR_MODEL
    assert config.detector_model == "glm-5.2"
    assert llm_config.DEFAULT_INTERACTION_TIMEOUT_S == 45.0
    assert config.interaction_timeout_s == DEFAULT_INTERACTION_TIMEOUT_S
    assert config.agno_database_url == "postgresql+psycopg://coke:coke@localhost/coke"


def test_zai_config_allows_model_and_agno_database_overrides():
    config = ZAILLMConfig.from_env(
        {
            "ZAI_API_KEY": "test-key",
            "ZAI_BASE_URL": "https://zai.example/v4/",
            "COKE_INTERACTION_MODEL": "custom-interaction",
            "COKE_PLANNER_MODEL": "custom-planner",
            "COKE_DETECTOR_MODEL": "custom-detector",
            "COKE_INTERACTION_TIMEOUT_S": "12.5",
            "COKE_AGNO_DATABASE_URL": "postgresql+psycopg://agno:agno@localhost/agno",
        }
    )

    assert config.base_url == "https://zai.example/v4/"
    assert config.interaction_model == "custom-interaction"
    assert config.planner_model == "custom-planner"
    assert config.detector_model == "custom-detector"
    assert config.interaction_timeout_s == 12.5
    assert config.agno_database_url == "postgresql+psycopg://agno:agno@localhost/agno"


def test_zai_config_requires_api_key():
    with pytest.raises(LLMConfigurationError, match="ZAI_API_KEY"):
        ZAILLMConfig.from_env({})


def test_zai_config_rejects_invalid_interaction_timeout():
    with pytest.raises(LLMConfigurationError, match="COKE_INTERACTION_TIMEOUT_S"):
        ZAILLMConfig.from_env(
            {
                "ZAI_API_KEY": "test-key",
                "COKE_INTERACTION_TIMEOUT_S": "0",
            }
        )


def test_openai_like_model_uses_zai_settings_and_interaction_timeout():
    config = ZAILLMConfig.from_env(
        {
            "ZAI_API_KEY": "test-key",
            "COKE_INTERACTION_MODEL": "custom-interaction-model",
            "COKE_DETECTOR_MODEL": "custom-detector-model",
            "COKE_INTERACTION_TIMEOUT_S": "31.5",
        }
    )

    interaction_model = config.create_interaction_model()
    planner_model = config.create_planner_model()
    model = config.create_detector_model()

    assert interaction_model.id == "custom-interaction-model"
    assert interaction_model.timeout == 31.5
    # Thinking is disabled on every turn-path model, not just the detector:
    # GLM-5.2 thinking mode leaks reasoning into final content and breaks the
    # JSON output protocol (forcing full agent re-runs) while inflating latency.
    assert interaction_model.extra_body == {"thinking": {"type": "disabled"}}
    # Every turn-path text model is on the user's reply critical path, so each
    # must carry the same bounded per-request timeout. Without it the OpenAI
    # client falls back to its ~600s default and a single stalled Z.AI request
    # blocks the whole turn for minutes. See
    # docs/issues/2026-06-09-turn-latency-uncapped-interpreter-timeout.md.
    assert planner_model.timeout == 31.5
    assert planner_model.extra_body == {"thinking": {"type": "disabled"}}
    assert model.id == "custom-detector-model"
    assert str(model.base_url) == ZAI_BASE_URL
    assert model.api_key == "test-key"
    assert model.timeout == 31.5
    assert model.extra_body == {"thinking": {"type": "disabled"}}


def test_siliconflow_media_config_reads_model_ids_without_defaults():
    config = SiliconFlowMediaConfig.from_env(
        {
            "SiliconFlow_API_KEY": "test-key",
            "SILICONFLOW_BASE_URL": "https://sf.example/v1",
            "COKE_ASR_MODEL": "sensevoice-candidate",
            "COKE_VISION_TEXT_MODEL": "qwen-vl-candidate",
            "COKE_MEDIA_MODEL_TIMEOUT_S": "70",
        }
    )

    assert config.api_key == "test-key"
    assert config.base_url == "https://sf.example/v1"
    assert config.asr_model == "sensevoice-candidate"
    assert config.vision_text_model == "qwen-vl-candidate"
    assert config.media_model_timeout_s == 70.0


def test_siliconflow_media_config_defaults_to_verified_siliconflow_models():
    config = SiliconFlowMediaConfig.from_env({"SiliconFlow_API_KEY": "test-key"})

    assert config.base_url == SILICONFLOW_BASE_URL
    assert config.asr_model == DEFAULT_ASR_MODEL
    assert config.vision_text_model == DEFAULT_VISION_TEXT_MODEL


def test_siliconflow_media_config_requires_api_key():
    with pytest.raises(LLMConfigurationError, match="SiliconFlow_API_KEY"):
        SiliconFlowMediaConfig.from_env({})
