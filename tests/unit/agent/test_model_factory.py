from importlib import reload
import json
from pathlib import Path

from agno.models.openai import OpenAIChat
from agno.models.siliconflow import Siliconflow

from agent.agno_agent import agents, model_factory
from agent.agno_agent.workflows import chat_workflow_streaming

ROOT = Path(__file__).resolve().parents[3]


def test_chat_response_config_uses_siliconflow_deepseek_v4_flash():
    expected = {
        "provider": "siliconflow",
        "model_id": "deepseek-ai/DeepSeek-V4-Flash",
        "api_key": "${SiliconFlow_API_KEY}",
        "base_url": "https://api.siliconflow.cn/v1",
    }

    for config_path in (
        ROOT / "conf" / "config.json",
        ROOT / "deploy" / "config" / "coke.config.json",
    ):
        config = json.loads(config_path.read_text())
        chat_response = config["llm"]["roles"]["chat_response"]
        assert chat_response["provider"] == expected["provider"], config_path
        assert chat_response["model_id"] == expected["model_id"], config_path
        assert chat_response["api_key"] == expected["api_key"], config_path
        assert chat_response["base_url"] == expected["base_url"], config_path


def test_reminder_detect_config_uses_siliconflow_glm_51():
    expected = {
        "provider": "siliconflow",
        "model_id": "Pro/zai-org/GLM-5.1",
        "api_key": "${SiliconFlow_API_KEY}",
        "base_url": "https://api.siliconflow.cn/v1",
    }

    for config_path in (
        ROOT / "conf" / "config.json",
        ROOT / "deploy" / "config" / "coke.config.json",
    ):
        config = json.loads(config_path.read_text())
        reminder_detect = config["llm"]["roles"]["reminder_detect"]
        assert reminder_detect["provider"] == expected["provider"], config_path
        assert reminder_detect["model_id"] == expected["model_id"], config_path
        assert reminder_detect["api_key"] == expected["api_key"], config_path
        assert reminder_detect["base_url"] == expected["base_url"], config_path


def test_create_llm_model_uses_role_specific_prepare_config(monkeypatch):
    monkeypatch.setitem(
        model_factory.CONF,
        "llm",
        {
            "provider": "siliconflow",
            "model_id": "Pro/MiniMaxAI/MiniMax-M2.5",
            "api_key": "sk-default",
            "base_url": "https://api.siliconflow.cn/v1",
            "max_retries": 2,
            "roles": {
                "prepare": {
                    "provider": "siliconflow",
                    "model_id": "Pro/MiniMaxAI/MiniMax-M2.5",
                    "api_key": "sk-prepare",
                    "base_url": "https://api.siliconflow.cn/v1",
                    "max_retries": 3,
                }
            },
        },
    )

    model = model_factory.create_llm_model(max_tokens=4096, role="prepare")

    assert isinstance(model, Siliconflow)
    assert model.id == "Pro/MiniMaxAI/MiniMax-M2.5"
    assert model.api_key == "sk-prepare"
    assert model.base_url == "https://api.siliconflow.cn/v1"
    assert model.max_retries == 3
    assert model.max_tokens == 4096


def test_create_llm_model_uses_role_specific_chat_response_config(monkeypatch):
    monkeypatch.setitem(
        model_factory.CONF,
        "llm",
        {
            "provider": "siliconflow",
            "model_id": "Pro/MiniMaxAI/MiniMax-M2.5",
            "api_key": "sk-default",
            "base_url": "https://api.siliconflow.cn/v1",
            "max_retries": 2,
            "roles": {
                "chat_response": {
                    "provider": "openai",
                    "model_id": "gpt-4o",
                    "api_key": "sk-openai",
                    "max_retries": 4,
                }
            },
        },
    )

    model = model_factory.create_llm_model(max_tokens=2048, role="chat_response")

    assert isinstance(model, OpenAIChat)
    assert model.id == "gpt-4o"
    assert model.api_key == "sk-openai"
    assert model.max_retries == 4
    assert model.max_tokens == 2048


def test_runtime_uses_split_prepare_and_chat_models(monkeypatch):
    monkeypatch.setitem(
        model_factory.CONF,
        "llm",
        {
            "provider": "siliconflow",
            "model_id": "Pro/MiniMaxAI/MiniMax-M2.5",
            "api_key": "sk-default",
            "base_url": "https://api.siliconflow.cn/v1",
            "max_retries": 2,
            "roles": {
                "prepare": {
                    "provider": "siliconflow",
                    "model_id": "Pro/MiniMaxAI/MiniMax-M2.5",
                    "api_key": "sk-prepare",
                    "base_url": "https://api.siliconflow.cn/v1",
                    "max_retries": 2,
                },
                "reminder_detect": {
                    "provider": "siliconflow",
                    "model_id": "Pro/zai-org/GLM-5.1",
                    "api_key": "sk-reminder",
                    "base_url": "https://api.siliconflow.cn/v1",
                    "max_retries": 2,
                },
                "post_analyze": {
                    "provider": "siliconflow",
                    "model_id": "Pro/MiniMaxAI/MiniMax-M2.5",
                    "api_key": "sk-post",
                    "base_url": "https://api.siliconflow.cn/v1",
                    "max_retries": 2,
                },
                "chat_response": {
                    "provider": "siliconflow",
                    "model_id": "deepseek-ai/DeepSeek-V4-Flash",
                    "api_key": "sk-chat",
                    "base_url": "https://api.siliconflow.cn/v1",
                    "max_retries": 2,
                },
            },
        },
    )

    reload(agents)
    reload(chat_workflow_streaming)

    workflow = chat_workflow_streaming.StreamingChatWorkflow()

    assert isinstance(agents.reminder_detect_agent.model, Siliconflow)
    assert isinstance(agents.orchestrator_agent.model, Siliconflow)
    assert isinstance(agents.post_analyze_agent.model, Siliconflow)
    assert agents.reminder_detect_agent.model.id == "Pro/zai-org/GLM-5.1"
    assert agents.reminder_detect_agent.model.api_key == "sk-reminder"
    assert agents.orchestrator_agent.model.id == "Pro/MiniMaxAI/MiniMax-M2.5"
    assert agents.orchestrator_agent.model.api_key == "sk-prepare"
    assert agents.post_analyze_agent.model.id == "Pro/MiniMaxAI/MiniMax-M2.5"
    assert isinstance(workflow.agent.model, Siliconflow)
    assert workflow.agent.model.id == "deepseek-ai/DeepSeek-V4-Flash"
