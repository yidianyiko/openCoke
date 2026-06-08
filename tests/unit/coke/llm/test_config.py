from __future__ import annotations

import pytest

import coke.llm.config as llm_config
from coke.llm.config import (
    DEFAULT_DETECTOR_MODEL,
    DEFAULT_INTERACTION_MODEL,
    DEFAULT_INTERACTION_TIMEOUT_S,
    DEFAULT_INTERPRETER_MODEL,
    SILICONFLOW_BASE_URL,
    LLMConfigurationError,
    SiliconFlowLLMConfig,
)


def test_siliconflow_config_reads_key_base_url_and_default_model_ids():
    config = SiliconFlowLLMConfig.from_env(
        {
            "SiliconFlow_API_KEY": "test-key",
            "DATABASE_URL": "postgresql+psycopg://coke:coke@localhost/coke",
        }
    )

    assert config.api_key == "test-key"
    assert config.base_url == SILICONFLOW_BASE_URL
    assert config.interaction_model == DEFAULT_INTERACTION_MODEL
    assert config.interpreter_model == DEFAULT_INTERPRETER_MODEL
    assert config.detector_model == DEFAULT_DETECTOR_MODEL
    assert llm_config.DEFAULT_INTERACTION_TIMEOUT_S == 45.0
    assert config.interaction_timeout_s == DEFAULT_INTERACTION_TIMEOUT_S
    assert config.agno_database_url == "postgresql+psycopg://coke:coke@localhost/coke"


def test_siliconflow_config_allows_model_and_agno_database_overrides():
    config = SiliconFlowLLMConfig.from_env(
        {
            "SiliconFlow_API_KEY": "test-key",
            "COKE_INTERACTION_MODEL": "custom/interaction",
            "COKE_INTERPRETER_MODEL": "custom/interpreter",
            "COKE_DETECTOR_MODEL": "custom/detector",
            "COKE_INTERACTION_TIMEOUT_S": "12.5",
            "COKE_AGNO_DATABASE_URL": "postgresql+psycopg://agno:agno@localhost/agno",
        }
    )

    assert config.interaction_model == "custom/interaction"
    assert config.interpreter_model == "custom/interpreter"
    assert config.detector_model == "custom/detector"
    assert config.interaction_timeout_s == 12.5
    assert config.agno_database_url == "postgresql+psycopg://agno:agno@localhost/agno"


def test_siliconflow_config_requires_api_key():
    with pytest.raises(LLMConfigurationError, match="SiliconFlow_API_KEY"):
        SiliconFlowLLMConfig.from_env({})


def test_siliconflow_config_rejects_invalid_interaction_timeout():
    with pytest.raises(LLMConfigurationError, match="COKE_INTERACTION_TIMEOUT_S"):
        SiliconFlowLLMConfig.from_env(
            {
                "SiliconFlow_API_KEY": "test-key",
                "COKE_INTERACTION_TIMEOUT_S": "0",
            }
        )


def test_openai_like_model_uses_siliconflow_settings_and_interaction_timeout():
    config = SiliconFlowLLMConfig.from_env(
        {
            "SiliconFlow_API_KEY": "test-key",
            "COKE_INTERACTION_MODEL": "zai-org/GLM-5.1-interaction",
            "COKE_DETECTOR_MODEL": "zai-org/GLM-5.1",
            "COKE_INTERACTION_TIMEOUT_S": "31.5",
        }
    )

    interaction_model = config.create_interaction_model()
    interpreter_model = config.create_interpreter_model()
    model = config.create_detector_model()

    assert interaction_model.id == "zai-org/GLM-5.1-interaction"
    assert interaction_model.timeout == 31.5
    # Thinking is disabled on every turn-path model, not just the detector:
    # GLM-5.1 thinking mode leaks reasoning into final content and breaks the
    # JSON output protocol (forcing full agent re-runs) while inflating latency.
    assert interaction_model.extra_body == {"enable_thinking": False}
    assert interpreter_model.timeout is None
    assert interpreter_model.extra_body == {"enable_thinking": False}
    assert model.id == "zai-org/GLM-5.1"
    assert str(model.base_url) == SILICONFLOW_BASE_URL
    assert model.api_key == "test-key"
    assert model.timeout is None
    assert model.extra_body == {"enable_thinking": False}


def test_siliconflow_config_reads_media_model_ids_without_defaults():
    config = SiliconFlowLLMConfig.from_env(
        {
            "SiliconFlow_API_KEY": "test-key",
            "COKE_ASR_MODEL": "sensevoice-candidate",
            "COKE_VISION_TEXT_MODEL": "qwen-vl-candidate",
            "COKE_MEDIA_MODEL_TIMEOUT_S": "70",
        }
    )

    assert config.asr_model == "sensevoice-candidate"
    assert config.vision_text_model == "qwen-vl-candidate"
    assert config.media_model_timeout_s == 70.0


def test_siliconflow_config_defaults_media_model_ids_to_verified_siliconflow_models():
    config = SiliconFlowLLMConfig.from_env({"SiliconFlow_API_KEY": "test-key"})

    assert config.asr_model == "FunAudioLLM/SenseVoiceSmall"
    assert config.vision_text_model == "Qwen/Qwen3-VL-32B-Instruct"
