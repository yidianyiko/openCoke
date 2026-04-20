from importlib import reload

from agno.models.openai import OpenAIChat
from agno.models.siliconflow import Siliconflow

from agent.agno_agent import agents, model_factory
from agent.agno_agent.workflows import chat_workflow_streaming


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
                "post_analyze": {
                    "provider": "siliconflow",
                    "model_id": "Pro/MiniMaxAI/MiniMax-M2.5",
                    "api_key": "sk-post",
                    "base_url": "https://api.siliconflow.cn/v1",
                    "max_retries": 2,
                },
                "chat_response": {
                    "provider": "openai",
                    "model_id": "gpt-4o",
                    "api_key": "sk-openai",
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
    assert agents.reminder_detect_agent.model.id == "Pro/MiniMaxAI/MiniMax-M2.5"
    assert agents.post_analyze_agent.model.id == "Pro/MiniMaxAI/MiniMax-M2.5"
    assert isinstance(workflow.agent.model, OpenAIChat)
    assert workflow.agent.model.id == "gpt-4o"
