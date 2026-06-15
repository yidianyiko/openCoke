from __future__ import annotations

import pytest

import coke.llm.config as llm_config
from coke.llm.config import (
    DEEPSEEK_BASE_URL,
    DEFAULT_ASR_MODEL,
    DEFAULT_DETECTOR_MODEL,
    DEFAULT_EXPRESS_MODEL,
    DEFAULT_INTERACTION_MODEL,
    DEFAULT_INTERACTION_TIMEOUT_S,
    DEFAULT_PLANNER_MODEL,
    DEFAULT_PLANNER_PROVIDER,
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
    assert config.deepseek_base_url == DEEPSEEK_BASE_URL
    assert config.interaction_model == DEFAULT_INTERACTION_MODEL
    assert config.planner_model == DEFAULT_PLANNER_MODEL
    assert config.detector_model == DEFAULT_DETECTOR_MODEL
    assert config.express_model == DEFAULT_EXPRESS_MODEL
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


@pytest.mark.parametrize(
    "role_provider_env",
    ["COKE_PLANNER_PROVIDER", "COKE_DETECTOR_PROVIDER", "COKE_EXPRESS_PROVIDER"],
)
def test_zai_config_requires_deepseek_key_for_deepseek_roles(role_provider_env):
    with pytest.raises(LLMConfigurationError, match="DEEPSEEK_API_KEY"):
        ZAILLMConfig.from_env(
            {
                "ZAI_API_KEY": "zai-key",
                role_provider_env: "deepseek",
            }
        )


def test_zai_config_allows_deepseek_detector_and_express_role_overrides():
    config = ZAILLMConfig.from_env(
        {
            "ZAI_API_KEY": "zai-key",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "DEEPSEEK_BASE_URL": "https://deepseek.example",
            "COKE_DETECTOR_PROVIDER": "deepseek",
            "COKE_DETECTOR_MODEL": "deepseek-v4-flash",
            "COKE_EXPRESS_PROVIDER": "deepseek",
            "COKE_EXPRESS_MODEL": "deepseek-v4-flash",
            "COKE_INTERACTION_TIMEOUT_S": "31.5",
        }
    )

    interaction_model = config.create_interaction_model()
    planner_model = config.create_planner_model()
    detector_model = config.create_detector_model()
    express_model = config.create_express_model()

    assert interaction_model.id == DEFAULT_INTERACTION_MODEL
    assert interaction_model.api_key == "zai-key"
    assert str(interaction_model.base_url) == ZAI_BASE_URL
    assert planner_model.id == DEFAULT_PLANNER_MODEL
    assert planner_model.api_key == "zai-key"
    assert str(planner_model.base_url) == ZAI_BASE_URL
    assert detector_model.id == "deepseek-v4-flash"
    assert detector_model.api_key == "deepseek-key"
    assert str(detector_model.base_url).rstrip("/") == "https://deepseek.example"
    assert detector_model.timeout == 31.5
    assert detector_model.extra_body == {"thinking": {"type": "disabled"}}
    assert express_model.id == "deepseek-v4-flash"
    assert express_model.api_key == "deepseek-key"
    assert str(express_model.base_url).rstrip("/") == "https://deepseek.example"
    assert express_model.timeout == 31.5
    assert express_model.extra_body == {"thinking": {"type": "disabled"}}


def test_zai_config_allows_deepseek_planner_role_override():
    config = ZAILLMConfig.from_env(
        {
            "ZAI_API_KEY": "zai-key",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "DEEPSEEK_BASE_URL": "https://deepseek.example",
            "COKE_PLANNER_PROVIDER": "deepseek",
            "COKE_PLANNER_MODEL": "deepseek-v4-flash",
            "COKE_INTERACTION_TIMEOUT_S": "31.5",
        }
    )

    interaction_model = config.create_interaction_model()
    planner_model = config.create_planner_model()

    assert config.planner_provider == "deepseek"
    assert DEFAULT_PLANNER_PROVIDER == "zai"
    assert interaction_model.id == DEFAULT_INTERACTION_MODEL
    assert interaction_model.api_key == "zai-key"
    assert str(interaction_model.base_url) == ZAI_BASE_URL
    assert planner_model.id == "deepseek-v4-flash"
    assert planner_model.api_key == "deepseek-key"
    assert str(planner_model.base_url).rstrip("/") == "https://deepseek.example"
    assert planner_model.timeout == 31.5
    assert planner_model.extra_body == {"thinking": {"type": "disabled"}}


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
            "COKE_INTERACTION_MODEL": "glm-5.1-interaction",
            "COKE_DETECTOR_MODEL": "glm-5.1-detector",
            "COKE_INTERACTION_TIMEOUT_S": "31.5",
        }
    )

    interaction_model = config.create_interaction_model()
    planner_model = config.create_planner_model()
    model = config.create_detector_model()

    assert interaction_model.id == "glm-5.1-interaction"
    assert interaction_model.timeout == 31.5
    # Thinking is disabled on every turn-path model, not just the detector:
    # GLM-5.1 thinking mode leaks reasoning into final content and breaks the
    # JSON output protocol (forcing full agent re-runs) while inflating latency.
    assert interaction_model.extra_body == {"thinking": {"type": "disabled"}}
    # Every turn-path text model is on the user's reply critical path, so each
    # must carry the same bounded per-request timeout. Without it the OpenAI
    # client falls back to its ~600s default and a single stalled Z.AI request
    # blocks the whole turn for minutes. See
    # docs/issues/2026-06-09-turn-latency-uncapped-interpreter-timeout.md.
    assert planner_model.timeout == 31.5
    assert planner_model.extra_body == {"thinking": {"type": "disabled"}}
    assert model.id == "glm-5.1-detector"
    assert str(model.base_url) == ZAI_BASE_URL
    assert model.api_key == "test-key"
    assert model.timeout == 31.5
    assert model.extra_body == {"thinking": {"type": "disabled"}}


def test_openai_like_express_model_defaults_to_zai_settings():
    config = ZAILLMConfig.from_env(
        {
            "ZAI_API_KEY": "test-key",
            "COKE_INTERACTION_TIMEOUT_S": "31.5",
        }
    )

    model = config.create_express_model()

    assert model.id == DEFAULT_EXPRESS_MODEL
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
