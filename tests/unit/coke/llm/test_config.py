from __future__ import annotations

import pytest

from coke.llm.config import (
    SILICONFLOW_BASE_URL,
    DEFAULT_DETECTOR_MODEL,
    DEFAULT_INTERACTION_MODEL,
    DEFAULT_INTERPRETER_MODEL,
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
    assert config.agno_database_url == "postgresql+psycopg://coke:coke@localhost/coke"


def test_siliconflow_config_allows_model_and_agno_database_overrides():
    config = SiliconFlowLLMConfig.from_env(
        {
            "SiliconFlow_API_KEY": "test-key",
            "COKE_INTERACTION_MODEL": "custom/interaction",
            "COKE_INTERPRETER_MODEL": "custom/interpreter",
            "COKE_DETECTOR_MODEL": "custom/detector",
            "COKE_AGNO_DATABASE_URL": "postgresql+psycopg://agno:agno@localhost/agno",
        }
    )

    assert config.interaction_model == "custom/interaction"
    assert config.interpreter_model == "custom/interpreter"
    assert config.detector_model == "custom/detector"
    assert config.agno_database_url == "postgresql+psycopg://agno:agno@localhost/agno"


def test_siliconflow_config_requires_api_key():
    with pytest.raises(LLMConfigurationError, match="SiliconFlow_API_KEY"):
        SiliconFlowLLMConfig.from_env({})


def test_openai_like_model_uses_siliconflow_settings():
    config = SiliconFlowLLMConfig.from_env(
        {
            "SiliconFlow_API_KEY": "test-key",
            "COKE_DETECTOR_MODEL": "zai-org/GLM-5.1",
        }
    )

    model = config.create_detector_model()

    assert model.id == "zai-org/GLM-5.1"
    assert str(model.base_url) == SILICONFLOW_BASE_URL
    assert model.api_key == "test-key"
    assert model.extra_body == {"enable_thinking": False}
