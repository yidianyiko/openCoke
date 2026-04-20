import os

from agno.models.deepseek import DeepSeek
from agno.models.openai import OpenAIChat
from agno.models.siliconflow import Siliconflow

from conf.config import CONF


def _get_llm_conf(role: str | None = None) -> dict:
    llm_conf = dict(CONF.get("llm", {}))
    role_configs = llm_conf.pop("roles", {})

    if role:
        role_conf = role_configs.get(role) or {}
        if role_conf:
            llm_conf.update(role_conf)

    return llm_conf


def _resolve_api_key(provider: str, llm_conf: dict) -> str | None:
    configured = llm_conf.get("api_key")
    if configured:
        return configured

    if provider == "siliconflow":
        return os.getenv("SiliconFlow_API_KEY") or os.getenv("SILICONFLOW_API_KEY")
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_API_KEY")
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY")
    return None


def create_llm_model(*, max_tokens: int, role: str | None = None):
    llm_conf = _get_llm_conf(role)
    provider = str(llm_conf.get("provider") or "deepseek").lower()
    model_id = llm_conf.get("model_id") or "deepseek-chat"
    max_retries = int(llm_conf.get("max_retries", 2))
    api_key = _resolve_api_key(provider, llm_conf)
    base_url = llm_conf.get("base_url")

    if provider == "siliconflow":
        return Siliconflow(
            id=model_id,
            api_key=api_key,
            base_url=base_url or "https://api.siliconflow.cn/v1",
            max_retries=max_retries,
            max_tokens=max_tokens,
        )
    if provider == "openai":
        return OpenAIChat(
            id=model_id,
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
            max_tokens=max_tokens,
        )
    if provider == "deepseek":
        return DeepSeek(
            id=model_id,
            api_key=api_key,
            base_url=base_url or "https://api.deepseek.com",
            max_retries=max_retries,
            max_tokens=max_tokens,
        )
    raise ValueError(f"Unsupported llm provider: {provider}")
